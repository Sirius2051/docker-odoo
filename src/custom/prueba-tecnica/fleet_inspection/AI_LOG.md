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

## Lo que escribiste tú sin IA

- El código de los archivos viene de la guía generada por la IA. Mi trabajo fue mover el módulo,
  transcribir cada archivo, entender cada cambio de versión y verificarlo.
- Correr las pruebas antes de migrar para ver el error real de Odoo 17 (`Invalid version
  '16.0.1.0.0'`) y después, para confirmar 10 pruebas sin fallos ni advertencias.
- La prueba manual en la interfaz: instalar Flotilla y el módulo en `dev`, crear e iniciar una inspección.
- Los commits, uno por tipo de cambio.
