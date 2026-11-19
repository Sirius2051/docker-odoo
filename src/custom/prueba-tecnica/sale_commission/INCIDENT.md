# INCIDENT T-200 — Los vendedores no pueden confirmar pedidos

| | |
|---|---|
| Cliente | Comercial Los Andes C.A. (ficticia) |
| Severidad | Crítica: ningún vendedor puede vender; mañana sábado es el día de más ventas |
| Inicio | Viernes 12:00, despliegue de la versión 1.1.0 (commit `3f4d73f`) |
| Detección | Viernes 17:40, ticket del cliente |
| Corrección | Versión 1.1.1, rama `hotfix/T-200`, PR [#1](https://github.com/Sirius2051/docker-odoo/pull/1) (fusionado) |
| Datos y prevención | Rama `fix/T-200-datos` (tramo C) |

## Cómo se reproduce

1. Usuario con el grupo *Ventas: Usuario: solo documentos propios* (en la base de prueba,
   `vendedor_t200`).
2. Crear una cotización y pulsar *Confirmar*.
3. Error en pantalla:

   ```text
   No puede acceder a los registros 'Comisión por categoría de producto' (sale.commission.rule).

   Esta operación está permitida para los siguientes grupos:
       - Ventas/Administrador
   ```

4. En el log del servidor (Odoo no guarda *traceback* de los errores de permisos):

   ```text
   INFO dev odoo.addons.base.models.ir_model: Access Denied by ACLs for operation: read, uid: 9, model: sale.commission.rule
   WARNING dev odoo.http: No puede acceder a los registros 'Comisión por categoría de producto' (sale.commission.rule).
   ```

Con el administrador (gerente de ventas) la confirmación funciona, igual que describe el cliente.

## Causa raíz

Al confirmar, `sale.order.action_confirm()` fija el porcentaje de cada línea con
`sale.order.line._get_commission_percent()`, que **busca en `sale.commission.rule`** (el modelo
nuevo de la versión 1.1.0) **con el usuario que confirma**:

```text
File ".../sale_commission/models/sale_order.py", line 10, in action_confirm
    line.commission_percent = line._get_commission_percent()
File ".../sale_commission/models/sale_order_line.py", line 28, in _get_commission_percent
odoo.exceptions.AccessError: You are not allowed to access 'Comisión por categoría de producto' (sale.commission.rule) records.
```

El archivo de permisos (`security/ir.model.access.csv`) solo le daba acceso a ese modelo al grupo
*gerente de ventas*. El vendedor recibe un `AccessError` en la operación de **lectura**, y Odoo
deshace la confirmación completa.

**Por qué no lo detectaron las pruebas:** el mismo commit `3f4d73f` cambió el helper de las
pruebas: `self.env["sale.order"].with_user(user).create(...)` pasó a
`self.env["sale.order"].create(...)`. Desde entonces las pruebas corrían como administrador, que
no está sujeto a permisos. Las pruebas se adaptaron al código, en lugar de al revés.

**Segundo error, en la misma función:** cuando el producto no tiene regla de categoría, se
devolvía `self.env.user.commission_percent`, el porcentaje de **quien confirma**, en lugar del
vendedor del pedido (`self.order_id.user_id`), que es lo que se usaba antes del commit. Las
pruebas tampoco lo veían, porque el commit le asignó al administrador el mismo 5 % que al vendedor
de prueba. Este error está generando datos incorrectos **ahora mismo**: esta tarde el gerente
confirmó los pedidos de todos los vendedores, y esas líneas quedaron con el porcentaje del gerente.

## Corrección

| Commit | Cambio |
|---|---|
| `7775d17` | Pruebas que reproducen el error con un vendedor (fallan antes de corregir) |
| `d4b1e1b` | Permiso de **solo lectura** de `sale.commission.rule` para `sales_team.group_sale_salesman`; versión 1.1.1 |
| `e2910b7` | `_get_commission_percent()` usa `self.order_id.user_id` en lugar de `self.env.user` |

- **Por qué un permiso de lectura:** el vendedor necesita **leer** la configuración de comisiones
  para calcular su propia comisión, y eso no le da poder de cambiarla (lo verifica la prueba
  `test_t200_salesman_cannot_edit_rules`). El vendedor ya ve su comisión en cada línea; ver el
  porcentaje de la categoría no le revela nada nuevo.
- **Alternativa descartada:** `sudo()` en la búsqueda de reglas. También era válida con
  justificación, pero prefiero que el permiso quede declarado en el CSV, donde se audita la
  seguridad, y no escondido en una línea de Python.
- **Lo que no se hizo:** darle al vendedor el grupo de gerente (permisos de más), atrapar el
  `AccessError` y devolver 0 (escondería el síntoma con comisiones en cero), ni revertir el
  despliegue (Odoo recalcularía las comisiones de líneas existentes y el cliente perdería la
  funcionalidad que pidió).
- **Por qué el segundo error va en el mismo hotfix:** no es una mejora oportunista; la contención
  de esta tarde (el gerente confirmando) estaba generando comisiones incorrectas, y cualquier
  pedido confirmado por otra persona seguiría saliendo mal. Es una línea, en la misma función, con
  su propia prueba y su propio commit.

## Prueba

- `_create_order` vuelve a crear los pedidos **como el vendedor** (`with_user`), como antes del
  commit `3f4d73f`.
- Se eliminó `cls.env.user.commission_percent = 5.0`; hay un gerente de prueba con **1 %** para que
  confundir "quien confirma" con "el vendedor del pedido" haga fallar algo.
- Pruebas nuevas: el vendedor confirma su pedido; el gerente sigue confirmando; si el gerente
  confirma un pedido ajeno se usa el porcentaje del vendedor; el vendedor **no** puede modificar
  reglas.

**Antes de la corrección** (commit `7775d17`): 8 pruebas, **1 fallo y 5 errores**.

```text
ERROR: TestSaleCommission.test_commission_by_category
ERROR: TestSaleCommission.test_commission_on_confirm
ERROR: TestSaleCommission.test_salesman_report_only_own
ERROR: TestSaleCommission.test_subcategory_uses_most_specific_rule
ERROR: TestSaleCommission.test_t200_salesman_can_confirm_own_order
    → odoo.exceptions.AccessError: You are not allowed to access 'Comisión por categoría de producto' (sale.commission.rule) records.
FAIL: TestSaleCommission.test_t200_manager_confirming_keeps_salesman_percent
    → AssertionError: 1.0 != 5.0   (se guardó el porcentaje del gerente, no el del vendedor)
```

**Después** (commit `e2910b7`): 8 pruebas, **0 fallos y 0 errores**.

```bash
./odoo test prueba-tecnica -d t200 -m sale_commission
```

## Contención (primeros 15 minutos, antes de tener la corrección)

Crear el mismo permiso desde la interfaz, en producción: *Ajustes → Técnico → Seguridad →
Derechos de acceso → Nuevo*: modelo `sale.commission.rule`, grupo *Ventas / Usuario: solo
documentos propios*, solo lectura.

- **Reversible:** se borra ese registro.
- **Riesgos:** es un cambio manual en producción, así que hay que registrarlo y retirarlo al
  desplegar la corrección (el del módulo lo reemplaza). **No** corrige el porcentaje de los
  pedidos que confirme otra persona (el segundo error).
- **Descartado:** que el gerente siga confirmando (genera comisiones incorrectas en cada pedido y
  no escala un sábado); revertir el despliegue; dar el grupo de gerente a los vendedores.

## Commit que introdujo el error y por qué pasó la revisión

`3f4d73f [FEAT] sale_commission: porcentaje de comisión por categoría de producto`, el único
commit del despliegue del mediodía:

```bash
git log --oneline -- src/custom/prueba-tecnica/sale_commission
git show 3f4d73f -- src/custom/prueba-tecnica/sale_commission/tests src/custom/prueba-tecnica/sale_commission/security
```

Con más commits, `git bisect` lo encontraría solo: `git bisect start`, `git bisect bad HEAD`,
`git bisect good ad51040`, `git bisect run ./odoo test prueba-tecnica -d bisect -m sale_commission`
(con la prueba nueva disponible en cada paso).

**Por qué pasó la revisión:** el commit modificó las pruebas existentes para que pasaran (quitó
`with_user`) y les dio a los dos usuarios el mismo porcentaje. Todo quedó en verde, pero las
pruebas dejaron de probar el caso real: un vendedor confirmando su pedido.

## Despliegue y verificación

1. Respaldo de la base de datos y del *filestore*.
2. Traer la rama con la corrección al servidor.
3. Actualizar **solo** este módulo (el permiso nuevo está en un CSV, que solo se carga al
   actualizar): `odoo -d <base> -u sale_commission --stop-after-init`.
4. Reiniciar el servicio de Odoo.
5. Entrar como un vendedor, confirmar un pedido de prueba, revisar el porcentaje de la línea y
   cancelar el pedido.
6. Borrar el permiso manual de la contención.
7. Avisar al cliente.

## Mensaje al cliente


>Buenas noches. Les comparto el estatus sobre el inconveniente de hoy:
>Causa: La actualización del mediodía no habilitó el acceso de los vendedores a la nueva configuración de comisiones.
>Solución: Ya aplicamos la corrección y validamos que pueden confirmar pedidos sin problema, por lo que mañana podrán operar con normalidad.
>Próximos pasos: Estamos revisando los pedidos que confirmó el gerente esta tarde, ya que podrían tener la comisión mal calculada. El lunes les enviamos el detalle.

## Impacto en los datos (tramo C)

**Qué quedó mal:** entre el despliegue (12:00) y la corrección, los pedidos que confirmó el
gerente en nombre de los vendedores se guardaron, en las líneas sin regla de categoría, con **el
porcentaje del gerente** en lugar del del vendedor. El reporte asigna la comisión al vendedor
correcto (usa el vendedor del pedido), pero con un monto incorrecto.

**Cómo se detecta:** `sale.order.line._get_commission_mismatches(desde)` lista las líneas de
pedidos confirmados desde una fecha (UTC) cuyo porcentaje guardado no coincide con el que
corresponde hoy al vendedor del pedido. Tiene dos pruebas: lista solo las líneas incorrectas, e
ignora los pedidos anteriores a la fecha.

El script `scripts/t200_affected_lines.py` lo llama, escribe un CSV por la salida estándar y
**deshace la transacción** (`env.cr.rollback()`): no modifica nada.

```bash
docker exec -i <contenedor_odoo> odoo shell -c /home/odoo/.config/odoo.conf -d <base> --no-http \
    < src/custom/prueba-tecnica/sale_commission/scripts/t200_affected_lines.py > t200_afectadas.csv
```

`CONFIRMED_SINCE` va en UTC: las 12:00 de Venezuela son las 16:00 UTC.

**Ejemplo real** (base de prueba `dev`): un pedido del vendedor `vendedor_t200` (5 %), confirmado
por el administrador, con la línea guardada al 1 % para simular lo que dejó el error:

```text
pedido,fecha_confirmacion,vendedor,confirmado_por,linea_id,producto,porcentaje_guardado,porcentaje_correcto,comision_guardada,comision_correcta,diferencia
S00027,2026-11-19 20:34:59,vendedor_t200,__system__,53,[API-001] Producto API prueba,1.0,5.0,0.2,1.0,0.8
# Líneas afectadas: 1 · diferencia total de comisiones: 0.80
```

Sin ese caso fabricado, el mismo script sobre `dev` daba 0 líneas afectadas.

**Columna `confirmado_por`:** usa `write_uid`, el último usuario que modificó el pedido. Es una
pista, no una prueba: alguien pudo editarlo después. El dato exacto de quién confirmó está en el
historial del pedido (el seguimiento del campo de estado).

**Limitación:** se compara con las reglas vigentes al ejecutar el script. Si una regla de
categoría cambió después del incidente, una línea correcta en su momento aparecería como
afectada; por eso el paso 2 del plan es revisar el listado.

## Plan de corrección

1. Ejecutar el script en producción con la hora real del despliegue y guardar el CSV.
2. Revisar el CSV con el cliente (administración): confirmar las líneas y preguntar si alguna
   comisión ya se pagó (esas requieren un ajuste en la nómina, no solo en Odoo).
3. Respaldo de la base de datos.
4. Corregir **solo** las líneas confirmadas del CSV, en una transacción, desde `odoo shell`:
   `env["sale.order.line"].browse(<ids>)` y, para cada una,
   `line.commission_percent = line._get_commission_percent()`; después `env.cr.commit()`.
   **No** usar el botón *Recalcular comisiones* pedido por pedido: toca todas las líneas.
5. Volver a ejecutar el script: debe dar 0 líneas afectadas.
6. Comparar el total del reporte *Comisiones* por vendedor antes y después, y enviar el resumen
   al cliente.

## El mismo patrón en otra parte del módulo

- **`action_recompute_commissions`** repetía la lógica de cálculo con otra regla: buscaba la
  categoría **exacta**, sin categorías padre y sin compañía. Un producto de *Repuestos / Frenos*
  recibía un porcentaje al confirmar y otro al recalcular. **Corregido** reutilizando
  `_get_commission_percent()`, con una prueba que falla antes (`44d700c`) y pasa después
  (`6fda0ae`).
- **El botón *Recalcular comisiones*** no tiene restricción de grupo: cualquier vendedor puede
  recalcular un pedido confirmado. **Pregunta al cliente:** ¿debería ser solo del gerente? No se
  cambió porque altera el comportamiento para el cliente.

## Prevención

1. **Regla de revisión:** un PR que modifica una prueba existente para que pase (quitar
   `with_user`, ajustar datos) explica por qué en la descripción. Fue la señal de este incidente.
2. **Las pruebas de flujos de usuario corren con el usuario del rol** (`with_user(vendedor)`).
   Correr como administrador prueba la lógica, no los permisos.
3. **Modelo nuevo, revisión de permisos:** por cada modelo nuevo, preguntar "¿qué grupos lo
   **leen** en el flujo normal?", no solo "¿quién lo administra?".
4. **Datos de prueba que distingan:** cada usuario de prueba con un valor distinto (5 % y 1 %),
   para que confundir uno con otro haga fallar algo.
5. **Una sola implementación de cada regla de negocio:** si dos métodos calculan lo mismo, uno
   llama al otro (fue el problema del recálculo).
6. **Correr las pruebas después de cada commit** (por ejemplo, en un *pre-commit* o en CI): en
   este mismo trabajo, un error de transcripción (`rom` en lugar de `from`) llegó a un commit y
   se detectó después, al ejecutar el script; se corrigió en `479c809`.
7. **Ensayo en *staging* con un usuario de cada rol** antes de desplegar en producción, y no
   desplegar un viernes al mediodía sin ese ensayo.
