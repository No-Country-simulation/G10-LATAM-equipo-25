# Motor FAQ sobre `motor_educativo.db`

Este documento explica cómo el backend encuentra la FAQ oficial que responde a una duda de la comunidad usando la base de datos del equipo, **sin claves ni internet**.

## ¿Qué problema resuelve?

Cuando un lote trae dudas, el grafo toma la ruta `faq` y genera un contenido de FAQ. Para que la respuesta no sea inventada, debe apoyarse en una **fuente oficial**: las FAQs curadas que el equipo de datos guardó en `motor_educativo.db`.

Antes de la integración había dos opciones de búsqueda:

- `mock`: no devolvía nada, así que la FAQ siempre quedaba "pendiente de revisión".
- `semantic`: muy buena, pero necesita clave de Cohere y construir un índice antes.

Ahora existe una tercera, `faq_db`, que es la opción por defecto: busca directamente en la base.

## La base de datos

`data/motor_educativo.db` viene de la rama `feature/data`. Tiene una tabla, `contenido_educativo`, con reseñas de cursos y FAQs mezcladas:

| Columna | Uso en el backend |
|---|---|
| `reviews` | Texto original. En las filas FAQ es **la pregunta** |
| `faq_answer` | **La respuesta oficial** (vacía en las reseñas) |
| `is_faq` | `1` = FAQ, `0` = reseña. Solo se leen las filas con `1` |
| `course_id` | Curso al que pertenece. Se muestra como fuente (`faq:machine-learning`) |
| `sentiment`, `rating`, `reviewers`, `date_reviews`, `reviews_clean` | No se usan en esta etapa |

Datos: 3,063 filas, de las cuales 145 son FAQ. Como algunas preguntas se repiten en varios cursos, quedan **141 preguntas únicas**. Las FAQs están **en inglés**.

## Cómo busca

```
duda de la comunidad (español, ya sin datos personales)
   │
   ▼
1. Glosario          agrega los términos en inglés que encuentre
   │                 "sobreajuste" → overfitting, "valores faltantes" → missing data
   ▼
2. BM25              compara las palabras con cada FAQ y les da un puntaje
   │                 (la pregunta de la FAQ pesa el doble que la respuesta)
   ▼
3. Umbral            descarta las FAQs con puntaje menor a 5
   │
   ▼
4. Top 5 citas       pasan al generador como evidencia
```

**BM25** es el método de puntaje que usan los buscadores clásicos: premia las palabras poco comunes que coinciden (por ejemplo "overfitting") y castiga las muy frecuentes (por ejemplo "learning", que aparece en casi todas las FAQs).

**El glosario** (`GLOSSARY` en `infrastructure/faq_database.py`) tiene unos 60 términos técnicos de machine learning y datos. Si una duda frecuente de la comunidad no encuentra su FAQ, lo primero que hay que revisar es si falta su término en el glosario.

**El umbral** (`MIN_SCORE = 5.0`) evita citar FAQs por coincidencias casuales. Por ejemplo, el testimonio del briefing ("marcó toda la diferencia en la entrevista") no debe traer la FAQ "What is the difference between classification and regression?". Si no hay ninguna FAQ por encima del umbral, la lista queda vacía y el contenido de FAQ dice "Respuesta pendiente de revisión humana con evidencia". **Nunca se inventa una cita.**

La base se abre en **modo solo lectura** y se carga en memoria una vez. Si el archivo cambia, se vuelve a leer automáticamente.

## Ejemplos reales

| Duda | FAQ encontrada |
|---|---|
| ¿Cómo evito el sobreajuste en mi red neuronal? | How does regularization prevent overfitting in neural networks? |
| ¿Cómo manejo los valores faltantes en mi dataset? | How do you handle missing data in a dataset? |
| ¿Cuál es la diferencia entre clasificación y regresión? | What is the difference between classification and regression? |
| ¿Qué es el procesamiento de lenguaje natural? | What is natural language processing (NLP)? |
| Quedé seleccionada para el puesto de Desarrolladora Junior | *(ninguna: no es una duda)* |

## Qué pasa después con la cita

- **Modo local (`LLM_PROVIDER=mock`):** el contenido de FAQ muestra las dudas de la comunidad y la respuesta oficial mejor puntuada **tal cual, en inglés**, con su identificador (`faq-538`).
- **Con Gemini (`LLM_PROVIDER=gemini`):** las citas se envían a Gemini, que redacta la respuesta en español, paso a paso, basándose **solo** en ellas. Esa regla está en el prompt `KIND_GUIDE["faq_content"]` de `gemini_adapter.py`.

En ambos casos, el activo guarda en `evidence_ids` qué FAQs lo respaldan, y el panel de curaduría las muestra en "Ver de dónde salió".

## Cómo elegir el buscador

| `RETRIEVAL_PROVIDER` | Necesita | Ventaja | Limitación |
|---|---|---|---|
| `faq_db` (por defecto) | Nada | Funciona sin claves ni red, es inmediato | Depende de palabras y del glosario |
| `semantic` | Clave de Cohere e índice construido | Entiende el significado aunque no coincidan las palabras | Gasta 2 llamadas de Cohere por consulta |
| `mock` | Nada | Útil para probar el flujo sin evidencia | No devuelve citas |

Para la búsqueda semántica, ver [busqueda-semantica.md](busqueda-semantica.md). El índice se construye desde la misma base:

```bash
python -m communitylab_backend.tools.build_faq_index
```

## Probar la búsqueda

Con la API encendida:

```bash
curl -X POST http://localhost:8000/api/v1/rag/query \
     -H "Content-Type: application/json" \
     -d '{"query": "¿Cómo evito el sobreajuste?", "limit": 3}'
```

O desde `http://localhost:8000/docs`, en el endpoint `POST /api/v1/rag/query`.

## Archivos

| Archivo | Papel |
|---|---|
| `data/motor_educativo.db` | Base de FAQs (rama `feature/data`) |
| `infrastructure/faq_database.py` | Lectura de la base, glosario, BM25 y `SqliteFaqRetriever` |
| `api/dependencies.py` | Elige el buscador según `RETRIEVAL_PROVIDER` |
| `tools/build_faq_index.py` | Usa la misma lectura de la base para el índice semántico |

## Errores

| Situación | Resultado |
|---|---|
| No existe el archivo de `FAQ_DB_PATH` | 502 (`RetrievalError`: "No se encontró la base de datos de FAQs") |
| La base no tiene la tabla `contenido_educativo` | 502 (`RetrievalError`) |
| Ninguna FAQ supera el umbral | No es un error: lista vacía y respuesta pendiente de revisión |

## Agregar FAQs nuevas

Además de reemplazar la base completa, se pueden sumar FAQs nuevas desde un CSV (`pregunta,respuesta,curso`) o un JSON, sin tocar las reseñas:

- **Desde el panel:** *Base de conocimiento → Agregar FAQs*. Primero se ve una vista previa y nada se escribe hasta confirmar.
- **Desde la terminal:**

  ```bash
  python -m communitylab_backend.tools.import_faqs ejemplos/faqs/faqs_nuevas_ejemplo.csv            # vista previa
  python -m communitylab_backend.tools.import_faqs ejemplos/faqs/faqs_nuevas_ejemplo.csv --aplicar  # escribe
  ```

Antes de escribir se guarda una copia completa de la base en `data/respaldos/` (no se sube a git). Para volver atrás basta con copiar ese archivo sobre `data/motor_educativo.db`. Las preguntas que ya existen no se repiten. El buscador usa las FAQs nuevas al instante.
