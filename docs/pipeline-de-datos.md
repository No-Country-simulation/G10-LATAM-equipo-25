# 🧠 Data Pipeline & AI Sentiment Engine — CommunityLab

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white)
![Hugging Face](https://img.shields.io/badge/Hugging%20Face-FFD21E?style=for-the-badge&logo=huggingface&logoColor=000)
![SQLite](https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white)

Esta rama (`feature/data`) orquesta todo el proceso de **Data Engineering (ETL) y Procesamiento de Lenguaje Natural (NLP)** necesario para generar la base de conocimiento que alimenta el backend y el sistema RAG del equipo 25 (CommunityLab).

## 🚀 Arquitectura del Pipeline

El script automatizado toma datos crudos, los purifica y los enriquece a través del siguiente flujo de trabajo:

1. **Extracción y Poda Estratégica:** Filtra un dataset de +270MB aislando exclusivamente contenido de alta relevancia (*Data Science, Machine Learning, Deep Learning, Neural Networks*).
2. **Data Interleaving (Inyección de FAQ):** Fusiona orgánicamente reseñas humanas con contenido educativo estructurado (FAQ) en una proporción exacta de 1:20.
3. **Análisis de Sentimiento Multilingüe (Zero-Shot):** Utiliza Inteligencia Artificial local (`XLM-RoBERTa`) para analizar el sentimiento de cada reseña. El modelo soporta +100 idiomas de forma nativa, eliminando la dependencia de APIs externas (como Gemini) y evitando errores de Rate Limit o Latencia de Red.
4. **Empaquetado SQL:** Consolida los datos procesados en una base de datos relacional ultraligera lista para el consumo del Backend.

---

## 🗂️ Estructura del Repositorio

| Archivo | Descripción |
|---------|-------------|
| 📜 `coursera.py` | El script principal (ETL + IA). Refactorizado para uso en producción (CPU/GPU Agnostic). |
| 🗄️ `motor_educativo.db` | **[ENTREGABLE]** La base de datos SQLite final, lista para conectarse al RAG. |
| 📊 `datafaq_enriched.csv` | Archivo semilla con las FAQs estructuradas por curaduría. |

> ⚠️ **Nota de Arquitectura:** Siguiendo las mejores prácticas de Git, el archivo crudo original (`Coursera_reviews.csv` - 272 MB) fue excluido del repositorio para evitar la saturación del control de versiones. El pipeline asume su presencia local si se desea reprocesar desde cero.

---

## 💾 Contrato de Datos (Esquema de la BD)

El backend consumirá el archivo `motor_educativo.db`, el cual expone la tabla `contenido_educativo` con el siguiente esquema optimizado para búsquedas vectoriales/semánticas:

| Columna | Tipo | Detalles |
|---------|------|----------|
| `reviews_clean` | `TEXT` | Texto normalizado y en minúsculas. Contiene la opinión del alumno o la pregunta del FAQ. Ideal para _Embeddings_. |
| `faq_answer` | `TEXT` | Respuesta curada. Contiene valor `NULL` si el registro es una reseña humana. |
| `is_faq` | `INT` | Booleano (`1` o `0`). Facilita al Backend filtrar entre contexto orgánico y respuestas oficiales. |
| `sentiment` | `TEXT` | Clasificación del modelo de IA (`Positivo`, `Negativo`, `Neutral`, o `FAQ Educativo`). |
| `course_id` | `TEXT` | Dominio específico del conocimiento (ej. `machine-learning`). |
| `rating` | `FLOAT`| Calificación original (1.0 - 5.0). |

---

## ⚙️ Reproducibilidad (Solo para desarrollo)

Si se desea ejecutar el pipeline de procesamiento de datos desde cero, instalar las dependencias necesarias:

```bash
pip install pandas numpy transformers torch tqdm
python coursera.py
