# Plan de migración — fleet_inspection 16.0 → 17.0.2.0.0

## Alcance

- Código del módulo a Odoo 17 (17.0.1.0.0) y datos: tipo de vehículo de selección a catálogo
  `fleet.inspection.vehicle.type` (17.0.2.0.0).
- Fuera de alcance: la migración de los módulos estándar de Odoo 16 → 17 (base, fleet, mail).
  Se hace con el servicio de actualización de Odoo u OpenUpgrade, **antes** de este módulo.

## Cómo funciona la conversión

Al ejecutar `-u fleet_inspection`, Odoo hace, en este orden:

1. **Esquema:** crea la tabla del catálogo y la columna `vehicle_type_id`. La deja vacía: el valor
   por defecto ("Carro") no encuentra todavía su registro, a propósito
   (`raise_if_not_found=False`). La columna vieja `vehicle_type` sigue en la tabla.
2. **Datos:** carga los cuatro tipos del catálogo. Su `code` es el valor de la antigua selección.
3. **`migrations/17.0.2.0.0/post-migrate.py`:** llama a `_migrate_legacy_vehicle_type()`, que
   convierte con `UPDATE … FROM` por lotes de id. Lo desconocido o vacío queda como "Otro" y se
   registra en el log. Escribe en el log cuántas convirtió y en cuánto tiempo.
4. **Final de la actualización:** Odoo aplica `NOT NULL` a `vehicle_type_id` y **borra la columna
   vieja `vehicle_type`** (el campo ya no existe en el modelo). Si quedara alguna inspección sin
   tipo, el log diría `unable to set NOT NULL`: es la alarma.

## Idempotencia (se puede correr más de una vez sin daño)

- Solo toca filas con `vehicle_type_id IS NULL`: la segunda ejecución convierte 0
  (prueba `test_is_idempotent`).
- Si la columna vieja no existe (instalación nueva o migración ya hecha), no hace nada
  (`test_without_legacy_column_does_nothing`).
- El catálogo es `noupdate="1"` y `code` es único: no se duplica ni se pisa lo que edite el cliente.
- Si la actualización falla a medias, Odoo deshace la transacción completa y se puede repetir.

## Tiempos medidos

| Filas | Lote | Tiempo | Dónde |
|---|---|---|---|
| 4 | 5 000 | — (instantáneo) | Base `dev`, actualización real de 17.0.1.0.0 a 17.0.2.0.0 |
| 10 000 | 1 000 | **0,116 s** | Prueba `test_migrates_10000_rows_in_batches` |

A esta escala los lotes no hacen falta. Importan con millones de filas: cada `UPDATE` toca como
máximo un lote, en lugar de una sola transacción gigante que bloquee la tabla y llene el registro
de cambios de PostgreSQL.

## Antes

1. Respaldo completo (`pg_dump` y *filestore*) y una prueba de restauración. **Es la única forma
   de revertir** (ver abajo).
2. Ensayo en una copia de producción; anotar el tiempo real.
3. Guardar el conteo por tipo:

   ```sql
   SELECT vehicle_type, count(*) FROM fleet_inspection GROUP BY 1 ORDER BY 1;
   ```

## Durante

1. Ventana de mantenimiento: el tiempo del ensayo más un margen.
2. `odoo -d <base> -u fleet_inspection --stop-after-init`.
3. Revisar el log: la línea `fleet_inspection 17.0.2.0.0: N inspecciones convertidas … en X s`,
   ninguna línea `unable to set NOT NULL` y, si la hay, la advertencia de valores que quedaron
   como "Otro".
4. Reiniciar el servicio de Odoo.

## Validación

1. Conteo por tipo después, para comparar con el de antes (la columna vieja ya no existe, así que
   la comparación es contra el conteo guardado):

   ```sql
   SELECT t.code, count(fi.id) FROM fleet_inspection_vehicle_type t
     LEFT JOIN fleet_inspection fi ON fi.vehicle_type_id = t.id GROUP BY 1 ORDER BY 1;
   SELECT count(*) AS sin_tipo FROM fleet_inspection WHERE vehicle_type_id IS NULL;
   ```

   Mismo número por tipo que antes, y `sin_tipo` = 0.
2. Prueba funcional: crear, iniciar, aprobar e imprimir una inspección.

## Reversión

- **Restaurar el respaldo.** Odoo borra la columna vieja `vehicle_type` al terminar la
  actualización, así que sin respaldo no se puede reconstruir el dato original.
- Si el cliente quiere conservar el dato viejo dentro de la base, se agrega un
  `migrations/17.0.2.0.0/pre-migrate.py` que **renombre** la columna (por ejemplo a
  `legacy_vehicle_type`) y el método lee de ahí: Odoo solo borra columnas con el nombre de un
  campo eliminado. No se hizo en esta entrega.
