# AI_LOG — shop_integration_api

## Herramientas

- Claude (Claude Code, modelo Opus 5.5).

## Prompts clave

1. Le pasé el PDF de la prueba y le pedí una guía paso a paso con el diseño del endpoint,
   alternativas con ventajas y desventajas, y el código de cada archivo (controlador y pruebas)
   para transcribirlo yo, sin que la IA armara el proyecto ni hiciera los commits.
   - Me explicó `type="http"` frente a `type="json"` (JSON-RPC siempre responde 200), variantes
     frente a plantillas, y cómo devolver 400 en lugar de 500 con una fecha mala.
   - Me advirtió que Python 3.10 (el de la imagen de Odoo 17) no acepta la `Z` final en
     `datetime.fromisoformat`; dejé el reemplazo de `Z` por `+00:00`.
2. Le pedí verificar las firmas de las APIs de Odoo que usaba (`make_json_response`,
   `HttpCase.authenticate`, `url_open`) contra el código fuente de Odoo 17.
3. Le pedí revisar mi repositorio antes de empezar, para comprobar que el entorno estuviera bien.
   - Encontró que mi fork solo tenía la rama `master-multi`, sin los módulos de partida: GitHub,
     al hacer fork, copia por defecto solo la rama principal. Traje `master-multi-prueba-tecnica`
     desde el repositorio original.
4. Con la ruta dando 404, le pedí revisar el log del contenedor.

## Lo que la IA hizo mal

- **Configuración del entorno:** la guía suponía un `.env` con `ODOO_VERSION` (lo que dice el PDF),
  pero este repositorio se configura con `instances.json`. Me di cuenta al no encontrar
  `.env_example`.
- **`instances.json`:** me dijo que dejara las bases de datos de ejemplo que no usaba. El
  validador (`./odoo validate-instances`) las rechazó: *"Puerto duplicado: 5432 usado por la
  base 'v17' y 'base de datos 'v16''"*. Dejé solo `v17`.
- **Ruta con 404:** la guía instalaba el módulo con un segundo proceso de Odoo
  (`docker exec … odoo -i`) y no decía que el servidor que ya corría no ve lo instalado hasta
  reiniciarlo. La ruta respondía 404 y el log tenía `KeyError: 'sale.order'`. Lo resolví con
  `./odoo restart`.

## Lo que escribiste tú sin IA

- El código del controlador y de las pruebas viene de la guía generada por la IA. Mi trabajo fue
  transcribirlo archivo por archivo, entender cada decisión (por qué `type="http"`, por qué
  variantes, por qué 400 y no 500) y verificarlo.
- Montar el entorno desde cero (fork, `instances.json`, build, base de datos) y resolver sus errores.
- Diagnosticar el 404 de la ruta y comprobar el resultado de las pruebas (8 pruebas, 98 % de cobertura).
- La prueba manual del endpoint en el navegador.
- Los commits y la organización en ramas.
