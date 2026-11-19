{
    "name": "API para la tienda en línea",
    "summary": "Catálogo de productos con existencias para la tienda en línea",
    "version": "17.0.3.0.0",
    "category": "Sales",
    "author": "José Avilé",
    "license": "LGPL-3",
    "depends": ["sale_stock"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_cron_data.xml",
        "views/shop_api_log_views.xml",
    ],
    "installable": True,
    "application": False,
}