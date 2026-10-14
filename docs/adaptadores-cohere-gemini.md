# Adaptadores de Cohere y Gemini

Este documento explica los adaptadores que conectan el backend de Community Lab con **Cohere** (embeddings y reranking) y **Gemini** (análisis y generación de contenido), cómo configurarlos y cómo probarlos.

## ¿Qué problema resuelven?

El backend usa una arquitectura hexagonal: el dominio define *puertos* (interfaces) y la infraestructura los implementa con *adaptadores*. Antes de este cambio, Cohere y Gemini eran solo *stubs* que fallaban al usarse. Ahora hay implementaciones reales, intercambiables con los mocks sin tocar el dominio ni el grafo.

| Puerto (dominio) | Adaptador | Archivo |
|---|---|---|
| `EmbeddingProvider` | `CohereEmbeddingAdapter` | `infrastructure/cohere_adapters.py` |
| `RerankerProvider` | `CohereRerankerAdapter` | `infrastructure/cohere_adapters.py` |
| `LLMProvider` | `GeminiLLMAdapter` | `infrastructure/gemini_adapter.py` |

Cada proveedor vive en su propio módulo. `external_stubs.py` no se modificó; se eliminará en una limpieza final cuando todos los adaptadores estén integrados.

## Papel de cada pieza en el Motor FAQ

1. **Embed (Cohere):** convierte las FAQs y la pregunta del usuario en vectores numéricos.
2. **Búsqueda vectorial:** encuentra las FAQs más cercanas a la pregunta (pieza separada, no incluida aquí).
3. **Rerank (Cohere):** reordena esos candidatos por relevancia real.
4. **Gemini:** analiza el lote de mensajes y redacta los borradores a partir de las citas recuperadas.
5. **Object Storage:** guarda el paquete resultante (pieza separada).

## Cohere

### `CohereEmbeddingAdapter`
- `embed_documents(textos)`: devuelve un vector por texto, en el mismo orden. Divide en lotes de 96 y usa `input_type="search_document"`. Una lista vacía no hace ninguna llamada.
- `embed_query(texto)`: devuelve el vector de una consulta con `input_type="search_query"`. Un texto vacío produce un error.
- Modelo por defecto: `embed-v4.0` (configurable).

### `CohereRerankerAdapter`
- `rerank(consulta, candidatos)`: devuelve las mismas citas (`Evidence`) ordenadas de mayor a menor relevancia, con `score` actualizado y `record_id` intacto.
- Con 0 o 1 candidato no llama a Cohere, para ahorrar cuota.
- Valida que Cohere devuelva índices válidos y sin repetir.
- Modelo por defecto: `rerank-v4.0-pro` (configurable).

## Gemini

### `GeminiLLMAdapter`
- `analyze(interacciones)`: **una** llamada por lote. Devuelve sentimiento general, temas, ideas y dos señales (posible historia de éxito, pregunta recurrente). Un lote vacío no llama al proveedor.
- `generate(ruta, analisis, interacciones, evidencia)`: **una** llamada. Devuelve exactamente los dos formatos de la ruta:

| Ruta | Formatos |
|---|---|
| `faq` | `faq_content` + `newsletter_highlight` |
| `success_story` | `success_story` + `linkedin_post` |
| `community_highlight` | `linkedin_post` + `newsletter_highlight` |

- Cada solicitud completa gasta **2 llamadas** a Gemini. Con la cuota gratuita (20 llamadas al día) alcanza para unas 10 solicitudes diarias.
- Modelo por defecto: `gemini-3.8-flash` (configurable).

### Salvaguardas
- Las interacciones y las citas se envían dentro de etiquetas como **datos**, y se escapan los caracteres `<` y `>` para frenar intentos de inyección de instrucciones.
- Los borradores salen siempre en estado `draft`: requieren revisión humana.
- Los `evidence_ids` que Gemini invente y no existan en la evidencia se descartan.
- Si falta alguno de los dos formatos o el JSON es inválido, se produce `AssetGenerationError`.
- El modelo recibe solo texto sanitizado, nunca autor ni texto original.

## Manejo de errores

Ningún error del SDK se propaga tal cual: se traduce a un error de dominio con mensaje seguro (sin claves, prompts ni cabeceras).

| Situación | Error |
|---|---|
| Falta la clave o el SDK | `ProviderUnavailableError` |
| Límite de uso (HTTP 429) | `ProviderUnavailableError` ("alcanzó su límite de uso") |
| Servicio caído o respuesta incompleta | `ProviderUnavailableError` |
| Gemini no devuelve los formatos pedidos | `AssetGenerationError` |

La API los convierte en 503 y 502 respectivamente. No hay reintentos automáticos, porque cada reintento también consume cuota.

## Configuración

Variables de entorno (se leen de `.env`; **nunca** subas ese archivo al repositorio):

```env
LLM_PROVIDER=gemini            # mock | gemini
GEMINI_API_KEY=tu_clave
GEMINI_MODEL=gemini-3.8-flash

EMBEDDING_PROVIDER=cohere      # mock | cohere
RERANKER_PROVIDER=cohere       # mock | cohere
COHERE_API_KEY=tu_clave
COHERE_EMBED_MODEL=embed-v4.0
COHERE_RERANK_MODEL=rerank-v4.0-pro

PROVIDER_TIMEOUT_SECONDS=30
```

Por defecto todo usa `mock`, así que el backend arranca sin claves ni red.

## Estado de la integración

- `LLM_PROVIDER=gemini` ya está conectado en `api/dependencies.py`.
- Los adaptadores de Cohere están implementados y probados, pero **todavía no están conectados al buscador**: hoy el recuperador usa mocks y no consume embeddings ni reranking. Ese es el siguiente paso.
- Pendiente de confirmar: el nombre exacto del modelo de embeddings en la API directa de Cohere.
- Plan B si se agota la cuota de Gemini: generar con Cohere (aún no implementado).

## Ejemplo de uso

```python
from communitylab_backend.infrastructure.cohere_adapters import CohereEmbeddingAdapter, CohereRerankerAdapter

embeddings = CohereEmbeddingAdapter(api_key="...")
vectores = embeddings.embed_documents(["¿Cómo instalo Python?", "¿Cómo entrego el proyecto?"])
consulta = embeddings.embed_query("no puedo instalar python")

reranker = CohereRerankerAdapter(api_key="...", top_n=3)
ordenadas = reranker.rerank("no puedo instalar python", candidatos)  # lista de Evidence
```

## Pruebas

Las pruebas usan clientes falsos: no hacen llamadas de red ni gastan cuota.

```bash
pip install cohere google-genai pydantic pydantic-settings pytest
python -m pytest tests/backend -q
python -m communitylab_backend.documentation_check
```

Archivos: `tests/backend/test_cohere_adapters.py` y `tests/backend/test_gemini_adapter.py`.
