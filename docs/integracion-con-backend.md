# Integración del panel con el backend

Este documento registra los cambios que se hicieron al panel de curaduría (`communitylab_ui`) para conectarlo al backend real y cumplir los requisitos del hackathon: qué se cambió, por qué, y qué se mantuvo del trabajo original.

Fecha: 19 de octubre de 2026. El panel sigue siendo un **proyecto aparte** en la rama `feature/ui-curaduria`: no se fusiona con el backend, solo lo llama por HTTP.

---

## 1. Punto de partida

El panel original (Sprint 1) ya tenía las cuatro vistas, el diseño Material, la gestión de secretos y un **contrato de datos** escrito a mano (`data/resultados_ejemplo.json`). Su README dejaba planeado el siguiente paso:

> Conectar el backend (Sprint 2): se toca una sola función, `cargar_resultados()`.

Esa idea se respetó, con un ajuste: en vez de reemplazar una función, la conexión quedó repartida en tres módulos pequeños dentro de `core/`, uno por responsabilidad.

## 2. Cambios realizados

### Cambio 1 · Conexión con el backend (`core/backend.py`, nuevo)

- **Qué:** único módulo que hace llamadas HTTP: `procesar_lote`, `guardar_curaduria` y `estado`. La dirección se lee de `BACKEND_URL` (por defecto `http://localhost:8000`).
- **Por qué:** si cambia una ruta o el puerto del backend, se toca un solo archivo. Los errores de conexión se traducen a mensajes claros ("Revisa que el backend esté encendido").

### Cambio 2 · Adaptador de datos (`core/adaptador.py`, nuevo)

- **Qué:** convierte la respuesta del backend (en inglés: `community_summary`, `generated_assets`, `evidence`) a la estructura en español que usan las vistas, y junta varios lotes procesados en una sola vista.
- **Por qué:** cumple la regla original del equipo ("si el backend cambia un campo, se ajusta en un solo lugar"), que antes recaía en `resultados_ejemplo.json`. Las vistas siguen leyendo nombres como `activos_distribucion_generados` o `interacciones_muestra`.
- **Diferencias con el contrato original:**

  | Campo del contrato original | Ahora | Motivo |
  |---|---|---|
  | `total_descartadas`, `miembros_que_requieren_apoyo` | Se retiraron de la vista | El motor todavía no produce estos datos; mostrarlos sería inventarlos |
  | `distribucion_sentimiento` por mensaje | Por mensaje, según el sentimiento de su lote | El análisis del backend es por lote |
  | `temas_principales.menciones` | Cantidad de lotes en que aparece cada tema | Mismo motivo |
  | `score_relevancia` de cada activo | Citas de la FAQ oficial que lo respaldan | Es el respaldo real que da el motor |
  | `almacenamiento_oci` simulado | Configuración real del backend (`GET /api/v1/status`) y rutas de los paquetes guardados | Ya no es simulado |
  | — | Nuevo tipo de activo `caso_exito` | La ruta de historia de éxito del backend lo genera |

### Cambio 3 · Ingesta (`core/ingesta.py`, nuevo)

- **Qué:** lee JSON con el formato del briefing, CSV (`autor,canal,tipo,texto`) y las respuestas guardadas del backend (`salidas/respuestas/`).
- **Por qué:** el checklist pide ingesta funcional por JSON o CSV. Las respuestas guardadas permiten mostrar el panel aunque el backend no esté encendido (plan B para la demo).

### Cambio 4 · Nueva vista "Procesar lote" (`ui/app.py`)

- **Qué:** primera sección del menú, con cuatro pestañas: *Lotes de ejemplo* (uno o los 5 de la demo), *Subir archivo*, *Escribir mensajes* y *Respuesta guardada*.
- **Por qué:** es el disparador del flujo. Antes el panel leía siempre el mismo archivo fijo.

### Cambio 5 · Vistas existentes conectadas a datos reales (`ui/app.py`)

| Vista | Qué cambió |
|---|---|
| Resumen | Métricas reales (interacciones, lotes, activos, citas FAQ). Nueva tabla **Decisiones del motor por lote**, que muestra la bifurcación de condiciones pedida en el briefing. Hallazgos del motor por lote |
| Mensajes procesados | Muestra el lote y la ruta de cada mensaje. Se mantuvo el filtro por tipo |
| Curaduría | El texto editado se conserva al aprobar. "Ver de dónde salió" muestra también la **FAQ oficial** que respalda el activo. Nuevo filtro por tipo. Nuevo botón **Guardar curaduría en el backend**. La descarga de aprobados incluye las ediciones |
| Configuración | Almacenamiento y motor reales en lugar de datos simulados |

El aviso fijo "Versión de prueba (Sprint 1)" se reemplazó por un aviso que cambia según el estado: backend sin conexión o motor en modo local.

### Cambio 6 · Bloques visuales (`ui/mui_blocks.py`, `ui/theme.py`)

- `tarjeta_almacenamiento` y `tarjeta_origen` se reescribieron para mostrar la configuración real.
- Nuevo bloque `tabla_corridas` (decisiones del motor por lote), con el mismo estilo que `tabla_grupos`.
- `lista_mensajes`, `cabecera_activo`, `tabla_grupos`, `panel_temas` y `barra_apilada_sentimiento` se ajustaron para aceptar los datos reales; los campos que el motor no produce (fecha, reacciones, relevancia) se ocultan en vez de fallar.
- `theme.py`: color para el sentimiento `mixto`, tipo de activo `caso_exito` y la sección "Procesar lote".
- **Se mantuvieron sin cambios** la paleta, el CSS, el criterio de accesibilidad de colores y las soluciones a las limitaciones de `streamlit-mui-elements` documentadas al inicio de `mui_blocks.py`.

### Cambio 7 · Archivos de soporte

| Archivo | Cambio | Motivo |
|---|---|---|
| `data/resultados_ejemplo.json` | Eliminado | Era un ejemplo escrito a mano para construir la interfaz antes del motor. Su papel de contrato ahora lo cumple `core/adaptador.py`. Sigue disponible en el historial de Git |
| `data/lotes_ejemplo/` | Nuevo | Copia de los 5 lotes de `ejemplos/` del backend |
| `.env.example` | Se agregó `BACKEND_URL` | Dirección del backend |
| `requirements.txt` | Se agregó `requests`; se quitó el bloque comentado "Sprint 2" | El panel llama al backend por HTTP. Las dependencias del motor viven en el `requirements.txt` del backend |
| `core/secretos.py` | `BACKEND_URL` agregado al catálogo (no obligatorio) | Aparece en el diagnóstico de Configuración |
| `README.md` | Actualizado | Refleja el panel conectado |

## 3. Verificación realizada

Con el backend encendido en modo local:

- Procesamiento de un lote y de los 5 lotes de ejemplo: tres rutas distintas, con citas de FAQ en los lotes de dudas.
- Todas las vistas se dibujan con los datos de las corridas.
- Aprobar y rechazar activos, editar un texto y guardar la curaduría: el backend guardó `<request_id>-curaduria.json` con el texto editado.
- Con el backend apagado: aviso en pantalla y carga de respuestas guardadas.
- Limpiar la sesión borra lotes, decisiones y ediciones.

## 4. Mejoras posteriores: varias rutas y análisis por mensaje

El backend sumó tres mejoras (detalle en `docs/integracion-ramas.md` del backend, sección "Mejoras posteriores a la integración"): un lote puede activar **varias rutas** a la vez, cada mensaje trae su **propio análisis** con un **puntaje de relevancia**, y la respuesta incluye una copia con el formato del briefing. El panel se actualizó para mostrarlas.

### Cambio 8 · Adaptador (`core/adaptador.py`)

- **Qué:** lee los campos nuevos del backend y los traduce a la estructura de las vistas:

  | Campo del backend | Qué muestra el panel |
  |---|---|
  | `routing.flows` y `routing.reasons` | Todas las rutas activas del lote y por qué (antes, solo una) |
  | `generated_assets[].flow` | La ruta de cada activo en Curaduría, y solo los mensajes de esa ruta en "Ver de dónde salió" |
  | `interaction_analysis` | Texto de cada mensaje **con los datos personales ya ocultos** (`[EMAIL]`, `[TELEFONO]`), sentimiento, categoría (Logro, Duda, Pide apoyo, Comentario) y relevancia **reales** |
  | `highlights` | Lista **Mejores momentos** |
  | `interaction_analysis[].needs_support` | Métrica y lista **Requieren apoyo** (los mismos mensajes de `members_needing_support`) |
  | `discarded` | Mensajes marcados "Descartado: no entró a ningún activo" |

- Se agregaron dos ayudas: `rutas_de(respuesta)` y `resumen_respuesta(respuesta)` (la frase verde que aparece al procesar un lote). Así `ui/app.py` ya no lee esos campos del backend directamente.
- El análisis de cada mensaje se empareja por id y, si los ids no coinciden (respuestas guardadas en `salidas/respuestas/`, donde el backend generó los ids), por posición.
- **Compatibilidad:** las respuestas guardadas antes de estas mejoras siguen funcionando: se usa la ruta principal (`selected_flow`) y el sentimiento del lote, como antes.
- **Por qué:** se mantiene la regla del equipo: si cambia un campo del backend, solo se toca `adaptador.py`.
- Esto resuelve dos diferencias con el contrato original (tabla del cambio 2): los miembros que requieren apoyo y los descartados vuelven a mostrarse, porque ahora el motor sí los produce, y `distribucion_sentimiento` ya es por mensaje.

### Cambio 9 · Vistas (`ui/app.py`, `ui/mui_blocks.py`)

| Vista | Qué cambió |
|---|---|
| Procesar lote | El aviso verde muestra todas las rutas activas, los activos y cuántas personas requieren apoyo |
| Resumen | Nueva métrica **Requieren apoyo** (con la cantidad de descartados). La barra de sentimiento cuenta el sentimiento real de cada mensaje. La tabla **Decisiones del motor por lote** muestra las *Rutas activas* y suma las columnas *Apoyo* y *Descartados*. Nuevas listas **Mejores momentos** y **Miembros que requieren apoyo**. Los hallazgos por lote explican por qué se eligió cada ruta |
| Mensajes procesados | Cada mensaje muestra su categoría, su relevancia y las marcas "Mejor momento" y "Requiere apoyo". Nuevo filtro por categoría y selector *Todos / Requieren apoyo / Descartados* |
| Curaduría | Cada activo indica la ruta que lo encargó (por ejemplo, en el lote del briefing hay 2 activos de Historia de éxito y 2 de FAQ) |

En `mui_blocks.py`: `lista_mensajes` recibe un parámetro `clave` para poder dibujar varias listas en la misma vista, y `tabla_corridas` tiene las columnas nuevas. Paleta, CSS y estilos no cambiaron.

### Verificación

- El adaptador se probó con las 5 respuestas regeneradas en `salidas/respuestas/` del backend y con una respuesta en el formato anterior (sin los campos nuevos).
- Resumen, Mensajes procesados (incluido el filtro *Descartados*) y Curaduría se dibujaron sin errores con esas respuestas (prueba con `streamlit.testing`).
- Con el backend encendido, el cliente del panel procesó los 5 ejemplos: el lote del briefing trae las dos rutas y los 4 activos, cada uno con sus mensajes de origen.

## 5. Secretos desde OCI Vault

### Cambio 10 · Lectura de OCI Vault (`core/secretos.py`)

- **Qué:** `_leer_de_vault()` ya no es un esqueleto: pide el secreto a OCI Vault por su nombre del catálogo (`get_secret_bundle_by_name`), decodifica el base64 y devuelve el texto. Se activa con `FUENTE_SECRETOS=vault` (solo Vault) o `auto` (Vault y, si falla, `.env`). Con `env`, el valor por defecto, nada cambia.
- **Cómo se conecta:** `OCI_AUTH=instance_principal` en OCI Compute (el servidor se identifica sin claves guardadas) o `OCI_AUTH=config` con `~/.oci/config` para probar desde una computadora. El Vault se indica con `OCI_VAULT_ID`; se acepta también el nombre anterior `OCI_VAULT_OCID`. Son los mismos nombres de variables y de secretos que usa el backend (`SECRET_PROVIDER=oci`).
- **Seguridad:** nunca registra el valor. Si falta el SDK, el Vault, el permiso o el secreto, escribe un aviso con el nombre del secreto (no su valor ni el texto del error de OCI) y devuelve `None`, para que `auto` siga con el `.env` y `vault` muestre un error claro. El valor queda en memoria (la caché de `obtener_secreto`); para usar una versión nueva del secreto hay que reiniciar el panel.
- **Dependencia:** el SDK `oci` se importa solo al leer el Vault; no está en `requirements.txt` porque el modo local no lo usa (está anotado ahí cómo instalarlo).
- **Otros archivos:** `.env.example` (variables `OCI_VAULT_ID`, `OCI_AUTH`, `OCI_CONFIG_FILE`, `OCI_CONFIG_PROFILE`), el texto de la tarjeta **Secretos** en `ui/mui_blocks.py` y el README.
- **Por qué:** en producción las claves no deben vivir en un archivo del servidor. Guía completa (crear el Vault, grupo dinámico, política y rotación): `docs/secretos.md` del backend.
- **Verificación:** se probó con un cliente falso (sin red): lectura y decodificación, secreto inexistente, permiso denegado, contenido inválido, `auto` cayendo al `.env` y el mensaje de `vault` sin SDK. También que con un `~/.oci/config` de prueba se crea el cliente oficial. No se probó contra una cuenta real de OCI.

## 6. Curaduría como bandeja de trabajo

Al recorrer el panel con los 5 ejemplos se vio que la curaduría era una lista larga de cuadros de texto uno debajo de otro: con 12 borradores había que bajar mucho, no se veía cómo quedaría cada texto publicado y la fuente estaba escondida en un desplegable. Las herramientas que usan los equipos de marketing y comunidad trabajan como una **bandeja de entrada**: una lista corta a un lado y el elemento abierto al otro.

### Cambio 11 · Bandeja de curaduría (`ui/app.py`, `ui/previas.py`, `ui/theme.py`)

- **Qué:**

  | Parte | Qué hace |
  |---|---|
  | Lista (izquierda) | Una fila por borrador con un punto de color según el estado (naranja pendiente, verde aprobado, rojo rechazado), el título, el tipo, la ruta y el lote. Filtros por estado (con contadores), tipo y lote. Se desplaza dentro de su propio recuadro |
  | Decisión | **Aprobar** y **Rechazar** arriba del borrador; al decidir se abre solo el **siguiente pendiente**. Flechas ← → para recorrer la lista. Barra de progreso "N de 12 borradores revisados" |
  | Vista previa | El texto como se vería en su canal: tarjeta del feed de LinkedIn (marca dónde corta el «…ver más»), sección de la newsletter, entrada de FAQ (avisa si no tiene FAQ oficial que la respalde) o borrador de historia de éxito (recuerda pedir permiso a la persona). Debajo, el texto con botón de copiar |
  | Editar texto | Editor con contador de caracteres y el límite de cada canal (LinkedIn: 3.000 y ~210 antes de «ver más»; newsletter: 600 recomendados). Las ediciones **se conservan al cambiar de borrador** (marca ✎ en la lista) y **Restaurar** vuelve al texto del motor |
  | Fuente y FAQ | Los mensajes que originaron el borrador (autor, canal, sentimiento, categoría, relevancia, "Mejor momento", "Requiere apoyo") y las FAQs oficiales con su puntaje |
  | Cierre | Guardar la curaduría en el backend (sin cambios) y exportar los aprobados en **JSON** o en **Markdown** (para pegar en un documento o en la newsletter) |

- **Detalles técnicos:**
  - Las ediciones viven en `st.session_state.ediciones`, porque Streamlit borra el estado de un cuadro de texto cuando deja de mostrarse.
  - La lista es un `st.radio` con subtítulos (`captions`) dentro de un contenedor con `key="cl_bandeja"`; el CSS lo convierte en filas de bandeja.
  - Las vistas previas son HTML simple (sin iframes de Material UI), así cargan rápido al cambiar de borrador. Todo texto de la comunidad o del modelo se escapa antes de insertarlo, para que no pueda inyectar HTML en el panel. La vista anterior insertaba el texto de los mensajes sin escapar.
- **Adaptador:** suma `etiqueta` (nombre corto del tipo), `seccion_newsletter` (según la ruta que lo encargó), `ruta_corta`, `comunidades` y `periodos`. No cambió ningún campo que se lea del backend.
- **Por qué:** quien revisa decide más rápido y con más seguridad cuando ve el resultado final, la fuente y el respaldo en la misma pantalla, y no pierde el lugar después de cada decisión.

### Cambio 12 · Arreglos visuales del Resumen (`ui/app.py`, `ui/mui_blocks.py`)

| Antes | Ahora |
|---|---|
| La cabecera concatenaba todas las comunidades y períodos en una sola línea larga | "4 comunidades · 3 períodos" (o el nombre, si es uno solo) |
| Las 5 métricas se partían en 3 + 2 y la segunda fila quedaba corrida | Una grilla de columnas iguales: las 5 entran en una fila (era un `spacing` de MUI que agregaba margen en la segunda fila) |
| La tabla de decisiones tenía barra horizontal y títulos cortados | Encabezados y nombres de ruta cortos ("Historia de éxito + FAQ"), sin barra horizontal |
| "Mejores momentos" mostraba los 3 de cada lote: con lotes chicos, todos los mensajes | Los 5 mensajes de mayor relevancia de toda la sesión |
| "Miembros que requieren apoyo" era una tarjeta grande por persona | Una tabla compacta: persona, canal, motivo, inicio del mensaje y lote |
| Si se contraía la barra lateral, no había forma de volver a abrirla: el tema ocultaba toda la cabecera de Streamlit, y el botón para abrirla vive ahí | La cabecera sigue oculta, salvo ese botón (azul, arriba a la izquierda) |

### Verificación

Con el backend encendido y los 5 ejemplos procesados, en el navegador (1440 × 900):

- Aprobar el primer borrador abre solo el siguiente pendiente y la barra pasa a "1 de 12".
- Una edición se conserva al ir a otro borrador y volver (marca ✎, contador actualizado, "editado en el panel"); **Restaurar** vuelve al texto original y se deshabilita.
- Vista previa de LinkedIn (corte del «ver más» entre palabras), de FAQ con su respaldo oficial y pestaña de fuente con chips de relevancia.
- Resumen con las métricas en una fila, la tabla de decisiones sin barra horizontal y la tabla de apoyo.

Queda un detalle conocido: las tablas de Material UI dejan algo de espacio vacío abajo (el iframe de `streamlit-mui-elements` reserva más alto que la tabla).

### Cambio 13 · El panel ya no muestra datos personales

- **Qué:** el backend agrega a `interaction_analysis` el campo `text`, con el texto ya sanitizado (el mismo que recibe la IA). El adaptador lo usa en todas las vistas (Mensajes procesados, Mejores momentos, tabla de apoyo y la pestaña Fuente de la curaduría) en lugar del texto original del lote.
- **Por qué:** el README decía que en *Mensajes procesados* los datos personales aparecían ocultos, pero el panel mostraba el texto original: en el lote 02 se veía el correo del estudiante y en el 05 el teléfono. La IA nunca los recibió, pero el panel tampoco debe mostrarlos.
- **Compatibilidad:** con respuestas guardadas antes de este campo, el panel usa el texto del lote como antes. Los archivos de `salidas/respuestas/` del backend ya se regeneraron con el campo nuevo.
- **Verificación:** con las 5 respuestas regeneradas, ningún mensaje del panel contiene el correo ni el teléfono originales; aparecen `[EMAIL]` y `[TELEFONO]`.
- **Archivos:** `core/adaptador.py` (panel) y `application/batch.py` (backend).

### Cambio 14 · Vista «Base de conocimiento» (`ui/app.py`, `core/backend.py`, `core/adaptador.py`)

- **Qué:** una sección nueva en el menú que muestra qué hay en `motor_educativo.db` y cómo la usa el motor:
  - Cuántas FAQs oficiales, reseñas y cursos tiene, el sentimiento de las reseñas y los cursos con más reseñas.
  - **FAQs usadas en la sesión:** cuántas FAQs de la base citaron los borradores procesados. En la lista de FAQs aparecen primero, con el mismo número que se ve en la pestaña «Fuente y FAQ» de la curaduría. Es la prueba de que el motor responde con la base del equipo.
  - **Buscar en las FAQs:** el mismo buscador que usa el motor, para probar una duda en español y ver qué FAQ oficial respondería.
  - **Reseñas reales:** las reseñas de la base filtradas por curso y sentimiento, y un botón para enviarlas al motor como un lote más.
- **Por qué:** la base no se veía en ningún lado del panel y no había forma de comprobar que se estaba usando.
- **Verificación:** la vista mostró 141 FAQs, 2.918 reseñas y 30 cursos. El buscador encontró `faq-1583` para «cómo manejo los valores faltantes en mi dataset». Un lote de 8 reseñas reales de *machine-learning*, procesado en modo local, citó 3 FAQs de la base y la vista las contó como usadas.

### Cambio 15 · Agregar FAQs a la base desde el panel

- **Qué:** pestaña **Agregar FAQs** dentro de *Base de conocimiento*. Se sube un CSV (`pregunta,respuesta,curso`) o un JSON, el panel muestra una **vista previa** (qué se agregaría, qué ya existe en la base y qué filas tienen errores) y sólo al confirmar el backend guarda una copia de seguridad y agrega las FAQs nuevas. Incluye una plantilla CSV para descargar.
- **Dónde:** `core/ingesta.py` (`leer_faqs`, `PLANTILLA_FAQS`), `core/backend.py` (`importar_faqs`), `core/adaptador.py` (`resultado_importacion`) y `ui/app.py` (`agregar_faqs`). La validación la hace el backend; el panel sólo lee el archivo.
- **Verificación:** con un backend de prueba apuntando a una copia de la base: la vista previa marcó 2 FAQs nuevas, 1 repetida y 1 fila sin pregunta; al confirmar se agregaron `faq-3064` y `faq-3065` con copia de seguridad, y al volver a revisar el archivo todas figuraban como repetidas.

### Cambio 16 · Motor de FAQ dinámico en el panel

- **Qué:**
  - **Formatos nuevos** en la bandeja de curaduría: *Tutorial rápido*, *Tip de la semana* y *Tema de documentación*, cada uno con su tema (chip "Tema: …"), su vista previa (ficha de aprendizaje, mensaje fijado de Discord y propuesta de página de documentación) y sus mensajes de origen filtrados por tema.
  - **Cerrar el ciclo:** en un tutorial sin FAQ oficial aparece **Aprobar y agregar a la base**. La pregunta guardada es la duda real de la comunidad (sin datos personales) y la respuesta es el tutorial con las ediciones del panel. Al confirmar se muestra un aviso arriba de la bandeja.
  - **Vista nueva «Dudas frecuentes»:** el ranking del historial del motor (todos los lotes, no solo la sesión), con un filtro por período (todo, 30 o 7 días), métricas (dudas, temas, recurrentes, sin respuesta oficial), una tabla con barras y la lista de temas prioritarios sin respuesta oficial.
  - La tabla de **dudas recurrentes** del Resumen ahora va por tema.
- **Dónde:** `core/adaptador.py` (etiquetas y tipos nuevos, `tema` de cada activo y cada mensaje, `ranking_dudas`), `core/backend.py` (`dudas_frecuentes`), `ui/previas.py`, `ui/theme.py` (colores, sección nueva y estilos del tip), `ui/mui_blocks.py` (íconos y chip de tema) y `ui/app.py`.
- **Verificación:** en el navegador, contra un backend de prueba con una copia de la base: 22 borradores de los 6 ejemplos con los tres formatos por tema; «Aprobar y agregar a la base» en el tutorial de LangGraph creó `faq-3064` en la copia; «Dudas frecuentes» mostró 12 dudas en 4 temas y marcó LangGraph como prioridad sin respuesta oficial.

### Cambio 17 · La transformación en una sola pantalla, formato del briefing y sesión recuperable

- **Vista «Motor de FAQ»** (segunda en el menú; reemplaza a «Dudas frecuentes» e incluye su ranking en un desplegable): muestra el corazón del proyecto. Arriba, la franja del flujo (dudas → temas → tutorial · tip · documentación → revisión humana → base que crece) y las métricas. Debajo, una tarjeta por tema ordenada por frecuencia: a la izquierda los mensajes reales de la comunidad y, después de la flecha, el tutorial rápido, el tip de la semana y el tema de documentación con su vista previa, su estado y el botón **Revisar** (abre el borrador en la curaduría). En los temas sin FAQ oficial está **Aprobar y agregar a la base**, y la tarjeta pasa a "FAQ oficial" en el momento.
- **Vista «Esta semana»:** el resultado de cada lote con la estructura exacta del ejemplo de salida del briefing (`formato_briefing`): resumen de la comunidad, post de LinkedIn, newsletter, sugerencia de FAQ, caso de éxito, contenido educativo por tema y almacenamiento, con descarga en JSON.
- **Sesión recuperable:** el panel guarda la sesión (lotes, decisiones, ediciones y FAQs aprendidas) en `data/sesion_guardada.json` cada vez que cambia. Si se recarga la página, *Procesar lote* ofrece **Recuperar sesión** o **Empezar de cero**. «Limpiar la sesión» también borra esa copia. El archivo está en `.gitignore` porque trae textos de la comunidad.
- **Dónde:** `core/adaptador.py` (`motor_faq`, `briefing_de`), `core/backend.py` (`importar_faqs` con tema), `ui/app.py`, `ui/theme.py` (menú y estilos del Motor de FAQ), `.gitignore`.
- **Verificación en el navegador** con las 7 respuestas reales de Gemini cargadas: el Motor de FAQ mostró los temas con sus tres piezas; «Aprobar y agregar a la base» en LangGraph creó `faq-3064` en una copia de la base y la tarjeta pasó a "FAQ oficial"; «Revisar» abrió el tip en la curaduría; «Esta semana» mostró el formato del briefing; al recargar la página, «Recuperar sesión» devolvió los lotes.

### Cambio 18 · Repaso de reglas: docstrings y campos del backend solo en el adaptador

- **Qué:**
  - **Docstrings:** 22 funciones y módulos del panel no tenían docstring (algunos venían de la rama original). Ahora los tienen todos, en el mismo estilo breve y sin tildes. Por ejemplo, `init_estado`, `vista_config`, `banner` y `main` en `ui/app.py`; `_chip`, `_barra` y `panel_temas` en `ui/mui_blocks.py`; `_leer_de_env` en `core/secretos.py`; y `ui/__init__.py`.
  - **Campos del backend:** algunas vistas leían nombres del backend directamente, como `llm_provider`, `storage`, `generated_assets`, `new_ids`, `approved` y el cuerpo de `assets/review`. Esas lecturas pasaron al adaptador, en `estado_motor`, `numero_activos`, `ubicacion`, `resumen_guardado`, `decision_backend` y `activo_para_guardar`. Así se cumple la regla: si cambia un campo del backend, solo se toca `core/adaptador.py`. `core/backend.py` sigue armando los parámetros de cada llamada HTTP, porque es su trabajo.
  - Las sesiones guardadas con la versión anterior se siguen recuperando: `ubicacion()` acepta tanto el formato viejo como el nuevo.
- **Dónde:** `core/adaptador.py`, `ui/app.py`, `ui/mui_blocks.py`, `core/secretos.py` y `ui/__init__.py`.
- **Verificación:**
  - Un escaneo con `ast` del panel no encontró funciones ni módulos sin docstring.
  - En el navegador, contra un backend de prueba en modo local: procesar el ejemplo 01, aprobar un borrador y guardar la curaduría («1 aprobados… Guardado en …-curaduria.json»).
  - *Configuración* mostró la carpeta, los paquetes guardados y el modelo.
  - El aviso de modo local apareció.
  - *Base de conocimiento* y *Motor de FAQ* abrieron sin errores.

### Cambio 19 · `.gitignore` completo y validado

- **Qué:**
  - `communitylab_ui/.gitignore` suma variantes del `.env` (salvo `.env.example`), llaves `.key`, `.oci/`, `.pytest_cache/`, temporales y configuración personal de editores y asistentes de código.
  - Nuevo `.gitignore` en la raíz de la rama, que antes no tenía ninguno, con las reglas generales.
- **Por qué:** un `.env.local` o una carpeta de configuración del editor se podían subir por accidente.
- **Verificación con `git check-ignore`:**
  - Quedaron bloqueados 13 archivos que no deben subirse: los `.env`, una llave, `secrets.toml`, `.venv`, cachés y la sesión guardada.
  - Pasaron los 10 que sí deben subirse.
  - Se hizo `git add .` simulado sobre una copia con `.env` y `.venv`: solo quedan los 25 archivos del proyecto, sin claves.

### Cambio 20 · Se combinó el commit de Braulio sobre secretos y se evitaron choques con la rama del motor

- **Contexto:** el 19 de octubre, Braulio subió a esta rama el commit `50645d3` (*agrega COHERE_API_KEY y lectura de OCI Vault*). En paralelo, nosotros habíamos implementado la lectura de OCI Vault en el cambio 10. Los dos trabajos tocaban `core/secretos.py`, `.env.example` y `requirements.txt`.
- **Qué se tomó de cada uno.** La base es la versión del cambio 10, porque:
  - funciona en un servidor de OCI sin guardar llaves en disco (`instance_principal`);
  - no copia el texto de los errores de OCI en los registros, ya que puede traer identificadores de la cuenta;
  - da mensajes distintos para "no existe", "sin permiso" y "sin conexión";
  - usa los mismos nombres de variables que el motor.

  De Braulio se sumó:

  | Aporte | Por qué |
  |---|---|
  | `_fuente_activa()`: carga el `.env` **antes** de leer `FUENTE_SECRETOS` | **Corrige un error de nuestra versión:** si `FUENTE_SECRETOS` estaba solo dentro del `.env`, la primera consulta usaba el `.env` aunque se pidiera el Vault, y ese resultado quedaba en memoria |
  | `COHERE_API_KEY` en el catálogo y en `.env.example` | La vista Configuración muestra también la clave de Cohere |
  | Sus descripciones de las claves y la nota de que el nombre en el Vault debe coincidir exactamente | Más claras |
  | Sección "Qué necesita el modo vault / auto" y avisos visibles al ejecutar `python core/secretos.py` | Ayudan a quien configura el Vault por primera vez |
  | `FUENTE_SECRETOS=auto` como valor de la plantilla, `OCI_REGION=mx-queretaro-1` y `oci==2.140.0` en `requirements.txt` | Son decisiones suyas y no rompen nada |
  | Su nombre de variable `OCI_VAULT_OCID` | Se sigue aceptando, además de `OCI_VAULT_ID` |

  Un ajuste propio: con `auto` y sin Vault configurado (lo normal en una computadora), la falta del Vault se registra como información y no como aviso, para no llenar la pantalla de advertencias.
- **Choques con la rama del motor:** las dos ramas van a entrar a `main`.
  - `docs/instalacion.md` y `docs/registro-de-funciones.md` del panel pasaron a llamarse `docs/panel-instalacion.md` y `docs/panel-registro-de-funciones.md`.
  - El `.gitignore` de la raíz es idéntico al del motor, así git los une sin conflicto.
- **Verificación:** con un `.env` de prueba y un cliente de OCI falso:
  - `FUENTE_SECRETOS` se respeta desde la primera consulta;
  - `auto` sin Vault usa el `.env` sin avisos;
  - se lee del Vault con `OCI_VAULT_OCID`;
  - un 403 no copia identificadores de la cuenta en los registros;
  - el diagnóstico lista también Cohere.
- **Archivos:** `communitylab_ui/core/secretos.py`, `communitylab_ui/.env.example`, `communitylab_ui/requirements.txt`, `communitylab_ui/README.md`, `.gitignore`, `docs/panel-instalacion.md`, `docs/panel-registro-de-funciones.md`.

### Documentos nuevos

- [panel-instalacion.md](panel-instalacion.md): instalación del panel paso a paso y qué se configura en su `.env`.
- [panel-registro-de-funciones.md](panel-registro-de-funciones.md): cada función agregada, cambiada o quitada desde la versión original, con para qué sirve y por qué cambió.

## 7. Pendientes

- Acciones sobre las personas que requieren apoyo (asignar a un mentor, marcar como atendida).
- Pruebas automatizadas del panel (fuera del alcance de esta etapa).
