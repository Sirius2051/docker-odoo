# AI_LOG — fleet_inspection

## Herramientas

- Claude (Claude Code, modelo Opus 5.5).

## Prompts clave

1. Le pedí la lista de cambios de API entre Odoo 16 y 17 aplicada a este módulo, con el porqué de
   cada uno, y el código de cada archivo para transcribirlo yo.
   - Verificó cada cambio contra el código fuente de Odoo 17: la advertencia de `create` en lote
     (`odoo/api.py`), que `name_get` ya no alimenta `display_name` (`odoo/models.py`), el error de
     validación de `attrs`/`states` en las vistas y que `numbercall` sigue existiendo en 17.
   - Señaló que la prueba vieja de `name_get` seguía pasando en 17 aunque la placa ya no se veía en
     la interfaz: una prueba en verde que no probaba el comportamiento real.
2. Le pedí comprobar que no quedaran advertencias de obsolescencia de este módulo en el log de
   instalación.
3. Le pedí cómo convertir una selección a many2one sin perder datos.
   - Me explicó el orden de una actualización en Odoo (pre-migrate, esquema, datos, post-migrate,
     NOT NULL) y por qué el valor por defecto debía usar `raise_if_not_found=False`: sin eso, todas
     las inspecciones viejas quedarían como "Carro" antes del script. Lo verifiqué migrando una
     base real con una inspección de cada tipo.
4. Le pedí una prueba de la lógica de migración, aunque la base de prueba nunca tuvo la columna vieja.
   - Propuso poner la lógica en un método del modelo y recrear con SQL el esquema que deja la
     actualización (columna vieja, `NOT NULL` quitado), que se deshace solo al terminar la prueba.

## Lo que la IA hizo mal

- **La columna vieja:** la guía decía que Odoo conserva la columna `vehicle_type` después de
  migrar y que servía para revertir sin respaldo. Al revisar la base real después de la
  actualización, la columna ya no existía; el código de Odoo 17 (`_drop_column` en
  `odoo/addons/base/models/ir_model.py`) la borra al terminar la actualización. La migración
  funcionó igual (el post-migrate corre antes de ese borrado), pero corregí el README y el plan:
  revertir requiere el respaldo.
- **La verificación:** por lo mismo, la consulta de la guía que comparaba `vehicle_type` con el
  tipo nuevo después de migrar fallaba (`column fi.vehicle_type does not exist`). La cambié por un
  conteo por tipo antes y después.

## Lo que escribiste tú sin IA

- El código de los archivos viene de la guía generada por la IA. Mi trabajo fue mover el módulo,
  transcribir cada archivo, entender cada cambio de versión y verificarlo.
- Correr las pruebas antes de migrar para ver el error real de Odoo 17 (`Invalid version
  '16.0.1.0.0'`) y después, para confirmar 10 pruebas sin fallos ni advertencias.
- La prueba manual en la interfaz: instalar Flotilla y el módulo en `dev`, crear e iniciar una inspección.
- La migración real: crear una inspección de cada tipo en la versión 17.0.1.0.0, actualizar a
  17.0.2.0.0 y comprobar en la base que cada una quedó con su tipo y ninguna sin tipo.
- Medir la migración de 10 000 filas (0,116 s) y resolver que la interfaz dejara de funcionar.
- Los commits, uno por tipo de cambio.
