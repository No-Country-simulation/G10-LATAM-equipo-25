# Guía de la demostración

Guion paso a paso para presentar CommunityLab con **Gemini real** y mostrar cada punto del checklist del hackathon y nuestro reto: el **Motor de FAQ dinámico y contenido educativo**. Toma entre 8 y 10 minutos.

**La idea:** en vivo se procesa solo el ejemplo oficial del briefing (2 llamadas a Gemini, unos 15 segundos). El resto se generó con Gemini el día anterior y se carga sin gastar cuota. Si Gemini falla en vivo, se pasa al plan B sin que se note.

---

## El día anterior (15 minutos)

1. En el `.env` del backend: `LLM_PROVIDER=gemini` y `GEMINI_MODEL=gemini-3.1-flash-lite` (el que respondió mejor en las pruebas).
2. Generar con Gemini las respuestas de todos los ejemplos. Esto gasta 14 llamadas, tarda unos 2 minutos y además **llena el historial de dudas frecuentes**:

   ```bash
   python -m communitylab_backend.tools.process_batch ejemplos --out salidas/respuestas_gemini
   ```

   Si algún lote sale con `[ERROR] … Gemini no está disponible`, es saturación de Google: esperar un minuto y repetir solo ese archivo, por ejemplo `python -m communitylab_backend.tools.process_batch ejemplos/02_dudas_machine_learning.json --out salidas/respuestas_gemini`.

3. Revisar en `salidas/respuestas_gemini/` que estén los 7 archivos. Ya están todos generados con Gemini, y el historial ya tiene las dudas de los lotes 01 a 05 y 07: en *Dudas frecuentes* se ve **LangGraph con 3 dudas en 2 lotes y sin FAQ oficial**. Solo hace falta repetir este paso si se borra el historial o se quieren respuestas nuevas.
4. Ensayar una vez el guion completo.

## Antes de empezar (10 minutos antes)

1. Encender el motor y el panel (pasos 3.5 y 4 de [instalacion.md](instalacion.md), o el comando rápido para Windows de su sección 7).

2. Comprobar en el navegador:
   - `http://localhost:8000/docs` abre la documentación de la API.
   - `http://localhost:8501` abre el panel **sin** el aviso "Backend sin conexión" ni el de "Modo local".
   - Si no se ve el menú de la izquierda, pulsar el botón azul **»** arriba a la izquierda.
3. En el panel, *Procesar lote* → **Limpiar la sesión** si quedó algo de un ensayo. Si el navegador se recarga en medio de la demo, *Procesar lote* ofrece **Recuperar sesión**.
4. Tener a mano la carpeta `salidas\respuestas_gemini\` del backend, para el plan B.

---

## Guion

### 1. El problema (1 minuto)

Las comunidades generan a diario dudas, logros y testimonios que se pierden en Discord o Slack. Las mismas dudas se repiten semana a semana y nadie las convierte en material. CommunityLab las detecta, las agrupa por tema y las transforma en **tutoriales rápidos, tips de la semana y temas de documentación**, siempre con revisión humana.

Mostrar el diagrama de arquitectura y el flujo LangGraph del `README.md`.

### 2. El ejemplo del briefing, en vivo con Gemini (2 minutos)

- Panel → **Procesar lote** → *Lotes de ejemplo* → `01 briefing semana04` → "Ver los 2 mensajes del lote": es el JSON exacto del briefing.
- Clic en **Procesar este lote** (unos 15 segundos).
- Señalar el mensaje verde: **dos rutas a la vez** (Historia de éxito + FAQ), los activos generados y 1 persona que requiere apoyo.
- Frase clave: "el logro de Mariana no tapa la duda de Lucas: el motor atiende las dos en paralelo, con dos consultas a Gemini".

> **Plan B:** si aparece "Gemini no está disponible", es saturación de Google. Ir a *Respuesta guardada* y cargar `01_briefing_semana04.json` de `salidas\respuestas_gemini\`. Es una respuesta real de Gemini y el resto del guion funciona igual.

> Checklist: *ingesta funcional*, *sentimiento y temas con LLM*.

### 3. Más lotes y lo que ve el equipo de comunidad (2 minutos)

- *Procesar lote* → **Respuesta guardada** → seleccionar los demás archivos de `salidas\respuestas_gemini\` → **Cargar respuestas**. No gasta cuota.
- **Resumen**:
  - Tabla **Decisiones del motor por lote**: logro y duda → Historia de éxito + FAQ; dudas → FAQ; ni logros ni dudas → Resumen de comunidad.
  - El sentimiento de cada mensaje, los **mejores momentos** (puntaje de relevancia) y **Miembros que requieren apoyo**.
- **Mensajes procesados** → *Mostrar* → **Requieren apoyo** y **Descartados**. Señalar que los correos y teléfonos aparecen como `[EMAIL]` y `[TELEFONO]`.

> Checklist: *orquestación con bifurcación de condiciones*, *mínimo 3 ejemplos*. Briefing: *quién logró un hito*, *quién necesita apoyo*, *puntaje de relevancia*.

### 4. Motor de FAQ: el corazón del reto (3 minutos)

Ir a **Motor de FAQ** (segundo en el menú). Es la pantalla que responde a "¿dónde se ve la transformación?".

- Arriba, la franja del flujo: *dudas de la comunidad → agrupadas por tema y frecuencia → tutorial rápido · tip de la semana · tema de documentación → revisión humana → base de FAQs que crece*.
- Las métricas: dudas registradas, temas, contenidos generados, temas **sin respuesta oficial** y FAQs aprendidas.
- Una tarjeta por tema, ordenadas por frecuencia. A la izquierda **lo que pregunta la comunidad** (sus mensajes reales, sin datos personales) y, después de la flecha, **lo que generó el motor**: el tutorial rápido, el tip de la semana (como mensaje fijado en Discord) y la propuesta de documentación.
- Señalar **LangGraph: 3 dudas en 2 lotes, "Sin respuesta oficial"**. Leer el tutorial que propuso Gemini y pulsar **Aprobar y agregar a la base**: la tarjeta cambia a "FAQ oficial", la métrica *FAQs aprendidas* sube a 1 y el tema queda resuelto en el ranking al instante.
- Comparar con **Datos faltantes** o **Sobreajuste**: el tutorial dice "Respaldado por la FAQ oficial" con su número.
- Opcional: **Revisar** en cualquier pieza abre ese borrador en *Curaduría de activos* para editarlo.
- Prueba del aprendizaje: **Base de conocimiento → Buscar en las FAQs** → `cómo hago un router en LangGraph`. Antes no encontraba nada; ahora devuelve la FAQ nueva.
- Frase clave: "las dudas frecuentes se convierten en contenido, y lo que se aprueba entra a la base: el motor aprende de su comunidad".

> Checklist: *al menos 2 formatos* (hay 7). Reto del equipo: *dudas frecuentes → tutoriales rápidos, tips de la semana y temas de documentación*.

### 5. Curaduría humana y almacenamiento (1 minuto)

- Editar un borrador (aparece la marca ✎), **Aprobarlo** (se abre solo el siguiente) y **Rechazar** otro. Mostrar la barra de progreso.
- **Guardar curaduría en el backend**: aparece la ruta del paquete `...-curaduria.json`. Opcional: descargar los aprobados en Markdown.
- **Configuración**: dónde se guardan los paquetes (OCI Object Storage o carpeta local) y qué modelo usa el motor.
- Si OCI está activo, mostrar el bucket en la consola de OCI.

> Checklist: *integración con OCI Object Storage*.

### 6. La salida con el formato del briefing (30 segundos)

Ir a **Esta semana** y elegir el lote del briefing: muestra el resultado con la misma estructura del ejemplo oficial (resumen de la comunidad, post de LinkedIn, destacado de newsletter, sugerencia de FAQ, caso de éxito, contenido educativo por tema y almacenamiento) y permite descargarlo como JSON.

También se puede ver en `http://localhost:8000/docs` → `POST /api/v1/activity/process` → *Try it out* con `ejemplos/01_briefing_semana04.json` (gasta 2 llamadas). También se puede abrir `salidas/respuestas_gemini/01_briefing_semana04.json`, que no gasta nada. Al final está `formato_briefing`, con la estructura exacta del ejemplo oficial más el bloque `contenido_educativo` (tutorial, tip y documentación de cada tema).

### 7. Cierre (30 segundos)

- Repositorio documentado: README con diagramas, guía paso a paso y `docs/`.
- Siguientes pasos: OCI Vault, OCI Vector Store y despliegue en OCI Compute Ampere A1.

---

## Después de la demo

**Aprobar y agregar a la base** escribe en `data/motor_educativo.db`. Antes de escribir, el motor guarda una copia en `data/respaldos/`. Para dejar la base como estaba, copiar esa copia encima (desde la carpeta del backend):

```powershell
Copy-Item "data\respaldos\<archivo-de-respaldo>.db" "data\motor_educativo.db"
```

El historial de dudas frecuentes está en `data/historial_dudas.db`. Para empezar de cero, borrar ese archivo con el backend apagado.

## Si se acaba la cuota de Gemini

Cambiar en el `.env` del backend `LLM_PROVIDER=gemini` por `LLM_PROVIDER=mock` y reiniciar. El flujo completo funciona igual con reglas locales: los textos son más simples, pero se ven todas las rutas, temas, formatos y el ranking. Las respuestas de `salidas/respuestas_gemini/` se pueden seguir cargando para mostrar la redacción real de Gemini.

## Alternativa sin panel

Para mostrar el motor solo con la terminal:

```bash
python -m communitylab_backend.tools.process_batch ejemplos/01_briefing_semana04.json
```

Imprime las rutas activas, los activos generados, las citas de FAQ y cuántas personas requieren apoyo. La respuesta completa queda en `salidas/respuestas/`.
