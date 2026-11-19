import csv
import sys

CONFIRMED_SINCE = "2026-11-13 16:00:00"

lines = env["sale.order.line"]._get_commission_mismatches(CONFIRMED_SINCE)

writer = csv.writer(sys.stdout)
writer.writerow([
    "pedido", "fecha_confirmacion", "vendedor", "confirmado_por", "linea_id", "producto",
    "porcentaje_guardado", "porcentaje_correcto", "comision_guardada", "comision_correcta", "diferencia",
])
total_difference = 0.0
for line in lines:
    expected_percent = line._get_commission_percent()
    expected_amount = line.currency_id.round(line.price_subtotal * expected_percent / 100.0)
    difference = expected_amount - line.commission_amount
    total_difference += difference
    writer.writerow([
        line.order_id.name,
        line.order_id.date_order,
        line.order_id.user_id.login,
        line.order_id.write_uid.login,
        line.id,
        line.product_id.display_name,
        line.commission_percent,
        expected_percent,
        line.commission_amount,
        expected_amount,
        round(difference, 2),
    ])

print(
    f"# Líneas afectadas: {len(lines)} · diferencia total de comisiones: {total_difference:.2f}",
    file=sys.stderr,
)
env.cr.rollback()