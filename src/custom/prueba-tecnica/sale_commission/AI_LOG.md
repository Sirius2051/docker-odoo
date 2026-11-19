# AI_LOG — sale_commission

## Herramientas

- Claude (Claude Code, modelo Opus 5.5).

## Prompts clave

1. Le pasé el PDF y le pedí una guía para el ticket T-200: el método para reproducir el error, las
   alternativas de corrección con sus ventajas y desventajas, y el código para transcribirlo yo.
   - La guía dejaba la causa raíz escondida en un bloque plegado, con pistas antes. Reproduje el
     error con un usuario vendedor en la interfaz antes de leerla.
2. Le pedí comparar las alternativas de corrección: permiso de lectura, `sudo()` justificado,
   darle al vendedor el grupo de gerente, atrapar el error o revertir el despliegue.
   - Elegí el permiso de solo lectura: es declarativo, queda en el CSV donde se audita la seguridad
     y no le da al vendedor poder de cambiar nada (lo comprueba una prueba).
3. Le pedí revisar el commit del mediodía (`3f4d73f`) para entender por qué las pruebas no
   detectaron el error.
   - Señaló que el mismo commit había quitado `with_user` del helper de las pruebas y le había dado
     al administrador el mismo porcentaje que al vendedor, lo que también escondía un segundo error
     (`self.env.user` en lugar del vendedor del pedido).
4. Con el error reproducido, le pedí buscar en el log del contenedor el detalle técnico.
   - Odoo no guarda *traceback* para los errores de permisos; la evidencia del log es la línea
     `Access Denied by ACLs for operation: read`, y el *traceback* completo salió de las pruebas.

## Lo que la IA hizo mal

- La guía decía que buscara el *traceback* del error en el log del servidor (`./odoo logs | grep
  AccessError`). No hay: Odoo registra los errores de permisos como una advertencia de una línea,
  sin *traceback*. El *traceback* con la línea exacta (`sale_order_line.py`, línea 28) lo obtuve
  de la ejecución de las pruebas antes de corregir.

## Lo que escribiste tú sin IA

- El código de las pruebas y de las dos correcciones viene de la guía generada por la IA. Mi
  trabajo fue transcribirlo, entender la causa y verificar cada paso.
- La reproducción en la interfaz: crear el usuario vendedor, confirmar un pedido con él (error) y
  con el gerente (funciona).
- Correr las pruebas **antes** de corregir (8 pruebas: 1 fallo y 5 errores) y **después** (0 y 0),
  con un commit para las pruebas y uno por cada corrección.
- El mensaje al cliente.
