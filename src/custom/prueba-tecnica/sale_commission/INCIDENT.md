# INCIDENT T-200 — Los vendedores no pueden confirmar pedidos

| | |
|---|---|
| Cliente | Comercial Los Andes C.A. (ficticia) |
| Severidad | Crítica: ningún vendedor puede vender; mañana sábado es el día de más ventas |
| Inicio | Viernes 12:00, despliegue de la versión 1.1.0 (commit `3f4d73f`) |
| Detección | Viernes 17:40, ticket del cliente |
| Corrección | Versión 1.1.1, rama `hotfix/T-200`, PR: <enlace> |

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