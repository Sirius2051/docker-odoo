# Solicitudes de pago (`payment_request`)

Solicitudes de pago a proveedores con aprobación por niveles y registro en contabilidad
(ejercicio 4 de la prueba técnica). Odoo 17.0, versión del módulo 17.0.2.0.0.

> **Autoría:** este módulo lo desarrolló íntegramente la IA (Claude) a pedido mío, por falta de
> tiempo. Detalle en [AI_LOG.md](AI_LOG.md).

## Tramos completados

- **A:** modelo con chatter, secuencia `SP/AAAA/NNNN`, estados, grupos, reglas de registro, vistas,
  menú y pruebas.
- **B:** niveles de aprobación por monto, actividad al aprobador, asistente de rechazo con motivo,
  asistente de pago que crea el `account.payment` de proveedor, reporte PDF.
- **C:** pago en la moneda del diario a la tasa de la fecha del pago, multi-compañía, bloqueo en la
  base de datos para aprobadores simultáneos, y pago atómico. Decisiones en
  [ARCHITECTURE.md](ARCHITECTURE.md).

## Cómo probarlo

```bash
./odoo test prueba-tecnica -d prueba_limpia -m payment_request
```

Resultado: **23 pruebas, 0 fallos, 0 errores**; cobertura **91 %**.

| Archivo | Pruebas | Qué demuestra |
|---|---|---|
| `test_payment_request.py` | 17 | Flujo hasta aprobada; la secuencia toma el año de la solicitud; el nivel asigna el aprobador según el monto; actividad al aprobador, que se cierra al aprobar; solo el aprobador asignado aprueba; sin nivel no se envía; rechazo con motivo en el chatter y vuelta a borrador; motivo obligatorio; el solicitante solo ve lo suyo y no aprueba **ni por el método ni con `write({"state": ...})`**; nadie aprueba su propia solicitud; enviada no se edita; monto mayor que cero; tesorería no paga sin aprobación; no se borra lo enviado; los botones *Aprobar* y *Pagar* solo llegan al grupo que corresponde |
| `test_payment_request_payment.py` | 6 | El pago crea un `account.payment` de proveedor publicado y vinculado; **no se paga dos veces**; el aprobador no puede pagar; 100 USD desde un diario en VES = 4.500 VES con la tasa del día del pago (45), no la de la solicitud (40); si la publicación del pago falla, la solicitud **no** queda pagada ni queda un pago suelto; un usuario de otra compañía no ve solicitudes ni niveles |

La segunda clase usa `AccountTestInvoicingCommon`, que carga un plan de cuentas de prueba, diarios
y una segunda compañía.

### Prueba de concurrencia (manual, base `dev`)

Con una solicitud enviada, otra transacción bloquea su fila desde PostgreSQL
(`BEGIN; SELECT id FROM payment_request WHERE id = 3 FOR UPDATE; SELECT pg_sleep(25); COMMIT;`) y,
al mismo tiempo, el aprobador asignado intenta aprobar:

| Intento | Resultado |
|---|---|
| Con la fila bloqueada | *"Otro usuario está procesando esta solicitud. Intenta de nuevo en unos segundos."* (inmediato, sin esperar) |
| Con el bloqueo liberado | Aprobada |
| Un segundo intento sobre la ya aprobada | *"La solicitud SP/2026/0001 está en estado «Aprobada» y no admite esta acción."* |

## Configuración

1. **Grupos** (*Ajustes → Usuarios*, sección *Solicitudes de pago*): todo usuario interno ya es
   **Solicitante**; marcar **Aprobador** y **Tesorería** a quien corresponda.
2. **Niveles** (*Solicitudes de pago → Configuración → Niveles de aprobación*, lo edita un
   administrador): por ejemplo, desde 0 el jefe del área; desde 5.000 gerencia. El monto mínimo
   está en la moneda de la compañía.
3. **Diarios de banco o caja** en Contabilidad, para pagar.

| Grupo | Puede |
|---|---|
| Solicitante (todo usuario interno) | Crear, editar en borrador, enviar; ver **solo las suyas**; volver a borrador las rechazadas |
| Aprobador | Ver todas; aprobar o rechazar **las que tiene asignadas** (nunca las propias); leer los niveles |
| Tesorería | Ver todas; pagar las aprobadas desde un diario (crea el pago contable). Implica *Facturación* |
| Administrador (`base.group_system`) | Configurar los niveles de aprobación |

## Flujo

Borrador → **Enviar** (se asigna el aprobador según el monto y se le crea una actividad) →
**Aprobar** (registra quién y cuándo) o **Rechazar** (asistente con motivo obligatorio, publicado
en el chatter; el solicitante lo recibe como seguidor) → **Pagar** (asistente con diario y fecha;
crea y publica el pago de proveedor) → Pagada. Una rechazada puede volver a borrador. El PDF
(*Imprimir → Solicitud de pago*) muestra quién aprobó y cuándo, el motivo del rechazo y el pago.

## Supuestos y preguntas al cliente

| Pregunta para Carolina | Supuesto para avanzar |
|---|---|
| ¿"Cualquier empleado" incluye usuarios del portal? | No: todo usuario interno es Solicitante |
| Si se rechaza, ¿el empleado puede corregirla? | Sí: la vuelve a borrador, la edita y la reenvía |
| ¿Cuánto es un pago "grande"? ¿En qué moneda se mide? | Niveles configurables; umbral en la moneda de la compañía, convertido a la fecha de la solicitud |
| ¿El "jefe del área" depende del área del solicitante? | Un aprobador por nivel de monto (no por área) |
| ¿El aprobador puede aprobar su propia solicitud? | No (segregación de funciones) |
| Si el nivel asigna como aprobador al propio solicitante, ¿quién la aprueba? | Hoy nadie puede: queda pendiente de decidir (pasar al nivel siguiente o a gerencia) |
| ¿Basta con ver el motivo del rechazo en el historial o debe llegar por correo? | Chatter; el solicitante es seguidor y recibe la notificación |
| ¿Se paga contra una factura existente o es un pago suelto? | Pago suelto al proveedor; la conciliación con la factura la hace contabilidad |
| ¿A qué tasa se pagan en bolívares las solicitudes en dólares (solicitud, aprobación, pago; BCV)? | La tasa de la fecha del pago registrada en Odoo |
| ¿El pago en bolívares debe conservar el monto en dólares? | Se crea en la moneda del diario y el chatter deja la tasa aplicada (alternativa en ARCHITECTURE.md) |
| ¿Cada compañía tiene su propia numeración? | Una secuencia compartida `SP/año/número` |
| ¿Se pueden borrar solicitudes? | Solo en borrador |

## Limitaciones conocidas

- **Los usuarios necesitan correo electrónico.** Enviar una solicitud crea una actividad y una
  notificación; si el solicitante no tiene correo, Odoo responde *"No se puede enviar el mensaje,
  configure la dirección de correo electrónico del remitente"*. Se vio en la prueba manual con un
  usuario técnico sin correo.
- El aprobador es uno por nivel de monto, no por área del solicitante.
- La concurrencia se probó a mano (tabla de arriba): las pruebas de Odoo corren en una sola
  transacción y no pueden simular dos simultáneas.
- El pago no se concilia automáticamente con la factura del proveedor.
- Al instalar, Odoo muestra avisos de `docutils` si interpreta un README en Markdown como
  reStructuredText; este módulo declara `description` en el manifiesto para evitarlo.
