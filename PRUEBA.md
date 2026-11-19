# Prueba técnica Binaural — José Avilé

**Versión de Odoo: 17.0.**

Este repositorio no usa `.env`: la versión se define en `instances.json`
(`"odoo_version": "17.0"`). Ese archivo está en `.gitignore`, así que esta es la configuración usada,
sobre `instances.example.jsonc`:

```jsonc
"databases": {
  "v17": { "postgres_version": 16, "port": 5432, "expose_host_port": false,
           "user": "odoo", "password": "odoo", "config": "postgresql.small.conf" }
},
"instances": {
  "prueba-tecnica": {
    "enabled": true,
    "odoo_version": "17.0",
    "external_port": 8069,
    "database": "v17",
    "odoo_config": "17.0_full",
    "overwrite_odoo_config": { "addons": ["src/custom/prueba-tecnica"], "dev_mode": true }
  }
}
```

Se eliminaron las demás bases del ejemplo, porque el validador rechaza varias bases declaradas en
el mismo puerto. Las contraseñas son las de ejemplo del repositorio y no hay datos reales.

## Cómo levantarlo

```bash
cp instances.example.jsonc instances.json   # y aplicar la configuración de arriba
./odoo validate-instances
./odoo build
./odoo start                                # http://localhost:8069
```

Después de instalar o actualizar un módulo con un proceso aparte (`docker exec … odoo -i` o
`./odoo update`), conviene `./odoo restart prueba-tecnica`: el servidor que atiende el navegador
puede seguir con la versión anterior.

## Pruebas

```bash
./odoo test prueba-tecnica -d prueba_limpia \
  -m shop_integration_api,fleet_inspection,sale_commission,payment_request
```

Resultado, con los cuatro módulos juntos en una base nueva: **78 pruebas, 0 fallos, 0 errores;
4 módulos instalados; cobertura 93 %**. Las advertencias del log de `shop_integration_api`
("Webhook … falló, se reintenta") las provocan a propósito las pruebas de reintentos del webhook;
no hay advertencias de obsolescencia.

## Estado por ejercicio

| Ejercicio | Módulo | Tramos | Pruebas | Documentación |
|---|---|---|---|---|
| 1. API para la tienda en línea | `shop_integration_api` | A, B, C | 27 | [README](src/custom/prueba-tecnica/shop_integration_api/README.md) (contrato y errores) · [openapi.yaml](src/custom/prueba-tecnica/shop_integration_api/openapi.yaml) |
| 2. Migración del módulo de inspecciones | `fleet_inspection` | A, B, C | 17 | [README](src/custom/prueba-tecnica/fleet_inspection/README.md) (tabla de cambios de versión) · [MIGRATION_PLAN.md](src/custom/prueba-tecnica/fleet_inspection/MIGRATION_PLAN.md) |
| 3. Ticket urgente T-200 | `sale_commission` | A, B, C | 11 | [INCIDENT.md](src/custom/prueba-tecnica/sale_commission/INCIDENT.md) · PR [#1](https://github.com/Sirius2051/docker-odoo/pull/1) |
| 4. Solicitudes de pago | `payment_request` | A, B, C | 23 | [README](src/custom/prueba-tecnica/payment_request/README.md) (supuestos y preguntas al cliente) · [ARCHITECTURE.md](src/custom/prueba-tecnica/payment_request/ARCHITECTURE.md) |

Cada módulo tiene su `README.md` (tramos completados, cómo probar, supuestos y limitaciones) y su
`AI_LOG.md`.

## Uso de IA

Usé Claude (Claude Code) en los cuatro ejercicios, de dos formas distintas, explicadas en cada
`AI_LOG.md`:

- **Ejercicios 1, 2 y 3:** la IA preparó una guía con el diseño, las alternativas y el código de
  cada archivo. Yo monté el entorno, transcribí el código, entendí cada decisión, corrí y verifiqué
  las pruebas, hice las pruebas manuales y los commits, y resolví los problemas que fueron
  apareciendo. Varios eran errores de la propia guía, y están registrados en cada `AI_LOG.md`.
- **Ejercicio 4:** por falta de tiempo, lo desarrolló **íntegramente la IA** a pedido mío (código,
  pruebas, documentación y commits locales). Yo revisé el resultado y lo publiqué.

## Pendiente y limitaciones

- La concurrencia del ejercicio 4 (dos aprobadores a la vez) se probó a mano con un bloqueo real
  en PostgreSQL, no con una prueba automática; ver ARCHITECTURE.md.
- En el ejercicio 4, los usuarios necesitan correo electrónico para enviar solicitudes, porque se
  notifica al aprobador.
- En el ejercicio 2, Odoo borra la columna vieja `vehicle_type` al terminar la actualización:
  revertir la migración requiere el respaldo (MIGRATION_PLAN.md).
- Las comisiones mal asignadas por el incidente T-200 se detectan con un script de solo lectura;
  corregirlas en producción requiere la revisión del cliente (plan en INCIDENT.md).
- Al instalar, Odoo muestra avisos de `docutils` al interpretar como reStructuredText los README
  escritos en Markdown. No afectan al funcionamiento.

## Flujo de trabajo

Una rama por ejercicio y por tramo, con commits pequeños con prefijo (`[FEAT]`, `[FIX]`, `[MIG]`,
`[TEST]`, `[DOC]`), fusionadas con `--no-ff`:

- `feat/shop-integration-api`, `feat/shop-api-keys-orders`, `feat/shop-api-advanced` (ejercicio 1);
- `mig/fleet-inspection-17`, `mig/fleet-inspection-vehicle-type` (ejercicio 2);
- `hotfix/T-200` con pull request, y `fix/T-200-datos` (ejercicio 3);
- `feat/payment-request` (ejercicio 4).

`git log --oneline --graph` muestra el recorrido.
