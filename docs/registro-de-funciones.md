# Registro de funciones: para qué sirve cada una y por qué cambió

Este documento lista **cada función, clase y método del motor que se agregó, cambió o quitó** respecto de la versión original de la rama `feature/backend-ia-orchestration`. Para cada una dice para qué sirve y por qué se tocó, en palabras simples.

- La historia completa de cada cambio, con su verificación, está en [integracion-ramas.md](integracion-ramas.md). Aquí "cambio 12" significa "ver el cambio 12 de ese documento".
- Dentro del código, cada función tiene su propia explicación (docstring). `python -m communitylab_backend.documentation_check` comprueba que no falte ninguna.
- Las funciones que **no aparecen aquí** quedaron igual que en la rama original.

---

## 1. Cómo está organizado el código (arquitectura hexagonal)

La idea es que **el corazón del motor no dependa de ningún proveedor**. Si mañana se cambia Gemini por otro modelo, o SQLite por una base en la nube, solo se cambia la pieza de afuera; el corazón sigue igual.

```
            Quien pide algo                      Proveedores concretos
    (API, panel, herramientas de terminal)   (Gemini, Cohere, SQLite, OCI, carpeta local)
                     │                                       ▲
                     ▼                                       │ implementan
   ┌───────────────────────────────────┐        ┌────────────┴─────────────┐
   │ api/  y  tools/                   │        │ infrastructure/          │
   │ reciben pedidos y arman las piezas│        │ adaptadores              │
   └───────────────┬───────────────────┘        └────────────▲─────────────┘
                   ▼                                         │
   ┌───────────────────────────────────┐        ┌────────────┴─────────────┐
   │ application/                      │ ─usa─▶ │ domain/ports.py          │
   │ casos de uso: procesar un lote,   │        │ contratos ("qué se pide",│
   │ guardar la curaduría, ampliar la  │        │  no "quién lo hace")     │
   │ base de conocimiento              │        └──────────────────────────┘
   └───────────────────────────────────┘
                   │ usa
                   ▼
   ┌───────────────────────────────────┐
   │ domain/models.py  (datos del negocio: análisis, encargos, borradores) │
   └───────────────────────────────────┘
```

| Capa | Carpeta | Regla | ¿Se cumple? |
|---|---|---|---|
| Dominio | `domain/` | No conoce a nadie: solo datos y contratos | Sí. Solo importa la librería estándar |
| Aplicación | `application/` | Solo habla con contratos del dominio, nunca con un proveedor concreto | Sí. No importa nada de `infrastructure/` (revisado archivo por archivo) |
| Adaptadores | `infrastructure/` | Cada uno implementa un contrato (Gemini → `LLMProvider`, SQLite → `RetrieverPort`, etc.) | Sí |
| Entrada | `api/`, `tools/` | Reciben el pedido; `api/dependencies.py` es el único lugar que elige qué adaptador usar según el `.env` | Sí |

**Lo que se corrigió (cambio 20):** las consultas de la base de conocimiento (`/api/v1/knowledge/...`) llamaban directo a SQLite desde la API, y el historial de dudas entraba al flujo sin un contrato que lo describiera. Ahora existen los contratos `KnowledgeBasePort` y `DoubtHistoryPort`, el caso de uso `KnowledgeService` y el adaptador `SqliteKnowledgeBase`.

### Buenas prácticas que sigue el código

| Práctica | Cómo se aplica |
|---|---|
| **Ningún secreto en el código** | Las claves se leen del `.env` (que no se sube) o de OCI Vault. Los mensajes de error nunca muestran una clave |
| **Datos personales protegidos** | Correos, teléfonos, enlaces y menciones se ocultan **antes** de llegar a la IA. El autor nunca se envía a Gemini |
| **Revisión humana obligatoria** | Todo lo que redacta el motor sale como borrador (`draft`); nada se publica solo |
| **Errores claros y seguros** | Cada falla de un proveedor se traduce a un error del dominio con un mensaje entendible (422, 502 o 503), sin detalles internos |
| **Funciona sin internet** | Con el `.env` de ejemplo, todo corre en modo local; los servicios reales se activan con una variable |
| **Ahorro de cuota** | 2 consultas a Gemini por lote, sin importar cuántas rutas o temas tenga; textos recortados |
| **Escrituras seguras** | Antes de agregar FAQs a la base se guarda una copia completa, y todo se escribe en una sola transacción |
| **Pruebas sin costo** | 101 pruebas unitarias con versiones falsas de Gemini, Cohere y OCI: no gastan cuota ni necesitan red |
| **Todo documentado en español** | Cada módulo, clase y función tiene su explicación, y lo comprueba `documentation_check` |

---

## 2. Dominio (`domain/`)

### `domain/models.py`

| Nombre | Estado | Para qué sirve | Por qué cambió |
|---|---|---|---|
| `InteractionSignal` | Nueva | Lo que el motor concluye de **un** mensaje: sentimiento, categoría (logro, duda, apoyo, comentario), relevancia de 0 a 1, si la persona necesita apoyo y su tema | El briefing pide saber quién logró algo, quién necesita apoyo y elegir los mejores momentos (cambios 13 y 18) |
| `ContentBrief` | Nueva | Un "encargo" de contenido: qué ruta lo pide, qué piezas redactar, con qué mensajes y qué FAQs | Permite que varias rutas preparen su pedido y la IA los redacte todos juntos en una sola llamada (cambio 12) |
| `Analysis` | Cambiada | Resultado del análisis del lote completo | Suma la lista de señales por mensaje (cambio 13) |
| `DraftAsset` | Cambiada | Un borrador listo para revisión humana | Suma qué ruta lo encargó (`flow`) y de qué tema trata (`topic`) (cambios 12 y 18) |
| `BRIEF_KINDS`, `MAX_FAQ_TOPICS`, `FLOW_ORDER` | Nuevas (constantes) | Qué piezas pide cada ruta, cuántos temas de dudas se redactan por lote (2) y el orden de prioridad de las rutas | Tablas compartidas por el grafo y por los adaptadores, para que no haya dos versiones (cambios 12 y 18) |

### `domain/ports.py` (contratos)

| Nombre | Estado | Para qué sirve | Por qué cambió |
|---|---|---|---|
| `LLMProvider.analyze` | Cambiada | Pide al modelo el análisis del lote | Recibe los temas ya conocidos para que la IA reutilice sus nombres y se pueda contar la frecuencia (cambio 18) |
| `LLMProvider.generate_assets` | Nueva | Pide al modelo redactar **todos** los encargos de un lote de una vez | Una sola llamada por lote, aunque haya varias rutas (cambio 12) |
| `DoubtHistoryPort` y sus 4 métodos (`record`, `known_topics`, `attach_faqs`, `ranking`) | Nuevos | Contrato del historial de dudas: guardar dudas, decir qué temas se repiten, marcar un tema como resuelto y armar el ranking | Antes el historial entraba al flujo sin contrato (cambio 20) |
| `KnowledgeBasePort` y sus 5 métodos (`summary`, `faqs`, `reviews`, `courses`, `add_faqs`) | Nuevos | Contrato de la base de conocimiento: leer totales, FAQs y reseñas, y agregar FAQs nuevas | La API llamaba directo a SQLite (cambio 20) |

---

## 3. Aplicación (`application/`)

### `application/orchestration.py` (el grafo de LangGraph)

| Nombre | Estado | Para qué sirve | Por qué cambió |
|---|---|---|---|
| `ProcessingState` | Cambiada | La "mesa de trabajo" que comparten los pasos del grafo | Suma la lista de encargos (que se juntan de varias ramas en paralelo), los temas conocidos y las FAQs por tema (cambios 12 y 18) |
| `topic_key` | Nueva | Escribe un tema de forma estable (sin mayúsculas, tildes ni espacios de más) | Para que "LangGraph" y "langgraph " cuenten como el mismo tema en el ranking (cambio 18) |
| `_signals_by_id`, `_ranked` | Nuevas | Ayudantes: buscar la señal de cada mensaje y ordenar los mensajes por relevancia | Las ramas eligen los mensajes más relevantes (cambio 13) |
| `_question_topics` | Nueva | Agrupa las dudas del lote por tema, de la más pedida a la menos | Base del Motor de FAQ por tema (cambio 18) |
| `ProcessingWorkflow.__init__` | Cambiada | Arma el grafo con sus piezas | Nuevos pasos `compose` y ramas en paralelo; recibe el historial de dudas por su contrato (cambios 12, 18 y 20) |
| `ProcessingWorkflow._timed.run` | Cambiada | Mide cuánto tarda cada paso y lo registra | Ajuste para los pasos nuevos (cambio 12) |
| `ProcessingWorkflow._analyze` | Cambiada | Paso que pide el análisis al modelo | Le pasa los temas conocidos (cambio 18) |
| `ProcessingWorkflow._retrieve` | Cambiada | Paso que busca las FAQs oficiales | Busca **por tema** (2 citas por tema) en lugar de una búsqueda mezclada (cambio 18) |
| `ProcessingWorkflow._route` | Cambiada | Decide qué rutas se activan | Ahora puede activar **varias** a la vez y explica por qué (cambio 12) |
| `ProcessingWorkflow._selected_flows` | Nueva (reemplaza a `_selected_flow`) | Le dice a LangGraph qué ramas ejecutar | Devuelve una lista en vez de una sola ruta (cambio 12) |
| `ProcessingWorkflow._brief`, `_success_story_brief`, `_faq_brief`, `_community_brief` | Nuevas | Cada rama arma su encargo eligiendo los mensajes adecuados; la de FAQ arma uno por tema | Las ramas ya no llaman a la IA: solo preparan el pedido (cambios 12 y 18) |
| `ProcessingWorkflow._compose` | Nueva (reemplaza a `_generate`) | Redacta todos los encargos en una sola llamada y revisa que llegue cada pieza pedida | Ahorra cuota y permite varias rutas por lote (cambio 12) |
| `ProcessingWorkflow._persist` | Cambiada | Guarda el paquete del lote | También guarda los encargos (cambio 12) |
| `ProcessingWorkflow.invoke` | Cambiada | Ejecuta el grafo completo | Estado inicial con los campos nuevos (cambios 12 y 18) |

### `application/batch.py` (nuevo, cambio 8)

| Nombre | Para qué sirve | Por qué existe |
|---|---|---|
| `process_batch` | Procesa un lote: separa el autor (que nunca llega a la IA), ejecuta el grafo, guarda las dudas en el historial y arma la respuesta | La API y la herramienta de terminal dan exactamente la misma respuesta (cambios 8, 13 y 18) |
| `interaction_rows` | Une el análisis de cada mensaje con su autor y su canal | Para responder "quién" logró algo o necesita apoyo sin mandar el nombre a la IA (cambio 13) |
| `save_review` | Guarda lo que el equipo aprobó o rechazó en el panel | Registrar la revisión humana que pide el briefing (cambio 8) |

### `application/briefing_format.py` (nuevo, cambio 14)

| Nombre | Para qué sirve |
|---|---|
| `build_briefing_format` | Arma la respuesta con la estructura exacta del ejemplo de salida del briefing |
| `predominant_sentiment` | Traduce el sentimiento a las etiquetas del briefing ("Altamente Positivo", etc.) |
| `engagement_potential` | Estima el potencial de engagement (Alto, Medio, Bajo) con la relevancia del lote |
| `storage_summary` | Dice dónde quedó guardado el paquete, con los nombres del briefing |
| `_origin` | Arma el texto "Duda planteada por <autor> en <canal>" |

**Por qué existe:** para que quien evalúe pueda comparar la respuesta lado a lado con el ejemplo oficial.

### `application/knowledge.py` (nuevo, cambio 20)

| Nombre | Para qué sirve |
|---|---|
| `KnowledgeService` | Reúne todo lo que se puede hacer con la base de conocimiento, hablando solo con contratos |
| `KnowledgeService.summary`, `.faqs`, `.reviews` | Consultar la base: totales, FAQs oficiales y reseñas reales |
| `KnowledgeService.frequent_doubts` | Ranking de dudas frecuentes |
| `KnowledgeService.import_faqs` | Validar y agregar FAQs nuevas; si responden a un tema del ranking, lo marca resuelto; si la búsqueda inteligente está activa, actualiza su índice |

**Por qué existe:** antes esta lógica estaba dentro de la API y llamaba directo a SQLite. Ahora la API y la herramienta `import_faqs` usan el mismo servicio, y la base se podría cambiar sin tocar la API.

### `application/faq_import.py` (nuevo, cambio 17)

| Nombre | Para qué sirve |
|---|---|
| `read_faq_file` | Lee un CSV o JSON con FAQs nuevas |
| `clean_faq_rows` | Revisa cada fila (pregunta y respuesta obligatorias, largos máximos) y separa las válidas de las que tienen errores |
| `_pick` | Acepta columnas en español o en inglés (`pregunta` o `question`) |

### `application/ingestion.py` (nuevo, cambio 9)

| Nombre | Para qué sirve |
|---|---|
| `load_batch_file` | Lee un lote de mensajes desde un JSON o CSV |
| `clean_interactions` | Acepta los nombres del briefing en español o en inglés y descarta filas vacías |
| `_pick` | Toma el primer nombre de columna que exista |

### `application/retrieval.py` (de la rama `feature/semantic-retrieval`)

| Nombre | Estado | Para qué sirve | Por qué cambió |
|---|---|---|---|
| `SemanticRetriever.__init__` y `.retrieve` | Cambiadas | Búsqueda inteligente de FAQs con Cohere | Suma `min_score`: descarta FAQs poco relevantes. Con el valor por defecto se comporta igual que antes (cambio 19) |

---

## 4. Adaptadores (`infrastructure/`)

### `infrastructure/local.py` (modo local, sin IA)

| Nombre | Estado | Para qué sirve | Por qué cambió |
|---|---|---|---|
| `_plain`, `_words`, `_mentions` | Nuevas | Comparar palabras sin tildes ni mayúsculas | "quede seleccionada" debe reconocerse igual que "quedé seleccionada" (cambio 6) |
| `InteractionRules` (con `is_success`, `is_question`, `signal`) | Nueva | Calcula la señal de cada mensaje con reglas: tipo declarado, palabras clave, signos de pregunta y frases de frustración | Análisis por mensaje también sin IA (cambio 13) |
| `_answer_from` | Nueva | Separa pregunta y respuesta de una FAQ citada | Para armar el contenido con la respuesta oficial (cambio 6) |
| `MockLLMProvider` y `__init__` | Cambiadas | El "modelo de mentira" del modo local | Reconoce los tipos del briefing (`testimonio`, `pregunta_tecnica`…) (cambio 6) |
| `MockLLMProvider.analyze` | Cambiada | Análisis del lote con reglas | Suma la señal y el tema de cada mensaje (cambios 13 y 18) |
| `MockLLMProvider._is_question`, `._topics` | Nuevas | Detectar dudas y asignar temas con reglas | Cambios 6 y 18 |
| `MockLLMProvider.generate_assets` | Nueva | Redacta todos los encargos con plantillas | Implementa el contrato nuevo (cambio 12) |
| `MockLLMProvider._educational` | Nueva | Arma tutorial rápido, tip de la semana y tema de documentación de un tema | Motor de FAQ también sin IA (cambio 18) |
| `MockLLMProvider.generate`, `._faq` | Cambiada / nueva | Redacción por ruta (método anterior) | Usa la respuesta de la FAQ oficial mejor puntuada (cambio 6) |
| `LocalObjectStorageAdapter.__init__`, `.save` | Cambiadas | Guardar paquetes en una carpeta | Aceptan la carpeta escrita como texto y devuelven la ruta con `/` en cualquier sistema, para que el panel y el formato del briefing la muestren igual en Windows y en Linux. La carpeta por defecto pasó a `salidas/paquetes` (cambio 7) |
| `ExistingLocalRagAdapter` | **Quitada** | — | Dependía de un módulo que nunca llegó al repositorio y no funcionaba (cambio 2) |

### `infrastructure/gemini_adapter.py` (de la rama `feature/cohere-gemini-adapters`)

Los prompts, las salvaguardas y el método `generate` original **no cambiaron**. Se agregó:

| Nombre | Estado | Para qué sirve | Por qué |
|---|---|---|---|
| `SignalOutput` | Nueva | Formato que Gemini debe devolver para cada mensaje (incluido su tema) | Cambios 13 y 18 |
| `AnalysisOutput` | Cambiada | Formato del análisis del lote | Suma las señales por mensaje (cambio 13) |
| `BriefAssetOutput`, `BriefGenerationOutput` | Nuevas | Formato de la redacción de todos los encargos | Cambio 12 |
| `_render_brief` | Nueva | Presenta cada encargo a Gemini, con sus mensajes y FAQs como datos (no como instrucciones) | Cambio 12 |
| `_signals` | Nueva | Completa con reglas locales los mensajes que Gemini omita y descarta ids inventados | Cambio 13 |
| `GeminiLLMAdapter.analyze` | Cambiada | Análisis del lote | Pide también la señal y el tema de cada mensaje, en la **misma** llamada (cambios 13 y 18) |
| `GeminiLLMAdapter.generate_assets` | Nueva | Redacta todos los encargos en una sola llamada y descarta citas inventadas | Cambio 12 |
| `_render_interactions`, `_render_evidence` | Cambiadas | Presentan mensajes y FAQs a Gemini | Recortes a 600 y 400 caracteres para gastar menos (cambio 18) |

### `infrastructure/faq_database.py` (nuevo)

| Nombre | Para qué sirve | Cambio |
|---|---|---|
| `SqliteFaqRetriever` (y `retrieve`) | Busca la FAQ oficial que responde una duda, sin claves ni internet | 4 |
| `load_faq_records`, `_load_index`, `_normalize`, `_tokens`, `expand_query` | Leer las FAQs una sola vez por pregunta, preparar la búsqueda y traducir términos español-inglés | 4 |
| `database_summary`, `list_reviews`, `list_courses`, `_connect_read_only` | Mostrar qué hay en la base (solo lectura), con las reseñas sin datos personales y sin repetir | 16 |
| `add_faqs`, `_clean_text` | Agregar FAQs nuevas con copia de seguridad previa y sin tocar las reseñas | 17 |
| `SqliteKnowledgeBase` (y sus 5 métodos) | Cumple el contrato `KnowledgeBasePort` usando las funciones de arriba | 20 |

### `infrastructure/doubt_history.py` (nuevo, cambios 18 y 19)

| Nombre | Para qué sirve |
|---|---|
| `DoubtHistory.record` | Guarda cada duda con su tema, fecha y texto sin datos personales |
| `DoubtHistory.known_topics` | Dice qué temas ya se vieron, para que la IA use el mismo nombre |
| `DoubtHistory.ranking` | Arma el ranking de dudas frecuentes (sin IA, sin costo) |
| `DoubtHistory.attach_faqs` | Marca un tema como resuelto cuando el equipo agrega su FAQ |
| `DoubtHistory._connect` | Abre el archivo y crea la tabla si hace falta |

### `infrastructure/oci_state.py` (nuevo, cambio 22)

| Nombre | Para qué sirve |
|---|---|
| `OCIFileMirror.restore` | Al encender, baja del bucket la última copia del historial y de la base; si no existe, deja la local |
| `OCIFileMirror.save` | Sube un archivo de memoria al bucket |
| `OCIFileMirror.object_name`, `_translate_error` | Nombre del objeto (`estado/<archivo>`) y mensajes de error seguros |
| `MirroredDoubtHistory` (y sus 4 métodos) | Cumple `DoubtHistoryPort`: usa el historial local y lo sube a OCI después de cada cambio |
| `MirroredKnowledgeBase` (y sus 5 métodos) | Cumple `KnowledgeBasePort`: usa la base local y la sube a OCI después de agregar FAQs |

**Por qué existe:** para desplegar en un servidor cuyo disco se borra al reiniciar (Hugging Face Spaces) sin perder el ranking ni las FAQs aprendidas.

### Otros adaptadores

| Archivo | Origen | Estado |
|---|---|---|
| `infrastructure/pii.py` (`sanitize`) | Nuevo (cambio 1) | Oculta correos, teléfonos, enlaces, IPs y menciones. Reemplaza a un módulo que no existía y hacía que el motor no arrancara |
| `infrastructure/oci_vault.py` (`OCIVaultSecretProvider` y ayudantes) | Nuevo (cambio 15) | Lee las claves desde OCI Vault en producción, sin mostrarlas nunca |
| `infrastructure/cohere_adapters.py` | Rama `feature/cohere-gemini-adapters` | Sin cambios |
| `infrastructure/vector_index.py` | Rama `feature/semantic-retrieval` | Sin cambios |
| `infrastructure/oci_storage.py` | Rama `feature/oci-object-storage` | Sin cambios |
| `infrastructure/external_stubs.py` | Rama original | **Eliminado**: sus funciones de relleno ya tenían versión real (cambio 3) |

---

## 5. Entrada (`api/`, `main.py`, `tools/`)

### `api/dependencies.py` (el único lugar que elige proveedores)

| Nombre | Estado | Para qué sirve | Cambio |
|---|---|---|---|
| `build_workflow` | Cambiada | Arma el motor con los proveedores del `.env` | Usa la base de FAQs, el historial y las claves desde el `.env` u OCI Vault (4, 15, 18) |
| `build_retriever`, `build_storage` | Nuevas | Eligen la búsqueda (local o Cohere) y el almacenamiento (carpeta u OCI) | 4 |
| `get_api_key`, `build_secret_provider`, `_vault_provider` | Nuevas | Obtienen la clave de Gemini o Cohere del `.env` o de OCI Vault | 15 |
| `rebuild_semantic_index` | Nueva | Actualiza el índice de la búsqueda inteligente al agregar FAQs | 19 |
| `build_knowledge`, `get_knowledge` | Nuevas | Arman el servicio de la base de conocimiento | 20 y 22 |
| `build_state_mirror`, `_state_mirror`, `build_history` | Nuevas | Con `STATE_PROVIDER=oci`, restauran la memoria desde OCI una sola vez y envuelven el historial y la base para respaldarlos | 22 |

### `api/schemas.py` (forma de los datos que entran y salen)

| Nombre | Estado | Por qué |
|---|---|---|
| `InteractionInput`, `ProcessRequest` | Cambiadas | Aceptan los nombres del briefing en español (cambio 8) |
| `ProcessResponse` | Cambiada | Suma rutas, análisis por mensaje, mejores momentos, personas que necesitan apoyo, temas de FAQ y el formato del briefing (cambios 12 a 14 y 18) |
| `ReviewedAsset`, `ReviewRequest`, `ReviewResponse` | Nuevas | Guardar la curaduría del panel (cambio 8) |
| `FaqImportRequest` | Nueva | Agregar FAQs desde el panel (cambios 17 y 19) |

### `main.py` (direcciones de la API)

| Función | Dirección | Estado | Cambio |
|---|---|---|---|
| `process_activity` | `POST /api/v1/activity/process` | Cambiada: le pasa el autor a `process_batch` sin enviarlo a la IA | 8 y 13 |
| `status` | `GET /api/v1/status` | Nueva: qué proveedores están activos, sin claves; desde el cambio 22 también dónde vive la memoria | 8 y 22 |
| `lifespan` | (al encender) | Nueva: restaura la memoria desde OCI antes de la primera solicitud | 22 |
| `review_assets` | `POST /api/v1/assets/review` | Nueva: guarda la curaduría | 8 |
| `knowledge_summary`, `knowledge_faqs`, `knowledge_reviews` | `GET /api/v1/knowledge/...` | Nuevas: consultar la base | 16 y 20 |
| `import_faqs` | `POST /api/v1/knowledge/faqs/import` | Nueva: agregar FAQs | 17, 19 y 20 |
| `frequent_doubts` | `GET /api/v1/knowledge/frequent-doubts` | Nueva: ranking de dudas | 18 y 20 |

### `tools/` (herramientas de terminal)

| Herramienta | Origen | Para qué sirve | Cambio |
|---|---|---|---|
| `process_batch` | Nueva | Procesa lotes de ejemplo y guarda las respuestas | 9 y 13 |
| `import_faqs` | Nueva | Agrega FAQs desde un archivo; ahora usa `KnowledgeService` | 17 y 20 |
| `build_faq_index` | Rama `feature/semantic-retrieval` | Prepara el índice de la búsqueda inteligente; ahora lee la base con la misma función que el buscador y toma la clave del `.env` o del Vault | 5 y 15 |
| `search_faq` | Rama `feature/semantic-retrieval` | Busca una pregunta desde la terminal; toma la clave del `.env` o del Vault | 15 |
| `check_oci` | Rama `feature/oci-object-storage` | Prueba la conexión con el bucket | Sin cambios |
| `sync_state` | Nueva | Sube o baja la memoria del motor (historial y base) al bucket | 22 |

### `config/settings.py`

`Settings` suma las variables nuevas, todas con un valor por defecto que funciona en modo local: `FAQ_DB_PATH`, `FAQ_BACKUP_DIR`, `HISTORY_DB_PATH`, `RETRIEVAL_MIN_SCORE`, `OCI_VAULT_ID`, `OCI_SECRET_GEMINI`, `OCI_SECRET_COHERE`, `STATE_PROVIDER`, `OCI_STATE_PREFIX` y los tipos y palabras del briefing (cambios 7, 15, 17, 18, 19 y 22).

### `despliegue/huggingface/` (nuevo, cambio 22)

| Archivo | Para qué sirve |
|---|---|
| `Dockerfile` | Arma el contenedor del Space: Python 3.13, descarga las dos ramas de GitHub e instala el motor y el panel |
| `arrancar.sh` | Arma la configuración de OCI con los secretos, enciende el motor solo hacia adentro y el panel hacia afuera, y reinicia todo si uno se cae |

---

## 6. Pruebas (`tests/backend/`)

| Archivo | Estado |
|---|---|
| `test_gemini_adapter.py` | Solo cambió el JSON falso de una prueba, porque el esquema de Gemini ahora pide señales y temas (cambios 13 y 18) |
| `test_semantic_wiring.py`, `test_storage_wiring.py` | Ajustes de integración (cambio 10) |
| `test_semantic_retriever.py` | Suma una prueba del umbral `min_score` (cambio 19) |
| `test_oci_vault.py`, `test_faq_import.py`, `test_motor_faq.py`, `test_knowledge_service.py`, `test_oci_state.py` | Nuevos (cambios 15, 17, 18, 20 y 22) |

Todas son pruebas unitarias. No se agregaron pruebas de punta a punta ni de aceptación.
