"""Búsqueda de FAQs directamente en la base ``motor_educativo.db``.

Pertenece a infraestructura e implementa ``RetrieverPort``. Es el recuperador
por defecto del Motor FAQ: funciona sin claves ni red, porque lee la base
SQLite que entrega el equipo de datos y ordena las FAQs con BM25, el mismo
tipo de puntaje que usan los buscadores clásicos.

Las FAQs de la base están en inglés y las dudas de la comunidad suelen venir
en español. Para acercar ambos idiomas, la consulta se enriquece con un
glosario corto de términos técnicos (por ejemplo, "sobreajuste" agrega
"overfitting"). Cuando se configura Cohere, la búsqueda semántica
(``RETRIEVAL_PROVIDER=semantic``) resuelve esa diferencia por significado.
"""

import math
import os
import re
import sqlite3
import unicodedata
from collections import Counter
from contextlib import closing
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from communitylab_backend.domain.errors import RetrievalError, StorageError
from communitylab_backend.domain.models import Evidence
from communitylab_backend.infrastructure.pii import sanitize

FAQ_QUERY = "SELECT rowid, reviews, faq_answer, course_id FROM contenido_educativo WHERE is_faq = 1 ORDER BY rowid"

# Puntaje mínimo para aceptar una FAQ como evidencia. Por debajo, la
# coincidencia es casual (una palabra suelta) y es mejor no citar nada.
MIN_SCORE = 5.0
_K1, _B = 1.5, 0.75

STOPWORDS = frozenset(
    "a al algo alguien and are as at be by como con cual cuando de del does el en es esa ese esta este for "
    "from hay how i in is it la las le lo los me mi my no o of on or para pero por que se si sin sobre "
    "some su the there this to tengo un una uno what when which why with y yo you".split()
)

# Glosario español -> inglés. La clave se busca en la consulta ya normalizada
# (minúsculas y sin tildes); el valor se agrega a la consulta.
GLOSSARY: dict[str, str] = {
    "diferencia": "difference",
    "aprendizaje automatico": "machine learning",
    "aprendizaje profundo": "deep learning",
    "aprendizaje por refuerzo": "reinforcement learning",
    "aprendizaje supervisado": "supervised learning",
    "aprendizaje no supervisado": "unsupervised learning",
    "red neuronal": "neural network",
    "redes neuronales": "neural networks",
    "convolucional": "convolutional cnn",
    "sobreajuste": "overfitting",
    "sobre ajuste": "overfitting",
    "regularizacion": "regularization",
    "ingenieria de caracteristicas": "feature engineering",
    "caracteristicas": "features",
    "escalado": "feature scaling",
    "normalizacion": "normalization scaling",
    "datos faltantes": "missing data",
    "valores faltantes": "missing data",
    "valores nulos": "missing data",
    "valores atipicos": "outlier detection",
    "atipicos": "outlier",
    "anomalias": "anomaly detection",
    "agrupamiento": "clustering",
    "clusterizacion": "clustering",
    "reduccion de dimensionalidad": "dimensionality reduction",
    "componentes principales": "pca principal component analysis",
    "procesamiento de lenguaje natural": "natural language processing nlp",
    "lenguaje natural": "natural language processing nlp",
    "analisis de sentimiento": "sentiment analysis",
    "analisis de sentimientos": "sentiment analysis",
    "entidades nombradas": "named entity recognition",
    "matriz de confusion": "confusion matrix",
    "validacion cruzada": "cross-validation",
    "arbol de decision": "decision tree",
    "bosque aleatorio": "random forest",
    "descenso de gradiente": "gradient descent",
    "funcion de activacion": "activation functions",
    "funciones de activacion": "activation functions",
    "retropropagacion": "backpropagation",
    "regresion lineal": "linear regression",
    "regresion": "regression",
    "clasificacion": "classification",
    "transferencia de aprendizaje": "transfer learning",
    "aumento de datos": "data augmentation",
    "ciencia de datos": "data science",
    "preprocesamiento": "preprocessing",
    "metricas": "evaluation metrics",
    "evaluar": "evaluate performance",
    "sesgo y varianza": "bias-variance tradeoff",
    "varianza": "variance",
    "desviacion estandar": "standard deviation",
    "correlacion": "correlation",
    "causalidad": "causation",
    "prueba de hipotesis": "hypothesis testing",
    "valor p": "p-value",
    "recompensa": "reward",
    "agente": "agent",
    "sistemas de recomendacion": "recommendation systems",
    "recomendacion": "recommendation",
    "atencion": "attention mechanism",
    "tiempo real": "real-time processing",
    "por lotes": "batch processing",
}


def _normalize(text: str) -> str:
    """Pasa ``text`` a minúsculas y quita tildes para comparar sin acentos."""
    decomposed = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _tokens(text: str) -> list[str]:
    """Divide ``text`` normalizado en palabras útiles, sin vacías ni plurales simples.

    Quita una ``s`` final en palabras largas para que "outliers" y "outlier"
    cuenten como la misma palabra. No tiene efectos secundarios.
    """
    words = re.findall(r"[a-z0-9]+", _normalize(text))
    return [word[:-1] if len(word) > 4 and word.endswith("s") else word for word in words if word not in STOPWORDS and len(word) > 1]


def expand_query(query: str) -> str:
    """Agrega a ``query`` los términos en inglés del glosario que encuentre.

    Retorna la consulta original más las traducciones, para que una duda en
    español pueda coincidir con una FAQ en inglés.
    """
    normalized = _normalize(query)
    extras = [english for spanish, english in GLOSSARY.items() if spanish in normalized]
    return " ".join([query, *extras])


def load_faq_records(db_path: Path) -> list[dict]:
    """Lee las FAQs de la base y devuelve una sola copia por pregunta.

    La base repite algunas preguntas en varios cursos; se conserva la primera.
    Cada registro trae ``record_id``, ``question``, ``answer``, ``snippet``
    (pregunta y respuesta) y ``source`` (el curso). Produce
    ``RetrievalError`` si la base no existe, no tiene la tabla esperada o no
    contiene FAQs. Abre la base sólo en modo lectura.
    """
    if not Path(db_path).is_file():
        raise RetrievalError("No se encontró la base de datos de FAQs")
    try:
        with sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True) as connection:
            rows = connection.execute(FAQ_QUERY).fetchall()
    except sqlite3.Error as exc:
        raise RetrievalError("La base de datos no tiene la tabla de FAQs esperada") from exc
    seen: set[str] = set()
    records = []
    for rowid, question, answer, course in rows:
        question, answer = (question or "").strip(), (answer or "").strip()
        if not question or not answer or question.casefold() in seen:
            continue
        seen.add(question.casefold())
        records.append({"record_id": f"faq-{rowid}", "question": question, "answer": answer, "snippet": f"Pregunta: {question}\nRespuesta: {answer}", "source": f"faq:{course or 'general'}"})
    if not records:
        raise RetrievalError("La base de datos no contiene FAQs")
    return records


@lru_cache(maxsize=4)
def _load_index(path: str, modified_ns: int) -> tuple[tuple[dict, ...], tuple[Counter, ...], dict[str, float], float]:
    """Lee las FAQs y prepara el índice BM25; se recalcula sólo si la base cambia.

    La pregunta cuenta doble frente a la respuesta, porque describe mejor el
    tema de cada FAQ. Retorna registros, frecuencias por documento, IDF y
    largo promedio. Produce ``RetrievalError`` si la base es inválida.
    """
    records = tuple(load_faq_records(Path(path)))
    documents = tuple(Counter(_tokens(record["question"]) * 2 + _tokens(record["answer"])) for record in records)
    total = len(documents)
    document_frequency = Counter(term for document in documents for term in document)
    idf = {term: math.log(1 + (total - count + 0.5) / (count + 0.5)) for term, count in document_frequency.items()}
    average = sum(sum(document.values()) for document in documents) / total
    return records, documents, idf, average


class SqliteFaqRetriever:
    """Implementa ``RetrieverPort`` con BM25 sobre las FAQs de ``motor_educativo.db``.

    Pertenece a infraestructura. No llama a servicios externos ni modifica la
    base. Nunca inventa citas: si ninguna FAQ supera ``MIN_SCORE`` devuelve
    una lista vacía y el generador deja la respuesta pendiente de revisión.
    """

    def __init__(self, db_path: Path, min_score: float = MIN_SCORE):
        """Recibe la ruta de la base; la lectura se difiere hasta ``retrieve``."""
        self.db_path = Path(db_path)
        self.min_score = min_score

    def retrieve(self, query: str, limit: int = 5) -> list[Evidence]:
        """Devuelve hasta ``limit`` FAQs ordenadas por relevancia para ``query``.

        ``query`` debe venir sanitizada. El ``score`` de cada cita es el
        puntaje BM25 (más alto, más parecida). Produce ``RetrievalError`` si
        la base no está disponible o no tiene el formato esperado.
        """
        terms = _tokens(expand_query(query or ""))
        if not terms:
            return []
        try:
            modified = os.stat(self.db_path).st_mtime_ns
        except OSError as exc:
            raise RetrievalError("No se encontró la base de datos de FAQs") from exc
        records, documents, idf, average = _load_index(str(self.db_path), modified)
        query_terms = Counter(terms)
        scored = []
        for record, document in zip(records, documents):
            length = sum(document.values())
            score = 0.0
            for term in query_terms:
                frequency = document.get(term, 0)
                if frequency:
                    score += idf[term] * frequency * (_K1 + 1) / (frequency + _K1 * (1 - _B + _B * length / average))
            if score >= self.min_score:
                scored.append((score, record))
        scored.sort(key=lambda row: row[0], reverse=True)
        return [Evidence(record["record_id"], record["snippet"], record["source"], round(score, 4)) for score, record in scored[:max(0, limit)]]


def _connect_read_only(db_path: Path) -> sqlite3.Connection:
    """Abre ``db_path`` sólo en modo lectura.

    Produce ``RetrievalError`` si el archivo no existe. Quien la usa debe
    cerrarla (``with closing(...)``): en Windows una conexión abierta puede
    bloquear el archivo.
    """
    if not Path(db_path).is_file():
        raise RetrievalError("No se encontró la base de datos de FAQs")
    return sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)


def database_summary(db_path: Path) -> dict:
    """Resume el contenido de ``motor_educativo.db`` para mostrarlo en el panel.

    Retorna el nombre del archivo, cuántas filas, FAQs (sin repetir) y reseñas
    tiene (y cuántas reseñas distintas, porque hay repetidas), cuántos cursos, el rango de fechas de las reseñas, su reparto por
    sentimiento (la etiqueta que calculó el equipo de datos) y por nota, y los
    cursos con más reseñas. Sólo lee. Produce ``RetrievalError`` si la base no
    existe o no tiene la tabla ``contenido_educativo``.
    """
    try:
        with closing(_connect_read_only(db_path)) as connection:
            total, faq_rows, reviews = connection.execute("SELECT COUNT(*), SUM(is_faq = 1), SUM(is_faq = 0) FROM contenido_educativo").fetchone()
            courses = connection.execute("SELECT COUNT(DISTINCT course_id) FROM contenido_educativo WHERE is_faq = 0").fetchone()[0]
            unique_reviews = connection.execute("SELECT COUNT(*) FROM (SELECT 1 FROM contenido_educativo WHERE is_faq = 0 GROUP BY reviewers, reviews)").fetchone()[0]
            first, last = connection.execute("SELECT MIN(date_reviews), MAX(date_reviews) FROM contenido_educativo WHERE is_faq = 0").fetchone()
            sentiment = dict(connection.execute("SELECT sentiment, COUNT(*) FROM contenido_educativo WHERE is_faq = 0 GROUP BY sentiment ORDER BY COUNT(*) DESC").fetchall())
            ratings = {str(rating): count for rating, count in connection.execute("SELECT rating, COUNT(*) FROM contenido_educativo WHERE is_faq = 0 GROUP BY rating ORDER BY rating DESC")}
            top = [{"course": course, "reviews": count} for course, count in connection.execute("SELECT course_id, COUNT(*) FROM contenido_educativo WHERE is_faq = 0 GROUP BY course_id ORDER BY COUNT(*) DESC, course_id LIMIT 8")]
    except sqlite3.Error as exc:
        raise RetrievalError("La base de datos no tiene la tabla esperada") from exc
    return {
        "file": Path(db_path).name, "total_rows": total, "faq_rows": faq_rows or 0, "unique_faqs": len(load_faq_records(db_path)),
        "reviews": reviews or 0, "unique_reviews": unique_reviews, "courses": courses, "date_range": [(first or "")[:10], (last or "")[:10]],
        "sentiment": sentiment, "ratings": ratings, "top_courses": top,
    }


def list_reviews(db_path: Path, course: str | None = None, sentiment: str | None = None, limit: int = 20) -> list[dict]:
    """Devuelve reseñas reales de la base, filtradas por curso y sentimiento.

    Cada reseña trae ``id``, ``author`` (sin el prefijo "By "), ``date``,
    ``rating``, ``course``, ``sentiment`` y ``text``. El texto pasa por el
    sanitizador de datos personales, igual que antes de llegar a la IA.
    Ordena por fecha, de la más reciente a la más antigua, y no repite
    reseñas idénticas (la base tiene algunas duplicadas). Produce
    ``RetrievalError`` si la base no está disponible.
    """
    query = "SELECT MIN(rowid), reviewers, date_reviews, rating, course_id, sentiment, reviews FROM contenido_educativo WHERE is_faq = 0 AND TRIM(COALESCE(reviews, '')) <> ''"
    params: list = []
    if course:
        query += " AND course_id = ?"
        params.append(course)
    if sentiment:
        query += " AND sentiment = ?"
        params.append(sentiment)
    # La base repite algunas reseñas idénticas: se muestra una sola vez cada una.
    query += " GROUP BY reviewers, reviews ORDER BY date_reviews DESC, MIN(rowid) LIMIT ?"
    params.append(max(1, min(limit, 100)))
    try:
        with closing(_connect_read_only(db_path)) as connection:
            rows = connection.execute(query, params).fetchall()
    except sqlite3.Error as exc:
        raise RetrievalError("La base de datos no tiene la tabla esperada") from exc
    rules = {key: True for key in ("email", "phone", "url", "ip", "user")}
    return [{"id": f"resena-{rowid}", "author": (author or "Anónimo").removeprefix("By ").strip(), "date": (date or "")[:10], "rating": rating, "course": course_id, "sentiment": label, "text": sanitize(" ".join((text or "").split()), rules)[0]} for rowid, author, date, rating, course_id, label, text in rows]


def list_courses(db_path: Path) -> list[str]:
    """Devuelve los cursos que tienen reseñas, en orden alfabético.

    Produce ``RetrievalError`` si la base no está disponible.
    """
    try:
        with closing(_connect_read_only(db_path)) as connection:
            return [row[0] for row in connection.execute("SELECT DISTINCT course_id FROM contenido_educativo WHERE is_faq = 0 AND course_id IS NOT NULL ORDER BY course_id")]
    except sqlite3.Error as exc:
        raise RetrievalError("La base de datos no tiene la tabla esperada") from exc


class SqliteKnowledgeBase:
    """Adaptador de ``KnowledgeBasePort`` sobre ``motor_educativo.db``.

    Pertenece a infraestructura. Sólo agrupa las funciones de este módulo
    (``database_summary``, ``load_faq_records``, ``list_reviews``,
    ``list_courses`` y ``add_faqs``) para que la aplicación no dependa de
    SQLite. ``backup_dir`` es la carpeta de las copias de seguridad.
    """

    def __init__(self, db_path: Path, backup_dir: Path):
        """Recibe las rutas; no abre la base hasta que se usa."""
        self.db_path, self.backup_dir = Path(db_path), Path(backup_dir)

    def summary(self) -> dict:
        """Totales de la base. Produce ``RetrievalError`` si no está disponible."""
        return database_summary(self.db_path)

    def faqs(self, limit: int) -> list[dict]:
        """Hasta ``limit`` FAQs oficiales sin repetir, en el orden de la base."""
        return [{key: record[key] for key in ("record_id", "question", "answer", "source")} for record in load_faq_records(self.db_path)[:limit]]

    def reviews(self, course: str | None, sentiment: str | None, limit: int) -> list[dict]:
        """Reseñas reales sin datos personales (ver ``list_reviews``)."""
        return list_reviews(self.db_path, course, sentiment, limit)

    def courses(self) -> list[str]:
        """Cursos que tienen reseñas (ver ``list_courses``)."""
        return list_courses(self.db_path)

    def add_faqs(self, rows: list[dict], dry_run: bool) -> dict:
        """Agrega FAQs con copia de seguridad previa (ver ``add_faqs``)."""
        return add_faqs(self.db_path, rows, self.backup_dir, dry_run=dry_run)


def _clean_text(question: str) -> str:
    """Versión en minúsculas y sin signos de una pregunta, como la columna ``reviews_clean``."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", question.lower())).strip()


def add_faqs(db_path: Path, rows: list[dict], backup_dir: Path, dry_run: bool = False) -> dict:
    """Agrega FAQs nuevas a ``motor_educativo.db`` sin tocar las reseñas.

    ``rows`` son FAQs ya validadas (``question``, ``answer``, ``course``). Se
    saltan las preguntas que ya existen en la base o que se repiten en la
    carga. Con ``dry_run`` sólo informa qué haría. Antes de escribir guarda
    una copia completa de la base en ``backup_dir`` y escribe todo en una
    sola transacción: si algo falla, la base queda como estaba. Retorna lo
    que se agregaría o agregó, las repetidas, los ids nuevos y la copia.
    Produce ``RetrievalError`` si la base no está disponible y
    ``StorageError`` si no se puede copiar o escribir.
    """
    existing = {record["question"].casefold() for record in load_faq_records(db_path)}
    to_add, duplicates = [], []
    for row in rows:
        key = row["question"].casefold()
        if key in existing:
            duplicates.append(row)
        else:
            existing.add(key)
            to_add.append(row)
    result = {"dry_run": dry_run, "to_add": to_add, "duplicates": duplicates, "added": 0, "new_ids": [], "backup": None}
    if dry_run or not to_add:
        return result
    db_path = Path(db_path)
    backup = Path(backup_dir) / f"{db_path.stem}-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}{db_path.suffix}"
    try:
        backup.parent.mkdir(parents=True, exist_ok=True)
        with closing(_connect_read_only(db_path)) as source, closing(sqlite3.connect(backup)) as target:
            source.backup(target)
    except (OSError, sqlite3.Error) as exc:
        raise StorageError("No se pudo crear la copia de seguridad de la base; no se agregó nada") from exc
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with closing(sqlite3.connect(db_path)) as connection, connection:
            for row in to_add:
                cursor = connection.execute(
                    "INSERT INTO contenido_educativo (reviews, reviewers, date_reviews, rating, course_id, faq_answer, is_faq, reviews_clean, sentiment) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (row["question"], "CommunityLab", now, 5, row["course"], row["answer"], _clean_text(row["question"]), "FAQ Educativo"),
                )
                result["new_ids"].append(f"faq-{cursor.lastrowid}")
    except sqlite3.Error as exc:
        raise StorageError("No se pudieron agregar las FAQs; la base quedó como estaba") from exc
    result.update(added=len(to_add), backup=backup.as_posix())
    return result
