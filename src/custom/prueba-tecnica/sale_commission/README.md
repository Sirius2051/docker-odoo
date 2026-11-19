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
- El botón *Recalcular comisiones* del pedido vuelve a aplicar los porcentajes vigentes, con la misma regla que la confirmación.
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

Resultado: **11 pruebas, 0 fallos, 0 errores**. Las pruebas crean y confirman los pedidos **con el
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
| `test_t200_mismatches_lists_only_wrong_lines` | **T-200, tramo C:** la detección lista solo las líneas con el porcentaje equivocado |
| `test_t200_mismatches_ignores_older_orders` | **T-200, tramo C:** la detección ignora los pedidos anteriores a la fecha |
| `test_recompute_uses_same_rule_as_confirm` | El recálculo usa la misma regla que la confirmación (incluida la categoría padre) |

## Prueba técnica — ejercicio 3 (ticket T-200)

- **Tramos completados:** A, B y C. Todo el detalle (reproducción, causa raíz, corrección, prueba
  antes y después, contención, commit culpable, despliegue, mensaje al cliente, impacto en los
  datos, plan de corrección y prevención) está en [INCIDENT.md](INCIDENT.md).
- **Ramas:** `hotfix/T-200` (tramos A y B, PR [#1](https://github.com/Sirius2051/docker-odoo/pull/1), fusionado) y `fix/T-200-datos` (tramo C).
- **Script de solo lectura:** `scripts/t200_affected_lines.py` lista las líneas con la comisión
  mal asignada (CSV) sin modificar nada.
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

- Las comisiones mal asignadas en producción **no se corrigen automáticamente**: el script las
  lista y el plan de corrección (en INCIDENT.md) requiere la revisión del cliente antes de tocarlas.
- El script compara con las reglas vigentes al ejecutarse: si una regla cambió después del
  incidente, conviene revisar el listado.
- El botón *Recalcular comisiones* sigue sin restricción de grupo, a la espera de la respuesta del
  cliente.
- Al instalar, Odoo muestra avisos de `docutils`: interpreta este README en Markdown como
  reStructuredText para la descripción del módulo. No afecta al funcionamiento.
