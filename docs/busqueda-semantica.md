# Búsqueda semántica de FAQs (Embed + Rerank)

Este documento explica cómo el Motor FAQ encuentra las preguntas frecuentes más parecidas a lo que escribe un estudiante, usando los adaptadores de Cohere.

## ¿Qué problema resuelve?

Hasta ahora el recuperador era un mock que devolvía una lista vacía. Sin evidencia, Gemini no tiene en qué basar la respuesta. La búsqueda semántica encuentra FAQs por **significado**, no por palabras exactas: "no me abre el notebook" puede encontrar "How do I run Jupyter?".

## Flujo

```
pregunta del estudiante
   │
   ▼
1. Embed (Cohere)        convierte la pregunta en un vector (search_query)
   │
   ▼
2. Índice local          compara con los vectores de las FAQs (similitud coseno)
   │                     → 20 candidatas
   ▼
3. Rerank (Cohere)       reordena las candidatas por relevancia real
   │
   ▼
4. Top N citas           pasan a Gemini como evidencia para redactar
```

Cada consulta gasta **2 llamadas a Cohere** (una de embed y una de rerank). Las FAQs se convierten en vectores **una sola vez**, al construir el índice.

## Piezas y archivos

| Pieza | Archivo | Papel |
|---|---|---|
| Recuperador | `application/retrieval.py` | Orquesta embed → búsqueda → rerank. Solo usa puertos del dominio |
| Almacén vectorial | `infrastructure/vector_index.py` | Lee el índice JSON y busca por similitud coseno |
| Constructor del índice | `tools/build_faq_index.py` | Lee las FAQs de la base, calcula vectores y escribe el JSON |
| Prueba rápida | `tools/search_faq.py` | Busca una pregunta desde la terminal |
| Composición | `api/dependencies.py` | `build_retriever` elige el recuperador según la configuración |

## Configuración

```env
RETRIEVAL_PROVIDER=semantic       # mock | existing_local | semantic
EMBEDDING_PROVIDER=cohere         # obligatorio con semantic
RERANKER_PROVIDER=cohere          # obligatorio con semantic
COHERE_API_KEY=tu_clave
FAQ_INDEX_PATH=data/faq_index.json
RETRIEVAL_CANDIDATES=20           # candidatas que recibe el reranker
COHERE_EMBED_DIMENSION=           # vacío = dimensión por defecto del modelo (1536)
```

El valor por defecto de `RETRIEVAL_PROVIDER` sigue siendo `mock`: nada cambia si no se configura.

## Construir el índice (una vez)

La base `motor_educativo.db` está en la rama `feature/data`. Desde la raíz del repo, con el entorno virtual activo y `COHERE_API_KEY` en el `.env`:

```bash
git show origin/feature/data:motor_educativo.db > /tmp/motor_educativo.db
python -m communitylab_backend.tools.build_faq_index --db /tmp/motor_educativo.db --out data/faq_index.json
```

- Lee las filas con `is_faq = 1` y deja **una copia por pregunta** (la base repite 4 preguntas en varios cursos: 145 filas, 141 preguntas únicas).
- Hace 2 llamadas a Cohere (lotes de 96 textos).
- Hay que **reconstruir el índice** si cambian las FAQs, el modelo de embeddings o la dimensión. Si la consulta y el índice tienen dimensiones distintas, la búsqueda falla con un mensaje que lo indica.

## Probar

Desde la terminal (2 llamadas a Cohere por ejecución):

```bash
python -m communitylab_backend.tools.search_faq "¿Qué es un proceso de decisión de Markov?" --limit 3
```

Desde la API, con `RETRIEVAL_PROVIDER=semantic`:

```bash
curl -X POST http://localhost:8000/api/v1/rag/query -H "Content-Type: application/json" -d '{"query": "¿Qué es un MDP?", "limit": 3}'
```

Con la búsqueda activa, `POST /api/v1/activity/process` también usa esta evidencia para generar los borradores de la ruta FAQ.

## Errores

| Situación | Resultado HTTP |
|---|---|
| Cohere sin clave, sin cuota o caído | 503 (`ProviderUnavailableError`) |
| Índice ausente, dañado o de otra dimensión | 502 (`RetrievalError`) |
| Consulta vacía | Lista vacía, sin llamadas a Cohere |

Si Cohere falla, `process` falla completo con 503: no se inventa evidencia.

## Limitaciones conocidas

- Las FAQs de la base están **en inglés**. Los modelos de Cohere son multilingües, pero hay que verificar con preguntas reales en español que la calidad sea buena.
- El índice vive en un archivo local. Para el despliegue hay que decidir dónde se guarda (por ejemplo, junto a la aplicación o en OCI Object Storage); el contrato `VectorStorePort` permite cambiarlo sin tocar el recuperador.
- La clave de prueba de Cohere permite 1.000 llamadas al mes, compartidas por todo el equipo. Cada solicitud de `process` gasta 2 de Cohere.
- La sanitización de la consulta en `/rag/query` y `/process` usa `dataset_builder.pii`, que todavía falta en el repositorio. El índice de FAQs no la necesita porque las FAQs no contienen datos personales (se revisó que no tengan correos, teléfonos ni enlaces).
