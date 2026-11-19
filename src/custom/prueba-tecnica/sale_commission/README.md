# Comisiones de vendedores (`sale_commission`)

Calcula la comisión del vendedor en cada línea de pedido de venta y ofrece un análisis mensual por vendedor.
Versión **1.1.1** (corrección del ticket T-200).

## Configuración

- **Porcentaje del vendedor:** Ajustes › Usuarios › pestaña *Comisiones* (solo gerentes de ventas).
- **Porcentaje por categoría (desde la 1.1):** Inventario/Ventas › Configuración › Categorías de producto,
  campo *Comisión (%)*. Si la categoría (o una categoría padre) tiene porcentaje, reemplaza al del vendedor.

## Cómo funciona

- Al confirmar el pedido se fija el porcentaje en cada línea y se calcula la comisión sobre el subtotal sin impuestos.
- Sin regla de categoría, se usa el porcentaje del **vendedor del pedido** (no el de quien lo confirma).
- El botón *Recalcular comisiones* del pedido vuelve a aplicar los porcentajes vigentes.
- Ventas › Reportes › *Comisiones*: tabla dinámica y gráfico por vendedor y mes. Cada vendedor ve solo lo suyo.

## Permisos

| Grupo | Reglas de comisión por categoría |
|---|---|
| Ventas: Usuario (vendedor) | **Solo lectura** (necesaria para calcular su comisión al confirmar) |
| Ventas: Administrador | Lectura y escritura |

## Pruebas

```bash
./odoo test prueba-tecnica -d prueba_limpia -m sale_commission
```

Resultado: **8 pruebas, 0 fallos, 0 errores**. Las pruebas crean y confirman los pedidos **con el
usuario vendedor** (`with_user`), no como administrador.

| Prueba | Qué demuestra |
|---|---|
| `test_commission_on_confirm` | Al confirmar se fija el porcentaje del vendedor y se calcula la comisión |
| `test_salesman_report_only_own` | En el reporte, cada vendedor ve solo sus comisiones |
| `test_commission_by_category` | La regla de la categoría reemplaza al porcentaje del vendedor |
| `test_subcategory_uses_most_specific_rule` | Gana la regla de la categoría más específica |
| `test_t200_salesman_can_confirm_own_order` | **T-200:** un vendedor confirma su propio pedido |
| `test_t200_manager_can_still_confirm` | **T-200:** el gerente sigue confirmando igual |
| `test_t200_manager_confirming_keeps_salesman_percent` | **T-200:** si el gerente confirma un pedido ajeno, se usa el porcentaje del vendedor |
| `test_t200_salesman_cannot_edit_rules` | **T-200:** el vendedor **no** puede modificar las reglas (no se repartieron permisos de más) |

## Prueba técnica — ejercicio 3 (ticket T-200)

- **Tramos completados:** A y B. Todo el detalle (reproducción, causa raíz, corrección, prueba
  antes y después, contención, commit culpable, despliegue y mensaje al cliente) está en
  [INCIDENT.md](INCIDENT.md).
- **Rama y pull request:** `hotfix/T-200`, PR: <enlace>.
- **Resumen:** desde la versión 1.1.0, confirmar un pedido lee `sale.commission.rule`, y el
  vendedor no tenía permiso de lectura sobre ese modelo. Se agregó un permiso de **solo lectura**
  para el grupo de vendedores y se corrigió que, sin regla de categoría, se usaba el porcentaje de
  quien confirma en lugar del vendedor del pedido.

### Supuestos

- El despliegue de las 12:00 corresponde al commit `3f4d73f`.
- La corrección del porcentaje (vendedor del pedido en lugar de quien confirma) va en el mismo
  hotfix porque la contención de la tarde, con el gerente confirmando los pedidos de todos,
  estaba generando datos incorrectos.

### Limitaciones conocidas

- Las comisiones de los pedidos que el gerente confirmó esta tarde siguen sin corregir (tramo C,
  no realizado en esta entrega).
- `action_recompute_commissions` repite la lógica de cálculo con otra regla (categoría exacta, sin
  categorías padre ni compañía). Se reporta, pero no se corrige en este hotfix, para mantener el
  cambio mínimo.
- El botón *Recalcular comisiones* no tiene restricción de grupo. Queda como pregunta para el
  cliente: ¿debería usarlo solo el gerente?
