# Inspecciones de vehículos (`fleet_inspection`)

Migrado de **Odoo 16** a **Odoo 17.0**, con el tipo de vehículo convertido de selección a
catálogo (ejercicio 2 de la prueba técnica). Versión del módulo: **17.0.2.0.0**.

## Qué hace

- Registra inspecciones de los vehículos de Flotilla con un checklist de puntos (frenos, luces,
  cauchos…) que se carga solo al crear la inspección.
- Estados: borrador → en curso → aprobada / rechazada. Un punto crítico con falla impide aprobar.
- Tipo de vehículo desde un catálogo configurable (*Flotilla → Configuración → Tipos de vehículo
  (inspecciones)*): moto, carro, camión y otro vienen de serie.
- Grupos: *Inspector* (ve solo sus inspecciones) y *Supervisor de inspecciones* (ve todas,
  aprueba, rechaza y administra el catálogo).
- Acción planificada diaria que marca las inspecciones con más de 7 días en curso y le crea una
  actividad al inspector.
- Reporte PDF de la inspección.

## Tramos completados

- **A:** migración del código a 17.0.
- **B:** tipo de vehículo como catálogo (`fleet.inspection.vehicle.type`), con script de migración
  de datos y pruebas de su lógica.
- **C:** migración idempotente, 10 000 registros por lotes con el tiempo medido y
  [plan de migración](MIGRATION_PLAN.md).

## Cómo probarlo

```bash
./odoo test prueba-tecnica -d prueba_limpia -m fleet_inspection
```

Resultado: **17 pruebas, 0 fallos, 0 errores**; cobertura **95 %**.

| Archivo | Pruebas | Qué demuestra |
|---|---|---|
| `test_fleet_inspection.py` | 10 | El comportamiento de siempre sigue igual en 17: secuencia y checklist al crear, creación en lote, la placa en el nombre, el flujo de estados, un punto crítico bloquea la aprobación, kilometraje no negativo, el inspector solo ve y no borra lo suyo, valor por defecto en el formulario, el cron no repite la actividad |
| `test_vehicle_type_migration.py` | 7 | Cada valor viejo va a su tipo; valores desconocidos o vacíos van a "Otro"; la migración es idempotente; los lotes pequeños no se saltan filas; sin columna vieja no hace nada; el tipo es obligatorio; **10 000 filas por lotes de 1 000** |

### Punto de partida (antes de migrar)

Con el módulo original en la ruta de addons de Odoo 17, el registro no carga:

```text
ValueError: Invalid version '16.0.1.0.0'. Modules should have a version in format `x.y`, `x.y.z`, `17.0.x.y` or `17.0.x.y.z`.
ValueError: Module fleet_inspection: invalid manifest
```

Por eso Binaural lo dejó fuera de la ruta de addons (`src/custom/prueba-tecnica-odoo16/`). El
primer commit de la migración lo mueve con `git mv`, para conservar el historial.

### Sin advertencias de obsolescencia

```bash
./odoo test prueba-tecnica -d mig -m fleet_inspection 2>&1 | grep -E "WARNING|DeprecationWarning" | grep -i fleet_inspection
# (sin salida)
```

### Migración real de datos (base `dev`)

Base con el módulo en **17.0.1.0.0** y cuatro inspecciones, una de cada tipo, actualizada a
**17.0.2.0.0** con `./odoo update prueba-tecnica -d dev -m fleet_inspection -f`:

| Tipo | Antes (`vehicle_type`) | Después (`vehicle_type_id.code`) |
|---|---|---|
| Moto | 1 | 1 |
| Carro | 1 | 1 |
| Camión | 1 | 1 |
| Otro | 1 | 1 |

Inspecciones sin tipo después de migrar: **0**.

## Cambios de versión (16.0 → 17.0)

| Qué cambió | Por qué | Cómo |
|---|---|---|
| Versión del manifiesto | Odoo 17 solo carga módulos `17.0.x.y.z` (error de arriba) | `16.0.1.0.0` → `17.0.1.0.0` (y `17.0.2.0.0` con el tramo B) |
| `states=` en los campos `vehicle_id` y `vehicle_type` | Desde 17 la propiedad `states` de un campo ya no se soporta | Se quitó de Python; `readonly="state != 'draft'"` en la vista |
| `attrs="{...}"` en las vistas | 17 usa expresiones Python directas; `attrs` y `states` dan error de validación | `invisible="not is_overdue"`, `readonly="state in ('approved', 'rejected')"`, `required="state == 'in_progress'"` |
| `states="..."` en los botones | Igual que el anterior | `invisible="state != 'draft'"`, etc. |
| `invisible="1"` en columnas de listas | En 17, `invisible` oculta la celda; la columna entera se oculta con `column_invisible` | `column_invisible="True"` |
| `@api.model def create(self, vals)` | Odoo crea en lote; un `create` de un solo registro genera la advertencia *"not overriding the create method in batch"* | `@api.model_create_multi def create(self, vals_list)`; la lista de puntos se busca una sola vez por lote |
| `name_get()` | Obsoleto en 17: `display_name` ya no lo usa, así que la placa dejaba de verse en la interfaz **aunque la prueba vieja seguía pasando** | `_compute_display_name` con `@api.depends` |
| `(0, 0, {...})` | Funciona; `Command` es la forma actual y legible | `Command.create({...})` |
| `_("…") % valor` | Funciona; con argumentos se traduce el texto completo antes de formatear | `_("…", valor)` |
| `super(FleetInspection, self)` | Estilo de Python 2 | `super()` |
| `t-esc` en el reporte | Funciona; `t-out` es el nombre actual | `t-out` |
| `from odoo.tests.common import Form` | Ruta obsoleta en 17 | `from odoo.tests import Form` |
| Prueba de `name_get` | Llamaba a un método obsoleto | `test_display_name_includes_plate`, y una prueba nueva `test_create_in_batch` |
| (sin cambio) `numbercall` / `doall` en el cron | Siguen existiendo en 17 (se eliminan en 18) | — |
| (sin cambio) `<tree>` | En 17 sigue siendo `<tree>` (en 18 es `<list>`) | — |

## Tramo B: el tipo de vehículo como catálogo

- **Modelo** `fleet.inspection.vehicle.type` (nombre, código, secuencia, activo). Los cuatro tipos
  vienen en `data/fleet_inspection_vehicle_type_data.xml` con `noupdate="1"` (si el cliente
  renombra uno, una actualización futura no se lo pisa). `code` es único y coincide con el valor
  de la antigua selección (`motorcycle`, `car`, `truck`, `other`).
- **Campo** `vehicle_type_id`: obligatorio (ninguna inspección sin tipo; prueba
  `test_type_is_required`) y `ondelete="restrict"` (un tipo en uso no se borra: se archiva).
- **Valor por defecto** "Carro", como antes, protegido con `raise_if_not_found=False`. Al
  actualizar, Odoo llena las columnas nuevas con el valor por defecto **antes** de cargar los
  datos XML; sin esa protección, todas las inspecciones viejas quedarían como "Carro" antes de que
  corra el script, sin un solo error.
- **Script** `migrations/17.0.2.0.0/post-migrate.py`: llama a
  `fleet.inspection._migrate_legacy_vehicle_type()`, que convierte con `UPDATE … FROM` sobre el
  catálogo, por lotes de id. "Otro" se conserva (su código es `other`); los valores desconocidos o
  vacíos también van a "Otro", y se cuentan en el log.
- **La lógica está en un método del modelo** (no en el script) para poder probarla: los scripts de
  `migrations/` no se pueden importar desde una prueba. Las pruebas recrean con SQL el esquema que
  deja una actualización desde 17.0.1 (la columna vieja y `vehicle_type_id` todavía vacío).
- **SQL directo en la conversión**, no ORM: el ORM dispararía el seguimiento en el chatter de cada
  inspección y recalcularía campos. En el resto del módulo, ORM.

## Tramo C: idempotencia, volumen y plan

- **Idempotente:** solo toca filas con `vehicle_type_id IS NULL` (la segunda ejecución convierte 0:
  `test_is_idempotent`); si la columna vieja no existe, no hace nada; el catálogo es `noupdate` con
  código único.
- **10 000 registros por lotes de 1 000: 0,116 s** (prueba `test_migrates_10000_rows_in_batches`;
  el tiempo queda en el log de la prueba, así cualquiera lo reproduce). A esta escala los lotes no
  hacen falta; importan con millones de filas, para no tener una sola transacción gigante que
  bloquee la tabla.
- Pasos para producción, validación y reversión: [MIGRATION_PLAN.md](MIGRATION_PLAN.md).

## Supuestos y limitaciones

- Los valores desconocidos o vacíos de la antigua selección se convierten a "Otro" (y se
  registran en el log), en vez de detener la actualización.
- **Odoo borra la columna vieja `vehicle_type` al terminar la actualización** (`_drop_column`):
  revertir requiere el respaldo. Si el cliente quiere conservar el dato original, un
  `pre-migrate.py` puede renombrar la columna antes.
- `readonly` en la vista no impide un `write()` por código o RPC (tampoco lo hacía `states=`).
- La migración de los módulos estándar de Odoo 16 → 17 (base, fleet, mail) está fuera de alcance:
  se hace con el servicio de actualización de Odoo u OpenUpgrade.
- Después de actualizar el módulo con un proceso aparte (`./odoo update`), el servidor que atiende
  el navegador puede seguir con la versión anterior: hay que reiniciarlo (`./odoo restart`).
- Al instalar, Odoo muestra avisos de `docutils`: interpreta este README en Markdown como
  reStructuredText para la descripción del módulo. No afecta al funcionamiento.
