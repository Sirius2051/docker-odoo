# Inspecciones de vehículos (`fleet_inspection`)

Migrado de **Odoo 16** a **Odoo 17.0** (ejercicio 2 de la prueba técnica).

## Qué hace

- Registra inspecciones de los vehículos de Flotilla con un checklist de puntos (frenos, luces,
  cauchos…) que se carga solo al crear la inspección.
- Estados: borrador → en curso → aprobada / rechazada. Un punto crítico con falla impide aprobar.
- Tipo de vehículo: moto, carro, camión u otro.
- Grupos: *Inspector* (ve solo sus inspecciones) y *Supervisor de inspecciones* (ve todas,
  aprueba y rechaza).
- Acción planificada diaria que marca las inspecciones con más de 7 días en curso y le crea una
  actividad al inspector.
- Reporte PDF de la inspección.

## Tramos completados

- **A:** migración a 17.0.
- B y C no realizados en esta entrega (el diseño propuesto está al final).

## Cómo probarlo

```bash
./odoo test prueba-tecnica -d prueba_limpia -m fleet_inspection
```

Resultado: **10 pruebas, 0 fallos, 0 errores**; cobertura **93 %**.

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

### Prueba manual (base `dev`)

Instalado junto con Flotilla en una base con datos de demostración: una inspección nueva toma el
número `INS/AAAA/NNNN`, carga el checklist, muestra la placa en su nombre y, al iniciarla, el
vehículo, el tipo y la fecha quedan de solo lectura.

## Cambios de versión (16.0 → 17.0)

| Qué cambió | Por qué | Cómo |
|---|---|---|
| Versión del manifiesto | Odoo 17 solo carga módulos `17.0.x.y.z` (error de arriba) | `16.0.1.0.0` → `17.0.1.0.0` |
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

## Supuestos y limitaciones

- `readonly` en la vista no impide un `write()` por código o RPC (tampoco lo hacía `states=`). Si
  el negocio exige que el vehículo no cambie después de iniciar la inspección, se agrega una
  validación en `write`.
- La migración de los módulos estándar de Odoo 16 → 17 (base, fleet, mail) está fuera de alcance:
  se hace con el servicio de actualización de Odoo u OpenUpgrade.
- Al instalar, Odoo muestra avisos de `docutils`: interpreta este README en Markdown como
  reStructuredText para la descripción del módulo. No afecta al funcionamiento.

## Tramos B y C (no realizados): diseño propuesto

- **B:** catálogo `fleet.inspection.vehicle.type` con un campo `code` igual al valor de la antigua
  selección; campo `vehicle_type_id` obligatorio con valor por defecto protegido
  (`raise_if_not_found=False`: al actualizar, Odoo llena las columnas nuevas con el valor por
  defecto **antes** de cargar los datos, y sin esa protección todas las inspecciones viejas
  quedarían como "Carro" antes del script); script `migrations/17.0.2.0.0/post-migrate.py` que llama
  a un método del modelo (probado) con `UPDATE … FROM` por lotes de id y `WHERE vehicle_type_id IS NULL`.
  La columna vieja se conserva para poder revertir.
- **C:** idempotencia por `IS NULL`, comprobación de que la columna vieja existe y datos
  `noupdate`; prueba con 10 000 filas por lotes con el tiempo medido; `MIGRATION_PLAN.md`.
