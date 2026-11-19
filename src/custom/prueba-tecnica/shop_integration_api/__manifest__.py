{
    "name": "API para la tienda en línea",
    "summary": "Catálogo de productos con existencias para la tienda en línea",
    "version": "17.0.2.0.0",
    "category": "Sales",
    "author": "José Avilé",
    "license": "LGPL-3",
    "depends": ["sale_stock"],
    "data": [
        "security/ir.model.access.csv",
        "views/shop_api_log_views.xml",
    ],
    "installable": True,
    "application": False,
}