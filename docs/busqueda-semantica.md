# Búsqueda semántica de FAQs (Embed + Rerank)

Este documento explica cómo el Motor FAQ encuentra las preguntas frecuentes más parecidas a lo que escribe un estudiante, usando los adaptadores de Cohere.

## ¿Qué problema resuelve?

Sin evidencia, Gemini no tiene en qué basar la respuesta. El buscador por defecto (`faq_db`, ver [motor-faq-base-de-datos.md](motor-faq-base-de-datos.md)) compara palabras; la búsqueda semántica va un paso más allá. La búsqueda semántica encuentra FAQs por **significado**, no por palabras exactas: "no me abre el notebook" puede encontrar "How do I run Jupyter?".

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
RETRIEVAL_PROVIDER=semantic       # faq_db | semantic | mock
EMBEDDING_PROVIDER=cohere         # obligatorio con semantic
RERANKER_PROVIDER=cohere          # obligatorio con semantic
COHERE_API_KEY=tu_clave
FAQ_INDEX_PATH=data/faq_index.json
RETRIEVAL_CANDIDATES=20           # candidatas que recibe el reranker
COHERE_EMBED_DIMENSION=           # vacío = dimensión por defecto del modelo (1536)
```

El valor por defecto de `RETRIEVAL_PROVIDER` es `faq_db`: si no se configura Cohere, se busca directamente en la base.

## Construir el índice (una vez)

La base `motor_educativo.db` ya está en `data/` (se copió de la rama `feature/data` en la integración). Desde la raíz del repo, con el entorno virtual activo y `COHERE_API_KEY` en el `.env`:

```bash
python -m communitylab_backend.tools.build_faq_index
```

Por defecto lee `data/motor_educativo.db` y escribe `data/faq_index.json`; `--db` y `--out` permiten cambiar las rutas.

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
- La sanitización de la consulta en `/rag/query` y `/process` usa `infrastructure/pii.py` (antes dependía de `dataset_builder.pii`, que nunca llegó al repositorio). El índice de FAQs no la necesita porque las FAQs no contienen datos personales (se revisó que no tengan correos, teléfonos ni enlaces).

## Prueba con Cohere real y umbral de relevancia (octubre 2026)

Se construyó el índice con las 141 FAQs y se compararon las dos búsquedas con 9 dudas reales:

| Duda | BM25 (`faq_db`) | Cohere (`semantic`) |
|---|---|---|
| ¿Cómo evito el sobreajuste en mi red neuronal? | faq-538 ✅ | faq-538 ✅ (0,92) |
| ¿Para qué sirve el dropout? | faq-2893 ✅ | faq-2893 ✅ (0,91) |
| ¿Rellenar faltantes con la media o borrar filas? | faq-1503 ✅ | faq-1503 ✅ (0,76) |
| Diferencia entre clasificación y regresión | faq-1572 ✅ | faq-1572 ✅ (0,97) |
| Aprendizaje supervisado y no supervisado | faq-3006 ✅ | faq-3006 ✅ (0,95) |
| What was the purpose of batch normalization? | faq-718 (batch vs. layer) | **faq-2067, la exacta** (0,92) |
| "Mi modelo funciona bien en entrenamiento pero mal con datos nuevos" | nada | **faq-1168 overfitting** (0,89) |
| Reintentos en un grafo de LangGraph (no hay FAQ) | nada ✅ | faq-2459 reinforcement learning ✗ (0,17) |
| ¿Watson Studio y Skills Network Lab? (no hay FAQ) | nada ✅ | faq-768 data science ✗ (0,36) |

- Las respuestas buenas puntúan 0,76 o más y las irrelevantes 0,36 o menos. Por eso `RETRIEVAL_MIN_SCORE=0.5`: con ese umbral, las dos últimas quedan correctamente sin cita.
- Cada búsqueda gasta 2 llamadas a Cohere (embed + rerank); el motor busca hasta 2 temas por lote, o sea hasta 4 llamadas por lote.
- Al agregar FAQs a la base con la búsqueda semántica activa, el índice se reconstruye solo (unas 2 llamadas).

Para activarla: en el `.env`, `RETRIEVAL_PROVIDER=semantic`, `EMBEDDING_PROVIDER=cohere`, `RERANKER_PROVIDER=cohere` y `COHERE_API_KEY`; construir el índice una vez con `python -m communitylab_backend.tools.build_faq_index`.
