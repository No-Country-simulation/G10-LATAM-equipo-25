# Integración de ramas en `feature/backend-ia-orchestration`

Este documento registra cómo se unió el trabajo de todas las ramas del equipo en la rama del backend: qué aportaba cada rama, qué se tomó tal cual, qué se modificó y **por qué**. Sirve para que cualquier integrante entienda el estado actual sin tener que comparar ramas.

Fecha de integración: 19 de octubre de 2026.

---

## 1. Ramas revisadas y decisión

| Rama | Qué aportaba | Decisión |
|---|---|---|
| `feature/backend-ia-orchestration` | Base del backend: FastAPI, grafo LangGraph, puertos del dominio, adaptadores locales y *stubs* | **Rama destino** de la integración |
| `feature/cohere-gemini-adapters` | Adaptadores reales de Gemini (análisis y generación) y Cohere (Embed y Rerank) | Integrada sin cambios en los adaptadores |
| `feature/semantic-retrieval` | Búsqueda semántica: recuperador, índice vectorial local y herramientas `build_faq_index` y `search_faq` | Integrada; un ajuste menor en `build_faq_index` (ver cambio 5) |
| `feature/oci-object-storage` | Adaptador de OCI Object Storage y herramienta `check_oci` | Integrada sin cambios en el adaptador |
| `feature/backend-requirements` | `requirements.txt` y `requirements-dev.txt` | Integrada; se actualizó una nota (ver cambio 11) |
| `feature/data` | Pipeline ETL (`coursera.py`), CSV de FAQs y la base `motor_educativo.db` | **No se fusionó la rama.** Solo se copió la base a `data/motor_educativo.db` (ver sección 4) |
| `feature/ui-curaduria` | Panel de curaduría en Streamlit | **Proyecto aparte, no se fusiona.** Se mejoró en su propia rama; sus cambios están en el documento `docs/integracion-con-backend.md` de esa rama |

### Hallazgo: las ramas del backend eran acumulativas

Al comparar las ramas archivo por archivo se vio que cada una se construyó encima de la anterior:

```
feature/backend-ia-orchestration
  └─ feature/cohere-gemini-adapters      (+ Gemini y Cohere)
       └─ feature/semantic-retrieval     (+ búsqueda semántica)
            └─ feature/oci-object-storage   (+ OCI Object Storage)
                 └─ feature/backend-requirements   (+ requirements)
```

Por eso `feature/backend-requirements` ya contenía el trabajo de todas las ramas del backend, y fue el punto de partida de la integración. No hubo conflictos entre ramas: ningún archivo tenía dos versiones distintas que hubiera que elegir.

## 2. Problemas encontrados al integrar

| Problema | Consecuencia | Solución |
|---|---|---|
| `infrastructure/local.py` importaba `dataset_builder.pii`, un módulo que **no existe en ninguna rama** | El backend no arrancaba: `ModuleNotFoundError` al iniciar la API | Sanitizador propio en `infrastructure/pii.py` (cambio 1) |
| `ExistingLocalRagAdapter` dependía de `dataset_builder.rag`, que tampoco existe | La opción `RETRIEVAL_PROVIDER=existing_local` fallaba siempre | Se reemplazó por la búsqueda en la base de FAQs (cambio 2) |
| La búsqueda de FAQs solo funcionaba con Cohere y un índice construido aparte | Sin clave de Cohere, el flujo FAQ no tenía evidencia y respondía "pendiente de revisión" | Búsqueda directa en `motor_educativo.db`, sin claves (cambio 4) |
| El modo local no reconocía los tipos del briefing (`testimonio`, `pregunta_tecnica`) ni textos sin tildes | El ejemplo oficial del briefing no se enrutaba bien en modo local | Reglas del modo local ampliadas (cambio 6) |
| La API solo aceptaba nombres en inglés | El JSON de ejemplo del briefing devolvía error 422 | Alias en español en los esquemas (cambio 8) |

## 3. Cambios realizados

Cada cambio indica qué se hizo, por qué y qué archivos toca.

### Cambio 1 · Sanitizador de datos personales propio

- **Qué:** nuevo módulo `communitylab_backend/infrastructure/pii.py`. Oculta correos (`[EMAIL]`), teléfonos (`[TELEFONO]`), enlaces (`[URL]`), IPs (`[IP]`) y menciones (`[USUARIO]`). `local.py` ahora lo importa en lugar de `dataset_builder.pii`.
- **Por qué:** sin este módulo el backend no arrancaba. Se mantuvo la misma forma de uso (`sanitize(texto, reglas)`), así que `ExistingSanitizerAdapter` y el grafo no cambiaron su comportamiento.
- **Archivos:** `infrastructure/pii.py` (nuevo), `infrastructure/local.py`.

### Cambio 2 · Se retiró `ExistingLocalRagAdapter` y la opción `existing_local`

- **Qué:** se eliminó el adaptador y la opción `existing_local` de `RETRIEVAL_PROVIDER`. En su lugar existe `faq_db`.
- **Por qué:** dependía de `dataset_builder.rag`, que nunca llegó al repositorio, y no se usaba en ninguna prueba ni configuración. `faq_db` cumple el mismo objetivo (buscar FAQs sin red) con la base real del equipo.
- **Archivos:** `infrastructure/local.py`, `api/dependencies.py`, `config/settings.py`.

### Cambio 3 · Se eliminó `external_stubs.py`

- **Qué:** se borró `infrastructure/external_stubs.py`.
- **Por qué:** sus *stubs* ya tenían implementación real (Gemini, Cohere, OCI Object Storage) y ningún archivo los importaba. El documento `adaptadores-cohere-gemini.md` ya anticipaba que se eliminaría "en una limpieza final cuando todos los adaptadores estén integrados". OCI Vector Store y OCI Vault siguen pendientes y están anotados en el README.
- **Archivos:** `infrastructure/external_stubs.py` (eliminado).

### Cambio 4 · Base de FAQs integrada y búsqueda sin claves

- **Qué:**
  - La base de la rama `feature/data` se copió a `data/motor_educativo.db`.
  - Nuevo `infrastructure/faq_database.py` con `SqliteFaqRetriever`, que busca FAQs con BM25 y un glosario español-inglés.
  - `RETRIEVAL_PROVIDER=faq_db` es ahora el **valor por defecto** (antes era `mock`, que nunca devolvía evidencia).
- **Por qué:** el objetivo de esta etapa es generar la parte de FAQ con la base del equipo. Con `faq_db` el flujo FAQ responde con la FAQ oficial sin necesitar Cohere. La búsqueda semántica con Cohere sigue disponible y sin cambios (`RETRIEVAL_PROVIDER=semantic`).
- **Detalle:** [motor-faq-base-de-datos.md](motor-faq-base-de-datos.md).
- **Archivos:** `data/motor_educativo.db` (nuevo), `infrastructure/faq_database.py` (nuevo), `api/dependencies.py`, `config/settings.py`.

### Cambio 5 · `build_faq_index` reutiliza la lectura de la base

- **Qué:** `tools/build_faq_index.py` ahora usa la función `load_faq_records` de `faq_database.py`, en vez de tener su propia consulta SQL. El parámetro `--db` pasó a ser opcional (por defecto `data/motor_educativo.db`).
- **Por qué:** así el índice semántico y la búsqueda local parten exactamente de las mismas FAQs (misma deduplicación de preguntas repetidas). El resultado es idéntico al anterior y sus pruebas pasan sin cambios.
- **Archivos:** `tools/build_faq_index.py`.

### Cambio 6 · Modo local (`MockLLMProvider`) más útil para la demo

- **Qué:**
  - Reconoce los tipos del briefing (`testimonio`, `pregunta_tecnica`, `pregunta`, `duda`) además de los originales en inglés.
  - Compara palabras sin tildes ("quede seleccionada" = "quedé seleccionada").
  - En la ruta FAQ arma el contenido con las dudas de la comunidad y **la respuesta de la FAQ oficial mejor puntuada**, citando su identificador. Si no hay FAQ relacionada, sigue diciendo "Respuesta pendiente de revisión humana con evidencia".
  - Temas más cercanos a la comunidad (Machine learning, IA generativa y LangGraph, Oracle Cloud, etc.).
- **Por qué:** permite demostrar el flujo completo sin clave de Gemini. Con `LLM_PROVIDER=gemini` se usa el adaptador de Gemini, que no se modificó.
- **Archivos:** `infrastructure/local.py`.

### Cambio 7 · Configuración

| Variable | Antes | Ahora | Motivo |
|---|---|---|---|
| `RETRIEVAL_PROVIDER` | `mock` (opciones `mock`, `existing_local`, `semantic`) | `faq_db` (opciones `mock`, `faq_db`, `semantic`) | Cambios 2 y 4 |
| `LOCAL_STORAGE_DIR` | `output/backend/drafts` | `salidas/paquetes` | Todas las salidas en una sola carpeta `salidas/` |
| `FAQ_DB_PATH` | — | `data/motor_educativo.db` | Ruta de la base de FAQs |
| `FAQ_TYPES` | — | `question,pregunta,pregunta_tecnica,duda` | Tipos que cuentan como duda en modo local |
| `SUCCESS_TYPES` | `testimonial` | `testimonial,testimonio,logro` | Tipos del briefing |
| `SUCCESS_KEYWORDS` | ... | se agregaron "quedé seleccionad", "me contrataron" | Frases del ejemplo del briefing |

Se agregó `.env.example` en la raíz con todas las variables comentadas. Antes no existía en el backend.

- **Archivos:** `config/settings.py`, `.env.example` (nuevo).

### Cambio 8 · API

- **Qué:**
  - `POST /api/v1/activity/process` acepta también los nombres del briefing (`origen_comunidad`, `periodo_referencia`, `interacciones`, `autor`, `canal`, `tipo`, `texto`). Los nombres en inglés siguen funcionando igual.
  - Nuevo `GET /api/v1/status`: indica qué LLM, buscador y almacenamiento están activos, sin mostrar claves. Lo usa el panel en su vista de Configuración.
  - Nuevo `POST /api/v1/assets/review`: guarda lo que el equipo aprobó o rechazó (con sus ediciones) como `<request_id>-curaduria.json`, en el mismo almacenamiento (carpeta local u OCI).
  - La construcción de la respuesta de `process` pasó de `main.py` a `application/batch.py`, sin cambiar la respuesta.
- **Por qué:** el ejemplo oficial del briefing debe funcionar tal cual. El panel necesitaba saber dónde se guarda y poder registrar la aprobación humana, que es parte del requisito de curaduría. Mover la lógica a `application/` permite que la API y la herramienta de terminal produzcan exactamente la misma respuesta.
- **Archivos:** `api/schemas.py`, `main.py`, `application/batch.py` (nuevo).

### Cambio 9 · Ingesta de archivos, ejemplos y salidas

- **Qué:**
  - `application/ingestion.py`: lee lotes JSON (formato del briefing o en inglés) y CSV (`autor,canal,tipo,texto`), limpia espacios y descarta filas vacías.
  - `tools/process_batch.py`: procesa uno o varios lotes desde la terminal y guarda cada respuesta en `salidas/respuestas/`.
  - `ejemplos/`: 5 lotes que cubren las tres rutas, incluido el ejemplo exacto del briefing.
  - `salidas/respuestas/`: resultados de la demostración generados en modo local.
- **Por qué:** el checklist pide ingesta funcional (JSON o CSV) y al menos 3 ejemplos demostrables. Las salidas quedan separadas del código en su propia carpeta.
- **Archivos:** `application/ingestion.py`, `tools/process_batch.py`, `ejemplos/`, `salidas/respuestas/` (todos nuevos).

### Cambio 10 · Pruebas

Solo se ajustaron dos pruebas existentes. No se agregaron pruebas nuevas en esta etapa.

| Prueba | Cambio | Motivo |
|---|---|---|
| `test_semantic_wiring.py` | `test_default_retrieval_is_still_the_mock` pasó a `test_default_retrieval_is_the_faq_database` | El valor por defecto cambió a `faq_db` (cambio 4) |
| `test_semantic_wiring.py` y `test_storage_wiring.py` | Se quitó el `dataset_builder` falso que se inyectaba en la *fixture* | Ya no hace falta: el sanitizador es propio (cambio 1) |

### Cambio 11 · Archivos de soporte

- `requirements.txt`: se reemplazó la nota que decía que faltaba `dataset_builder` por una que aclara que la sanitización y la búsqueda en la base solo usan la librería estándar. Las dependencias no cambiaron.
- `.gitignore`: se agregó `salidas/paquetes/`, porque la API genera un archivo por cada procesamiento, y `*.tmp`.
- `README.md` de la raíz: reescrito con el diagrama de arquitectura, el flujo, la guía paso a paso y el checklist.
- `docs/`: nuevos `integracion-ramas.md`, `motor-faq-base-de-datos.md` y `guia-demo.md`; se actualizaron los tres documentos existentes donde quedaban desactualizados.
- Docstrings que mencionaban `dataset_builder` se actualizaron (`__init__.py`, `orchestration.py`).

## 4. Qué se tomó de `feature/data` y qué no

- **Se tomó:** `motor_educativo.db`, tal cual (mismo archivo, sin modificar), en `data/motor_educativo.db`.
- **No se tomó:** `coursera.py` (pipeline ETL), `datafaq_enriched.csv` ni su README. Ese pipeline usa `pandas`, `transformers` y `torch`, y el CSV original de 272 MB no está en el repositorio. Esas dependencias no hacen falta para ejecutar el backend.
- **Si el equipo de datos regenera la base:** basta con reemplazar `data/motor_educativo.db`. La búsqueda lee la tabla `contenido_educativo` (columnas `reviews`, `faq_answer`, `course_id`, `is_faq`) y detecta el cambio automáticamente. Si se usa la búsqueda semántica, hay que reconstruir el índice (`python -m communitylab_backend.tools.build_faq_index`).

## 5. Lo que no se modificó

Para respetar el trabajo de cada rama, estos archivos quedaron **exactamente igual**:

- `infrastructure/gemini_adapter.py` (prompts, esquemas y salvaguardas de Gemini)
- `infrastructure/cohere_adapters.py`
- `infrastructure/vector_index.py`
- `infrastructure/oci_storage.py`
- `application/retrieval.py`
- `application/orchestration.py` (solo cambió una línea de docstring)
- `domain/` completo (modelos, puertos y errores)
- `tools/check_oci.py` y `tools/search_faq.py`
- Las demás pruebas de `tests/backend/`

> **Nota:** esta lista describe el momento de la integración. Después, en las mejoras de la [sección 7](#7-mejoras-posteriores-a-la-integración), sí se modificaron `gemini_adapter.py`, `orchestration.py`, `domain/` y una línea de `test_gemini_adapter.py`. Allí se explica qué cambió y por qué.

## 6. Verificación realizada

- Pruebas unitarias: 56 pasan. Una (`test_semantic_retrieval_builds_the_full_chain`) requiere tener instalado el SDK de Cohere, que viene en `requirements.txt`. En el entorno de integración no estaba instalado y esa prueba ya fallaba antes de los cambios por el mismo motivo.
- `python -m communitylab_backend.documentation_check`: documentación del backend completa.
- API levantada con `uvicorn`: se probaron `/health`, `/api/v1/status`, `/api/v1/activity/process` (con nombres en español e inglés), `/api/v1/rag/query`, `/api/v1/assets/review` y el error 422 con un texto vacío.
- Los 5 lotes de `ejemplos/` se procesaron con `tools/process_batch.py`, con las tres rutas esperadas, datos personales ocultos y citas de FAQ en los lotes de dudas.
- Panel de curaduría conectado al backend: procesamiento de los ejemplos, aprobación con texto editado y guardado de la curaduría.

## 7. Mejoras posteriores a la integración

Tres mejoras para cumplir mejor el briefing, hechas después de integrar las ramas. Todas funcionan igual en modo local (`LLM_PROVIDER=mock`, sin claves) y con Gemini.

**En resumen:** antes, cada lote seguía **una sola** ruta; si traía un logro y una duda, la duda se perdía. Ahora un lote puede activar **varias rutas**, cada mensaje recibe su propio análisis con un **puntaje de relevancia**, y la respuesta incluye una copia con la **estructura exacta del ejemplo de salida del briefing**.

### Cambio 12 · Varias rutas por lote

- **Qué:**
  - El nodo `route` ahora devuelve una **lista** de rutas activas: `success_story` si hay algún logro o testimonio, `faq` si hay alguna duda, y `community_highlight` solo si no aplica ninguna de las dos. En `routing` se agregan `flows` (la lista) y `reasons` (la razón de cada ruta). `selected_flow` y `reason` se conservan con la ruta principal, para no romper a quien ya los use.
  - La bifurcación sigue visible en el grafo (`add_conditional_edges` desde `route`), pero ahora devuelve una lista y LangGraph ejecuta esas ramas **en paralelo**.
  - Las ramas ya **no llaman al LLM**: cada una arma un *encargo* (`ContentBrief`: ruta, activos a pedir, mensajes elegidos, evidencia y razón). `faq` elige las dudas y las FAQs oficiales; `success_story`, los logros; `community_highlight`, los mensajes más relevantes. Los encargos se juntan con un reductor (`Annotated[list, operator.add]`).
  - Nuevo nodo `compose`: redacta **todos** los encargos con **una sola llamada** al LLM. Después sigue `persist`, que ahora también guarda los encargos en el paquete.
  - El puerto `LLMProvider` suma el método `generate_assets(encargos, análisis)`, implementado en `MockLLMProvider` y en `GeminiLLMAdapter`. En Gemini es una sola llamada por lote que pide exactamente los tipos de todos los encargos, sin repetir, y conserva las salvaguardas: los mensajes y citas van como datos dentro de etiquetas, se descartan los `evidence_ids` inventados (o de otro encargo) y todo sale en estado `draft`. El método `generate` anterior se conserva para no romper sus pruebas.
  - Cada activo indica con `flow` qué ruta lo encargó.
  - La búsqueda de FAQs (`retrieve`) usa solo el texto de las dudas cuando las hay, para que un logro en el mismo lote no desvíe la búsqueda.
- **Por qué:** el ejemplo de salida del briefing genera post de LinkedIn, newsletter y FAQ **del mismo lote**. Con una sola ruta, las dudas de un lote con logros se perdían. Una sola llamada en `compose` mantiene el gasto de Gemini en 2 llamadas por lote (la cuota gratuita es de unas 20 al día).
- **Resultado:** `ejemplos/01_briefing_semana04.json` ahora genera `success_story` + `linkedin_post` + `faq_content` + `newsletter_highlight`. Los otros 4 ejemplos mantienen su ruta, su sentimiento y sus temas.
- **Archivos:** `application/orchestration.py`, `domain/models.py` (`ContentBrief`, `FLOW_KINDS`, `FLOW_ORDER`, campo `flow` en `DraftAsset`), `domain/ports.py`, `infrastructure/local.py`, `infrastructure/gemini_adapter.py`.

### Cambio 13 · Análisis por mensaje y puntaje de relevancia

- **Qué:**
  - Nuevo modelo `InteractionSignal` (id, sentimiento, categoría, relevancia de 0 a 1 y si necesita apoyo). Categorías: `logro`, `duda`, `apoyo` y `comentario`. `Analysis` suma el campo `interaction_signals` (vacío por defecto).
  - **Gemini:** en la **misma** llamada de `analyze`, el esquema pide también la señal de cada mensaje. Si Gemini omite algún mensaje, se completa con la regla local; los ids inventados se descartan y la relevancia se acota entre 0 y 1.
  - **Modo local:** nueva clase `InteractionRules` en `local.py`. Calcula la señal con el tipo declarado, palabras clave sin tildes, signos de pregunta y palabras de frustración ("no entiendo", "me cuesta", "no funciona"...). La relevancia parte de un valor por categoría (logro 0.85, duda 0.70, apoyo 0.65, comentario 0.40) y se ajusta según el largo del texto. El sentimiento **del lote** en modo local se calcula igual que antes.
  - La respuesta de `/api/v1/activity/process` suma: `interaction_analysis` (id, autor, canal, texto con los datos personales ya ocultos, sentimiento, categoría, relevancia y si necesita apoyo; el texto sanitizado se agregó para que el panel no muestre correos ni teléfonos originales), `highlights` (los 3 mejores momentos), `members_needing_support` y `discarded` (mensajes que no entraron a ningún encargo).
  - El **autor nunca entra al grafo ni al LLM**: `application/batch.py` lo separa antes de invocar el grafo y lo une por id solo al armar la respuesta. Por eso `main.py` ahora le pasa el autor a `process_batch`.
- **Por qué:** el briefing pide identificar quién logró un hito, qué miembros necesitan apoyo y un mecanismo de puntuación de relevancia para elegir los mejores momentos.
- **Archivos:** `domain/models.py`, `infrastructure/local.py`, `infrastructure/gemini_adapter.py`, `application/batch.py`, `api/schemas.py`, `main.py`, `tools/process_batch.py` (el resumen de terminal muestra todas las rutas y cuántas personas requieren apoyo).

### Cambio 14 · Respuesta en el formato exacto del briefing

- **Qué:** nuevo módulo `application/briefing_format.py` y nuevo campo `formato_briefing` en la respuesta, con la estructura del ejemplo oficial:
  - `status: "exito"`.
  - `resumen_comunidad`: total procesado, `sentimiento_predominante` ("Altamente Positivo" si el lote es positivo y al menos el 75% de sus mensajes también; si no, Positivo, Neutral, Negativo o Mixto) y temas principales.
  - `activos_distribucion_generados`: `post_linkedin` (con `canal_recomendado: "LinkedIn Oficial"` y `potencial_engagement` Alto/Medio/Bajo según la relevancia máxima del lote), `destaque_newsletter_semanal` (sección según la ruta que lo encargó), `sugerencia_contenido_faq` (`origen: "Duda planteada por <autor> en <canal>"`; `status` `respuesta_con_faq_oficial` si cita una FAQ o `derivado_a_mentoria` si no) y `caso_exito` cuando existe. Solo aparecen los activos que realmente se generaron.
  - `almacenamiento_oci`: bucket, ruta del objeto y `guardado_con_exito` con OCI; en modo local, bucket `null`, la ruta del archivo y `guardado_local`.
- **Por qué:** quien evalúe puede comparar la respuesta lado a lado con el ejemplo del briefing. La respuesta en inglés se mantiene igual porque la usa el panel.
- **Archivos:** `application/briefing_format.py` (nuevo), `application/batch.py`, `api/schemas.py`.

### Cambios en archivos de otras ramas

| Archivo | Rama de origen | Qué cambió y por qué |
|---|---|---|
| `infrastructure/gemini_adapter.py` | `feature/cohere-gemini-adapters` | Se agregaron el esquema de señales por mensaje y `generate_assets`. `FLOW_KINDS` pasó a `domain/models.py` (mismos valores) para que el grafo y el adaptador usen la misma tabla. Prompts, salvaguardas y `generate` siguen igual |
| `tests/backend/test_gemini_adapter.py` | `feature/cohere-gemini-adapters` | Único cambio: el JSON falso de `test_analyze_parses_json_and_escapes_tags` incluye `interaction_signals`, porque ahora es un campo obligatorio del esquema que se envía a Gemini |
| `application/orchestration.py`, `domain/` | `feature/backend-ia-orchestration` | Grafo con varias rutas y nodo `compose`; nuevos modelos y método del puerto (cambios 12 y 13) |

No se agregaron pruebas e2e ni de aceptación.

### Verificación

- `python -m pytest tests/backend -q`: 60 pruebas pasan.
- `python -m communitylab_backend.documentation_check`: documentación del backend completa.
- `generate_assets` de Gemini probado a mano con un cliente falso: una sola llamada, 4 activos, se descarta una cita inventada y otra de un encargo ajeno, y falla con `AssetGenerationError` si falta un tipo.
- Los 5 ejemplos se reprocesaron (`salidas/respuestas/`) y se compararon con la versión anterior: igual sentimiento del lote, igual ruta principal e iguales temas; el lote 01 suma la ruta `faq`.
- API levantada con `uvicorn` y probada con `ejemplos/01_briefing_semana04.json`.

### Cambio 15 · Claves de Gemini y Cohere desde OCI Vault

- **Qué:**
  - Nuevo adaptador `OCIVaultSecretProvider` (`infrastructure/oci_vault.py`) que implementa el puerto `SecretProvider`, que ya existía pero nadie usaba. Pide cada secreto con `SecretsClient.get_secret_bundle_by_name`, decodifica el base64 y lo guarda en memoria. Se autentica igual que el almacenamiento en OCI: `OCI_AUTH=config` (archivo `~/.oci/config`) o `instance_principal` (servidor de OCI Compute, sin claves en disco).
  - `api/dependencies.py` suma `get_api_key(settings, nombre)`: con `SECRET_PROVIDER=environment` (por defecto) devuelve la clave de `Settings` exactamente como antes; con `oci` la pide al Vault antes de construir Gemini o Cohere. El lector del Vault se crea una sola vez por proceso, aunque el flujo se arme en cada solicitud. `tools/build_faq_index.py` y `tools/search_faq.py` usan la misma función.
  - Variables nuevas: `OCI_VAULT_ID`, `OCI_SECRET_GEMINI` (por defecto `communitylab-gemini-api-key`) y `OCI_SECRET_COHERE` (por defecto `communitylab-cohere-api-key`), los mismos nombres del catálogo del panel. Documentadas sin valores en `.env.example`.
  - `GET /api/v1/status` indica `secret_provider` (nunca valores).
  - Los valores nunca se registran ni aparecen en errores; los fallos de OCI se traducen a `ProviderUnavailableError` (503) con mensajes que dicen qué revisar (permiso, nombre del secreto, `OCI_VAULT_ID`).
- **Por qué:** en producción las claves no deben quedar en un archivo del servidor ni en el repositorio. Con OCI Vault quedan cifradas, solo las lee el servidor autorizado por una política de solo lectura, y se rotan creando una versión nueva del secreto. Guía para todo el equipo: [secretos.md](secretos.md).
- **Archivos:** `infrastructure/oci_vault.py` (nuevo), `config/settings.py`, `api/dependencies.py`, `main.py`, `tools/build_faq_index.py`, `tools/search_faq.py`, `.env.example`, `tests/backend/test_oci_vault.py` (nuevo), `docs/secretos.md` (nuevo), `README.md`.
- **Verificación:** 22 pruebas nuevas con un cliente falso (sin red): lectura y decodificación, caché, secreto inexistente, errores 401/403/429/500 sin filtrar identificadores, contenido inválido, `environment` sin cambios y `oci` entregando la clave del Vault a Gemini. `python -m pytest tests/backend -q`: 82 pruebas pasan. **No se probó contra una cuenta real de OCI.**

### Cambio 16 · La base de conocimiento se puede consultar

- **Qué:** tres consultas nuevas de sólo lectura sobre `motor_educativo.db`:
  - `GET /api/v1/knowledge/summary`: cuántas FAQs (141 distintas, 145 filas), reseñas (2.918 filas, 2.758 distintas) y cursos (30) tiene la base, el rango de fechas, el sentimiento que etiquetó el equipo de datos, las notas y los cursos con más reseñas.
  - `GET /api/v1/knowledge/faqs`: las FAQs oficiales con el mismo identificador que citan los borradores (por ejemplo `faq-2067`).
  - `GET /api/v1/knowledge/reviews`: reseñas reales filtradas por curso y sentimiento, con el texto sin datos personales y sin repetir las reseñas duplicadas de la base.
- **Por qué:** la base sólo se usaba por dentro (para buscar la FAQ que responde una duda) y no había forma de comprobar que estaba cargada ni de ver qué FAQ se había usado. Las reseñas reales no se usaban en ningún lado; ahora se pueden enviar al motor como un lote.
- **Hallazgo:** la base tiene 160 reseñas repetidas (mismo autor y mismo texto). No se modificó la base; las consultas muestran cada reseña una sola vez.
- **Archivos:** `infrastructure/faq_database.py` (`database_summary`, `list_reviews`, `list_courses`), `main.py`.

### Cambio 17 · Agregar FAQs nuevas a la base desde un CSV o JSON

- **Qué:**
  - `application/faq_import.py` lee un CSV (`pregunta,respuesta,curso`) o un JSON (lista, u objeto con la lista en `faqs`), acepta los nombres en español e inglés y valida cada fila (pregunta y respuesta obligatorias, largos máximos, hasta 200 FAQs por carga; sin curso se usa `general`).
  - `infrastructure/faq_database.add_faqs` agrega sólo las preguntas que no existen (sin distinguir mayúsculas) como filas nuevas con `is_faq = 1`, con el mismo formato que las FAQs del equipo de datos (`reviewers = CommunityLab`, `sentiment = FAQ Educativo`). **Antes de escribir guarda una copia completa de la base** en `data/respaldos/` y escribe todo en una sola transacción: si algo falla, la base queda como estaba. **No toca las reseñas.**
  - `POST /api/v1/knowledge/faqs/import`: con `dry_run=true` (el valor por defecto) sólo devuelve la vista previa: qué se agregaría, qué ya existe y qué filas tienen errores. Con `dry_run=false` escribe.
  - `python -m communitylab_backend.tools.import_faqs <archivo> [--aplicar]`: lo mismo desde la terminal.
  - Plantilla de ejemplo: `ejemplos/faqs/faqs_nuevas_ejemplo.csv`. Está en una subcarpeta para que `process_batch ejemplos` no la confunda con un lote de mensajes.
  - `.gitignore`: `data/respaldos/`. Variable nueva `FAQ_BACKUP_DIR` (por defecto `data/respaldos`).
- **Por qué:** la base sólo se podía actualizar reemplazando el archivo completo. Ahora el equipo puede sumar respuestas oficiales a las dudas que el motor no sabía responder. El buscador detecta el cambio en la base y usa las FAQs nuevas al instante, sin reiniciar.
- **Ejemplo real:** la duda del briefing sobre los nodos condicionales de LangGraph no tenía FAQ y quedaba `derivado_a_mentoria`. Después de agregar la FAQ de la plantilla, el mismo lote sale `respuesta_con_faq_oficial`, citando la FAQ nueva.
- **Ojo:** `motor_educativo.db` está en el repositorio. Si se agregan FAQs y se hace commit, el archivo de la base cambia en git. Si se usa la búsqueda semántica (Cohere), hay que reconstruir su índice (`build_faq_index`) para que incluya las FAQs nuevas.
- **Verificación:** 4 pruebas nuevas en `tests/backend/test_faq_import.py`, con una base temporal: la vista previa no escribe, la carga crea la copia, salta repetidas, no toca reseñas y el buscador encuentra la FAQ nueva. En total pasan 86 pruebas. En el navegador se probó contra una **copia** de la base: 2 FAQs agregadas, 1 repetida y 1 fila con error detectadas, reseñas sin cambios y copia de seguridad creada. La base real no se modificó (misma huella MD5).
- **Archivos:** `application/faq_import.py` (nuevo), `infrastructure/faq_database.py`, `api/schemas.py`, `main.py`, `config/settings.py`, `tools/import_faqs.py` (nuevo), `tests/backend/test_faq_import.py` (nuevo), `ejemplos/faqs/faqs_nuevas_ejemplo.csv` (nuevo), `.gitignore`.

### Cambio 18 · Motor de FAQ dinámico: dudas frecuentes → tutoriales, tips y documentación

- **Qué:**
  - **Tema por duda.** En la misma llamada de análisis, Gemini asigna a cada mensaje un `topic` en pocas palabras (por ejemplo "Normalización por lotes"). Recibe además los temas ya vistos en el historial, para reutilizar el nombre y poder contar la frecuencia. En modo local el tema sale de reglas.
  - **Búsqueda por tema.** El nodo `retrieve` busca en la base las FAQs de cada tema por separado (hasta 2 citas por tema), en lugar de una sola consulta con todas las dudas mezcladas.
  - **Un encargo por tema.** La rama `faq` arma un encargo por cada uno de los 2 temas con más dudas (`MAX_FAQ_TOPICS`). Las dudas de otros temas quedan descartadas en ese lote, pero cuentan en el ranking.
  - **Tres formatos nuevos**, redactados por Gemini en la misma llamada de `compose`: `quick_tutorial` (tutorial rápido con pasos), `weekly_tip` (tip de la semana) y `doc_topic` (propuesta de tema de documentación). Reemplazan, en la ruta `faq`, a `faq_content` + `newsletter_highlight`. Cada activo lleva su `topic`. El método anterior `generate` y su tabla `FLOW_KINDS` no cambiaron (la tabla nueva es `BRIEF_KINDS`).
  - **Historial y ranking de dudas frecuentes** (`infrastructure/doubt_history.py`): cada duda se guarda con su tema, la fecha, el texto sin datos personales y las FAQs encontradas, en `data/historial_dudas.db` (no se sube a git). `GET /api/v1/knowledge/frequent-doubts` devuelve los temas ordenados por cantidad, con semanas, lotes y si tienen FAQ oficial. No usa IA. Si guardar el historial falla, el lote se procesa igual y queda un aviso.
  - **Respuesta:** `faq_topics` (temas redactados, con sus dudas y FAQs), `topic` en `interaction_analysis` y en cada activo. En `formato_briefing`, el tutorial del tema principal alimenta `sugerencia_contenido_faq`, el tip alimenta `destaque_newsletter_semanal` (sección "Tip de la Semana") y el bloque nuevo `contenido_educativo` reúne los tres formatos de cada tema.
  - **Menos tokens:** cada mensaje se envía recortado a 600 caracteres (antes 1.200) y cada FAQ a 400 (antes 600). Siguen siendo 2 llamadas por lote.
- **Por qué:** el foco del equipo es transformar dudas **frecuentes** en tutoriales rápidos, tips de la semana y temas de documentación. Antes cada lote producía una sola FAQ mezclando temas, no había memoria entre lotes para saber qué era frecuente, el "tip" era un texto fijo y no existía la propuesta de documentación.
- **Ejemplo real con Gemini** (`salidas/respuestas_gemini/06_resenas_reales_coursera.json`): de 10 reseñas reales, Gemini identificó los temas de cada mensaje y redactó tutorial, tip y documentación para "Normalización por lotes" (citando la FAQ oficial `faq-2067`) y para "Herramientas de laboratorio". En este segundo tema la búsqueda devolvió FAQs que no venían al caso: Gemini no las citó y marcó el tutorial como borrador para validar con un mentor.
- **Archivos de otras ramas:** `infrastructure/gemini_adapter.py` (esquema con `topic`, esquema por encargo `BriefAssetOutput` y guía de los formatos nuevos) y `tests/backend/test_gemini_adapter.py`, donde **el único cambio** es agregar `"topic"` al JSON falso de la prueba de análisis, porque ahora es un campo obligatorio del esquema.
- **Verificación:** 4 pruebas nuevas en `tests/backend/test_motor_faq.py`: agrupamiento por tema con evidencia propia, los tres formatos por tema, el historial entre lotes y los nombres de tema estables. En total pasan 90 pruebas. Se reprocesaron los ejemplos en modo local y se validó con Gemini real (2 llamadas).
- **Archivos:** `domain/models.py`, `domain/ports.py`, `application/orchestration.py`, `application/batch.py`, `application/briefing_format.py`, `infrastructure/local.py`, `infrastructure/gemini_adapter.py`, `infrastructure/doubt_history.py` (nuevo), `api/dependencies.py`, `api/schemas.py`, `main.py`, `config/settings.py`, `.env.example`, `.gitignore`, `tests/backend/test_motor_faq.py` (nuevo), `tests/backend/test_gemini_adapter.py`.

### Cambio 19 · Ranking al instante y búsqueda semántica lista para usar

- **Qué:**
  - **Ranking al instante:** `POST /api/v1/knowledge/faqs/import` acepta `topic`. Cuando el panel agrega a la base el tutorial de un tema sin respaldo, el historial (`DoubtHistory.attach_faqs`) marca ese tema como resuelto en ese momento, sin esperar a que alguien vuelva a preguntar.
  - **Búsqueda semántica con umbral:** `SemanticRetriever` acepta `min_score` (por defecto 0, sin cambios para quien ya lo usaba) y la configuración nueva `RETRIEVAL_MIN_SCORE=0.5` descarta las FAQs poco relevantes. Sin umbral, una duda sin respuesta en la base recibía igual la FAQ "menos mala".
  - **Índice al día:** si la búsqueda semántica está activa, agregar FAQs reconstruye su índice (`rebuild_semantic_index`, unas 2 llamadas a Cohere). Si falla, las FAQs quedan agregadas y la respuesta trae un aviso.
  - `data/faq_index.json` se agregó a `.gitignore`: se genera con `build_faq_index` y pesa unos 2 MB.
- **Comparación hecha con Cohere real** (9 dudas en español): las dos búsquedas aciertan las 5 dudas directas. La semántica además encuentra la FAQ exacta de *batch normalization* y entiende "mi modelo funciona bien con los datos de entrenamiento pero mal con datos nuevos" como *overfitting* (0,89), cosa que BM25 no encuentra. Con el umbral, las dudas sin FAQ (LangGraph 0,17 y Watson 0,36) quedan sin cita. Detalle en [busqueda-semantica.md](busqueda-semantica.md).
- **Decisión:** el valor por defecto sigue siendo `faq_db` (BM25), porque no depende de la red, no gasta cuota y aprende al instante. La búsqueda semántica queda lista para activarla con `RETRIEVAL_PROVIDER=semantic`.
- **Archivos de otras ramas:** `application/retrieval.py` (de `feature/semantic-retrieval`) sólo suma el parámetro `min_score`, con valor por defecto que conserva el comportamiento anterior. `tests/backend/test_semantic_retriever.py` suma una prueba del umbral; las existentes no cambiaron.
- **Archivos:** `infrastructure/doubt_history.py`, `api/schemas.py`, `api/dependencies.py`, `main.py`, `config/settings.py`, `application/retrieval.py`, `.env.example`, `.gitignore`, `tests/backend/test_motor_faq.py`, `tests/backend/test_semantic_retriever.py`. Pasan 92 pruebas.

### Cambio 20 · La base de conocimiento y el historial respetan la arquitectura hexagonal

- **Qué:**
  - Dos contratos nuevos en `domain/ports.py`:
    - `KnowledgeBasePort`: leer totales, FAQs y reseñas, y agregar FAQs.
    - `DoubtHistoryPort`: guardar dudas, temas conocidos, marcar un tema resuelto y armar el ranking.
  - Un caso de uso nuevo, `application/knowledge.py` (`KnowledgeService`). Reúne lo que antes hacían los endpoints `/api/v1/knowledge/...`, incluida la importación de FAQs con la marca del tema y la actualización del índice semántico.
  - Un adaptador nuevo, `SqliteKnowledgeBase` en `infrastructure/faq_database.py`. Solo agrupa las funciones que ya existían.
  - `api/dependencies.py` arma el servicio (`build_knowledge`, `get_knowledge`). Los endpoints lo reciben con `Depends`, igual que el flujo de procesamiento.
  - `ProcessingWorkflow` declara el historial con su contrato (`DoubtHistoryPort | None`).
  - `tools/import_faqs.py` usa el mismo servicio. Por eso ahora también marca el tema resuelto y muestra los avisos, igual que la API.
- **Por qué:**
  - Los endpoints de la base de conocimiento llamaban directo a SQLite desde la API. Así se saltaban la capa de aplicación, y la lógica de importar FAQs quedaba repetida entre la API y la herramienta de terminal.
  - Además, el historial de dudas entraba al grafo sin un contrato que dijera qué se le podía pedir.
  - Con este cambio, la base o el historial se pueden pasar a otro almacenamiento (por ejemplo, uno en la nube) sin tocar la API ni el grafo.
- **Las respuestas no cambian:** se comparó cada endpoint antes y después.
- **Verificación:**
  - 2 pruebas nuevas en `tests/backend/test_knowledge_service.py`, con una base y un historial falsos:
    - la vista previa no escribe;
    - la importación marca el tema;
    - si el índice falla, queda un aviso.
  - En total pasan 94 pruebas y `documentation_check` está completo.
  - API levantada contra copias de la base y del historial:
    - `summary`, `faqs`, `reviews` y `frequent-doubts` responden igual;
    - importar una FAQ con `topic` marcó ese tema como resuelto en el ranking;
    - `import_faqs` por terminal mostró la vista previa;
    - el ejemplo 01 se procesó bien.
  - La base real no cambió (misma huella MD5).
- **Archivos:** `domain/ports.py`, `application/knowledge.py` (nuevo), `application/orchestration.py`, `application/faq_import.py` (solo el docstring), `infrastructure/faq_database.py`, `api/dependencies.py`, `main.py`, `tools/import_faqs.py`, `tests/backend/test_knowledge_service.py` (nuevo).

Qué hace cada función que cambió desde la rama original, y por qué: [registro-de-funciones.md](registro-de-funciones.md). Instalación y cambio de credenciales: [instalacion.md](instalacion.md).

### Cambio 21 · `.gitignore` completo y validado

- **Qué:** el `.gitignore` se reorganizó por secciones con un comentario cada una:
  - **Secretos:** `.env` y sus variantes, salvo `.env.example`; llaves `.pem`, `.key`, `.p12` y `.pfx`; `.oci/`; archivos de credenciales.
  - **Entorno de Python** y **cachés de pruebas:** `.venv/`, `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/` y cobertura.
  - **Datos que genera el motor:** `salidas/paquetes/`, `data/respaldos/`, `data/historial_dudas.db`, `data/faq_index.json` y los temporales de SQLite.
  - **Temporales y registros.**
  - **Configuración personal** de editores, asistentes de código y sistema operativo.
- **Por qué:** antes faltaban `.pytest_cache/`, los temporales de SQLite, otras extensiones de llaves y las carpetas de configuración personal. Cualquiera de esos archivos se podía subir por accidente con `git add .`.
- **Verificación con `git check-ignore`:**
  - 22 archivos que no deben subirse quedaron bloqueados: `.env.local`, una llave `.pem`, paquetes, historial, índice, cachés y configuración del editor.
  - 13 archivos que sí deben subirse pasaron: `.env.example`, `data/motor_educativo.db`, `ejemplos/`, `salidas/respuestas*/`, `docs/` y pruebas.
  - Se hizo `git add .` simulado sobre una copia con `.env`, `.venv` y 84 paquetes: se bloquean 131 archivos y solo quedan los 86 del proyecto.
  - Ninguno de esos 86 tiene claves. Las pruebas de OCI usan valores de mentira (`ocid1.user.oc1..aaaa`).
- **Archivos:** `.gitignore`.

### Cambio 22 · Memoria del motor en OCI Object Storage y despliegue en Hugging Face Spaces

- **Contexto:** no se pudo crear la máquina en OCI Compute. Los organizadores confirmaron que se puede desplegar en cualquier lugar, siempre que se usen los servicios de OCI. Se eligió **Hugging Face Spaces** (Docker, gratis), con **OCI Object Storage** y **OCI Vault** como servicios centrales.
- **Problema a resolver:** el disco de un Space se borra al reiniciar. Sin un cambio, se perderían el historial de dudas (el ranking) y las FAQs que el equipo agrega a la base.
- **Qué:**
  - **`STATE_PROVIDER=oci`** (nuevo; por defecto sigue `local`). El módulo nuevo `infrastructure/oci_state.py` tiene tres piezas:
    - `OCIFileMirror`: al encender, baja del bucket `estado/historial_dudas.db` y `estado/motor_educativo.db`; si todavía no existen, usa las copias locales del repositorio. También sabe subirlos.
    - `MirroredDoubtHistory`: envuelve al historial local y lo sube después de cada cambio.
    - `MirroredKnowledgeBase`: envuelve a la base local y la sube después de agregar FAQs.
  - Las dos envolturas cumplen los mismos contratos (`DoubtHistoryPort` y `KnowledgeBasePort`): el grafo, la API y los casos de uso no cambiaron.
  - **Seguridad de la memoria:** si OCI no responde al encender, el motor **no trabaja con una memoria vacía**, porque después la subiría encima de la buena. Responde 503 con un mensaje claro y reintenta en la siguiente solicitud. La restauración ocurre una sola vez por proceso, protegida con un candado, al encender (`lifespan` en `main.py`).
  - Si subir la base falla después de agregar FAQs, las FAQs quedan y la respuesta trae un aviso. `KnowledgeService` ahora conserva los avisos que vienen de la base.
  - `GET /api/v1/status` informa `state_provider`.
  - Nueva herramienta `python -m communitylab_backend.tools.sync_state subir|bajar`, para cargar la memoria inicial al bucket o traer la del servidor.
  - **Despliegue:** `despliegue/huggingface/Dockerfile` (Python 3.13; clona las dos ramas de GitHub e instala el motor y el panel juntos) y `despliegue/huggingface/arrancar.sh` (arma `~/.oci/config` con los secretos del Space, enciende el motor solo hacia adentro y el panel hacia afuera, y reinicia el contenedor si uno de los dos se cae).
  - `.gitattributes`: los `.sh` y el `Dockerfile` siempre con fin de línea LF, porque se ejecutan en Linux.
  - Guía paso a paso: [despliegue-hugging-face.md](despliegue-hugging-face.md).
- **Por qué así:** la memoria vive en OCI y el servidor solo ejecuta. Se puede cambiar de proveedor de hosting sin perder nada, y OCI pasa a ser el corazón del proyecto: paquetes, conocimiento, memoria y claves. Se respetó la arquitectura hexagonal, porque la memoria remota es solo otro adaptador.
- **Verificación:**
  - 7 pruebas nuevas en `tests/backend/test_oci_state.py`, con un bucket falso:
    - restaurar un archivo de 3 MB por partes;
    - primer arranque sin copia en el bucket;
    - un 403 detiene sin filtrar identificadores;
    - las subidas ocurren solo cuando algo cambió;
    - aviso si falla la subida;
    - la restauración ocurre una sola vez al armar el motor.
  - En total pasan 101 pruebas y `documentation_check` está completo.
  - Se confirmó en el SDK de OCI instalado que `get_object` entrega el contenido por partes (`data.raw.stream`).
  - **Motor encendido con `STATE_PROVIDER=oci` y una configuración de OCI inválida:** `/health` responde, `/status` informa `state_provider: oci`, y el ranking y el procesamiento responden 503 con "No se pudo iniciar la sesión con OCI". No se escribió ningún paquete.
  - **`arrancar.sh`:** con una llave de prueba generada en el momento, armó un `~/.oci/config` que el SDK de OCI valida. También funciona con la llave en base64 y, si falta un secreto, lo nombra.
  - Las librerías del motor y del panel se instalan juntas en Python 3.13 sin conflictos (93 paquetes, `oci 2.140.0`).
  - **No se probó** contra una cuenta real de OCI ni en Hugging Face, porque no hay credenciales ni Docker en el entorno de trabajo.
- **Archivos:** `infrastructure/oci_state.py` (nuevo), `api/dependencies.py`, `application/knowledge.py`, `main.py`, `config/settings.py`, `tools/sync_state.py` (nuevo), `.env.example`, `.gitattributes` (nuevo), `despliegue/huggingface/Dockerfile` (nuevo), `despliegue/huggingface/arrancar.sh` (nuevo), `tests/backend/test_oci_state.py` (nuevo), `docs/despliegue-hugging-face.md` (nuevo), `README.md`, `docs/instalacion.md`, `docs/registro-de-funciones.md`.

## 8. Pendientes

| Pendiente | Quién lo destraba |
|---|---|
| Probar `STORAGE_PROVIDER=oci` contra el bucket real (`python -m communitylab_backend.tools.check_oci`) y revisar que `formato_briefing.almacenamiento_oci` muestre el bucket | Quien tiene las credenciales de la cuenta OCI |
| ~~Probar `LLM_PROVIDER=gemini` con la clave del equipo~~ **Hecho:** los 7 ejemplos se procesaron con `gemini-3.1-flash-lite` (`salidas/respuestas_gemini/`) | — |
| ~~Construir el índice semántico y probar `RETRIEVAL_PROVIDER=semantic`~~ **Hecho** con Cohere real (cambio 19) | — |
| Agregar pruebas unitarias para `route` con varias rutas, `compose`, `InteractionRules` y `briefing_format` | Equipo de backend (hoy se verificaron a mano y con los ejemplos) |
| Ajustar con el equipo de comunidad los pesos de relevancia y las palabras de frustración del modo local | Equipo de comunidad y marketing |
| Crear el Vault, los secretos, el grupo dinámico y la política, y probar `SECRET_PROVIDER=oci` en el servidor (pasos en `docs/secretos.md`) | Quien administra la cuenta OCI |
| Publicar el Space siguiendo [despliegue-hugging-face.md](despliegue-hugging-face.md) y probar la memoria en OCI con la cuenta real | Quien tiene las credenciales de OCI |
| OCI Vector Store | Siguiente etapa (opcional en el briefing) |
| Pruebas de aceptación y de punta a punta | Se dejaron fuera de esta etapa por tiempo |
