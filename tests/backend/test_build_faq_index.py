"""Pruebas de la construcción del índice de FAQs desde la base SQLite."""

import sqlite3

import pytest

from communitylab_backend.domain.errors import RetrievalError
from communitylab_backend.infrastructure.vector_index import LocalVectorStore
from communitylab_backend.tools.build_faq_index import build_index, load_faq_records


class FakeEmbeddings:
    """Embeddings falsos: el vector depende de la longitud del texto."""

    def __init__(self):
        """Inicializa el registro de textos recibidos."""
        self.received = []

    def embed_documents(self, texts):
        """Registra los textos y devuelve un vector de dos valores por texto."""
        self.received.extend(texts)
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, text):
        """No se usa en estas pruebas."""
        return [1.0, 1.0]


def make_db(tmp_path, rows):
    """Crea una base mínima con la tabla de contenido educativo."""
    path = tmp_path / "motor.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE contenido_educativo (reviews TEXT, faq_answer TEXT, course_id TEXT, is_faq INTEGER)")
        connection.executemany("INSERT INTO contenido_educativo VALUES (?, ?, ?, ?)", rows)
    return path


ROWS = [
    ("What is MDP?", "Un marco matemático.", "rl", 1),
    ("what is mdp?", "Otra redacción de la respuesta.", "ml", 1),
    ("Great course!", None, "rl", 0),
    ("What is NLP?", "Procesamiento de lenguaje.", None, 1),
    ("Sin respuesta", "", "rl", 1),
]


def test_load_records_dedupes_and_skips_incomplete_rows(tmp_path):
    """Deja una copia por pregunta (sin distinguir mayúsculas), descarta reseñas no FAQ y FAQs sin respuesta."""
    records = load_faq_records(make_db(tmp_path, ROWS))
    assert [record["snippet"] for record in records] == ["Pregunta: What is MDP?\nRespuesta: Un marco matemático.", "Pregunta: What is NLP?\nRespuesta: Procesamiento de lenguaje."]
    assert records[0]["source"] == "faq:rl" and records[1]["source"] == "faq:general"


def test_build_index_writes_searchable_file(tmp_path):
    """Indexa las FAQs con embeddings y el archivo resultante se puede buscar."""
    embeddings, out = FakeEmbeddings(), tmp_path / "out" / "index.json"
    count = build_index(make_db(tmp_path, ROWS), out, embeddings, "modelo-falso")
    assert count == 2 and len(embeddings.received) == 2
    assert len(LocalVectorStore(out).search([1.0, 1.0], 5)) == 2


def test_missing_db_empty_db_and_wrong_schema_fail_cleanly(tmp_path):
    """Base ausente, sin FAQs o con otro esquema producen RetrievalError."""
    with pytest.raises(RetrievalError):
        load_faq_records(tmp_path / "no-existe.db")
    with pytest.raises(RetrievalError):
        load_faq_records(make_db(tmp_path, [("Great", None, "rl", 0)]))
    other = tmp_path / "otra.db"
    sqlite3.connect(other).execute("CREATE TABLE otra (x)").connection.close()
    with pytest.raises(RetrievalError):
        load_faq_records(other)
