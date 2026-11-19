# Arquitectura — payment_request

## Seguridad

- **Grupos:** *Solicitante* (todo usuario interno, porque `base.group_user` lo implica: el correo
  dice "cualquier empleado"), *Aprobador* y *Tesorería*. Tesorería implica *Facturación*
  (`account.group_account_invoice`), necesario para crear pagos; es preferible a un `sudo()`, que
  escondería quién creó el pago.
- **Cada regla tiene una capa de interfaz y otra de servidor.** En la interfaz, botones con
  `groups` e `invisible` y campos `readonly`. En el servidor, reglas de registro;
  `_check_group` y `_check_is_assigned_approver` en cada acción; y un `write()` que valida qué grupo
  puede poner cada estado. Esto último es necesario porque el solicitante tiene permiso de escritura
  (para editar su borrador) y podría llamar `write({"state": "approved"})` por RPC; hay una prueba.
- **Bloqueo de edición:** después de enviar se bloquean los campos de negocio (proveedor, monto,
  moneda, fecha, concepto, solicitante, compañía), no toda escritura: el chatter, las actividades y
  los propios botones escriben en el registro.
- **La lógica vive en métodos con guion bajo** (`_action_reject`, `_action_pay`), que Odoo no
  expone por RPC; los botones públicos solo validan y abren asistentes.
- **Niveles:** los lee el aprobador y los administra solo `base.group_system`. Si el aprobador
  pudiera editarlos, podría asignarse el nivel de gerencia.
- **`sudo()`:** uno solo, al buscar el nivel en `action_submit`; el solicitante no necesita leer la
  configuración de niveles.

## Multi-compañía

`company_id` en solicitudes y niveles, con reglas **globales** `company_id in company_ids`. Las
reglas globales se combinan con Y con las de grupo: ni un aprobador de la compañía B, que tiene la
regla "ve todas", ve nada de la A (`test_other_company_user_sees_nothing`). El nivel se busca en la
compañía de la solicitud y el asistente de pago solo ofrece diarios de esa compañía.

## Moneda

- El umbral de los niveles está en la moneda de la compañía; la solicitud se convierte a la fecha
  de la solicitud para elegir el nivel.
- El pago se crea **en la moneda del diario**, convertido con la tasa **de la fecha del pago**
  (`res.currency._convert`); el chatter deja la tasa aplicada. Prueba: 100 USD con tasas de 40 (fecha
  de la solicitud) y 45 (fecha del pago) → 4.500 VES.
- **Alternativa no elegida:** crear el pago en USD desde el diario en VES y dejar que Odoo calcule
  la diferencia en cambio. Conserva el dato en USD para conciliar con la factura del proveedor; es
  una decisión de contabilidad.

## Concurrencia: dos aprobadores al mismo tiempo

`SELECT … FOR UPDATE NOWAIT` sobre las filas de la solicitud, al principio de aprobar, rechazar y
pagar, **antes** de revisar el estado, y releyendo el estado después del bloqueo
(`invalidate_recordset`). Con un `if` en Python, dos transacciones simultáneas leerían las dos
"enviada" y las dos aprobarían. Con el bloqueo, la segunda falla de inmediato con un mensaje claro.
El `savepoint(flush=False)` permite recuperar la transacción tras el `LockNotAvailable`. Es el
mismo patrón que usa el módulo `account` de Odoo 17 (`account_move.py`).

- **Alternativa:** `FOR UPDATE` sin `NOWAIT`. La segunda espera, recibe un error de serialización
  (Odoo usa lectura repetible), Odoo reintenta y entonces ve "aprobada". También es correcta, pero el
  usuario espera sin saber por qué.
- **Cómo se probó:** a mano, en la base `dev`: otra transacción bloqueó la fila desde `psql` y el
  aprobador intentó aprobar al mismo tiempo (resultado en el README). No hay prueba automática: las
  pruebas de Odoo corren en una sola transacción y no pueden simular dos.

## Atomicidad del pago

Crear el pago, publicarlo y marcar la solicitud como pagada ocurren en la **misma transacción**, y
el estado se escribe después de `action_post()`. Si algo falla, la excepción sube y Odoo deshace
todo: no queda un pago sin solicitud pagada ni una solicitud pagada sin pago. No se atrapa la
excepción ni se hace `commit()`. Prueba: `test_failed_payment_does_not_mark_paid` (simula el fallo
de `action_post`). Doble pago: estado `approved` y `payment_id` vacío se revisan después del bloqueo
(`test_cannot_pay_twice`).

## Secuencia

`SP/%(range_year)s/` con `use_date_range`: el año sale de la **fecha de la solicitud** (no de hoy) y
el contador se reinicia cada año. Con rangos de fechas, Odoo interpola `%(year)s` con el año
actual; el del rango es `%(range_year)s` (`ir_sequence.py`, `_interpolation_dict`).
