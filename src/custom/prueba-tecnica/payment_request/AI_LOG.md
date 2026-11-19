# AI_LOG — payment_request

## Herramientas

- Claude (Claude Code, modelo Opus 5.5).

## Cómo se hizo este módulo (importante)

**Este módulo lo desarrolló íntegramente la IA, a pedido mío.** Me quedaban unos 20 minutos de
plazo y le pedí a Claude que hiciera el ejercicio 4 completo por su cuenta, a diferencia de los
ejercicios 1, 2 y 3, donde la IA me daba una guía y el código lo transcribía y verificaba yo.

En este módulo la IA:

- escribió todos los archivos (modelos, seguridad, vistas, asistentes, reporte, pruebas y
  documentación: este README, ARCHITECTURE.md y este AI_LOG);
- ejecutó las pruebas tras cada tramo y corrigió lo que falló;
- hizo la prueba manual de concurrencia en mi base `dev`;
- hizo los commits locales por tramo (`[FEAT]`, `[TEST]`, `[IMP]`), con la línea
  `Co-Authored-By: Claude`.

Yo decidí cambiar el plan, revisé el resultado y hice el push y la fusión.

## Prompts clave

1. *"Este ejercicio será desarrollado 100 % por ti; que esté claramente explicado en el AI_LOG.md."*
   Antes, en la misma conversación, la IA había preparado una guía para este ejercicio con el
   diseño, las alternativas y el código de los tres tramos; la usó como base.
2. La lectura del correo de la cliente "como consultor" (qué implica y qué no dice) es de esa guía;
   de ahí salen los supuestos y las preguntas del README.

## Lo que la IA hizo mal (y cómo se detectó)

- **La secuencia:** usó el prefijo `SP/%(year)s/` con rangos de fechas por año. La prueba
  `test_sequence_uses_request_year` falló (una solicitud del 31-12-2025 salía `SP/2026/…`). Revisó
  `ir_sequence.py` de Odoo 17: con rangos de fechas, `%(year)s` toma el año actual y el del rango es
  `%(range_year)s`. Corregido antes del primer commit.
- **La prueba manual de concurrencia:** el primer intento falló por el script de la IA, no por el
  módulo: `odoo shell` corre como el superusuario técnico, que no es el aprobador asignado. Repitió
  la prueba con el usuario aprobador.
- **Un caso que las pruebas no cubrían:** al preparar esa prueba manual con un usuario sin correo
  electrónico, enviar la solicitud falló (*"configure la dirección de correo electrónico del
  remitente"*), porque la actividad del aprobador genera una notificación. Las pruebas automáticas no
  lo vieron porque `new_test_user` les pone correo a los usuarios. Quedó documentado como limitación.

## Lo que escribiste tú sin IA

- Nada del código ni de la documentación de este módulo. Mi parte fue decidir delegarlo, revisar el
  resultado y publicarlo.
