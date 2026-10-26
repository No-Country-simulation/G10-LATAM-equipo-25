"""Pruebas de la carga de FAQs nuevas y de la consulta de la base, con una base temporal."""

import json
import sqlite3

import pytest

from communitylab_backend.application.faq_import import clean_faq_rows, read_faq_file
from communitylab_backend.domain.errors import InvalidInteractionError
from communitylab_backend.infrastructure.faq_database import SqliteFaqRetriever, add_faqs, database_summary, list_reviews

SCHEMA = 'CREATE TABLE "contenido_educativo" ("reviews" TEXT, "reviewers" TEXT, "date_reviews" TIMESTAMP, "rating" INTEGER, "course_id" TEXT, "faq_answer" TEXT, "is_faq" INTEGER, "reviews_clean" TEXT, "sentiment" TEXT)'


@pytest.fixture
def base(tmp_path):
    """Crea una base con 2 FAQs y 3 reseñas (una repetida) con el esquema real."""
    path = tmp_path / "motor_educativo.db"
    with sqlite3.connect(path) as connection:
        connection.execute(SCHEMA)
        connection.executemany("INSERT INTO contenido_educativo VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            ("What is outlier detection?", "Data Scientist", "2018-06-21 00:00:00", 5, "capstone", "Outliers are unusual points.", 1, "what is outlier detection", "FAQ Educativo"),
            ("What is overfitting?", "AI Support", "2019-01-01 00:00:00", 5, "ml", "Overfitting memorizes training data.", 1, "what is overfitting", "FAQ Educativo"),
            ("Great course, write me at ana@correo.com", "By Ana P", "2020-01-02 00:00:00", 5, "ml", None, 0, "", "Positivo"),
            ("Great course, write me at ana@correo.com", "By Ana P", "2020-01-02 00:00:00", 5, "ml", None, 0, "", "Positivo"),
            ("Too confusing", "By Leo R", "2020-01-03 00:00:00", 1, "ml", None, 0, "", "Negativo"),
        ])
    connection.close()
    return path


def contar(path, condicion):
    """Cuenta filas de la tabla que cumplen ``condicion``."""
    with sqlite3.connect(path) as connection:
        total = connection.execute(f"SELECT COUNT(*) FROM contenido_educativo WHERE {condicion}").fetchone()[0]
    connection.close()
    return total


def test_read_and_clean_accept_spanish_and_english_columns():
    """Lee CSV y JSON, completa el curso y separa las filas inválidas."""
    csv_rows = read_faq_file("faqs.csv", "pregunta,respuesta,curso\n¿Qué es LangGraph?,Un framework de grafos,\n,sin pregunta,x\n".encode("utf-8"))
    valid, invalid = clean_faq_rows(csv_rows)
    assert valid == [{"question": "¿Qué es LangGraph?", "answer": "Un framework de grafos", "course": "general"}]
    assert invalid == [{"row": 2, "reason": "Falta la pregunta o la respuesta"}]
    json_rows = read_faq_file("faqs.json", json.dumps({"faqs": [{"question": "Q", "answer": "A", "course": "c"}]}).encode("utf-8"))
    assert clean_faq_rows(json_rows)[0][0]["course"] == "c"
    with pytest.raises(InvalidInteractionError):
        read_faq_file("faqs.json", b"no es json")
    with pytest.raises(InvalidInteractionError):
        clean_faq_rows([])


def test_preview_does_not_write(base, tmp_path):
    """La vista previa informa, pero no crea copia ni cambia la base."""
    rows = [{"question": "¿Qué es LangGraph?", "answer": "Un framework.", "course": "langgraph"}]
    result = add_faqs(base, rows, tmp_path / "respaldos", dry_run=True)
    assert result["to_add"] == rows and result["added"] == 0 and result["backup"] is None
    assert contar(base, "is_faq = 1") == 2 and not (tmp_path / "respaldos").exists()


def test_add_backs_up_skips_duplicates_and_keeps_reviews(base, tmp_path):
    """Copia la base antes, agrega sólo lo nuevo, no toca reseñas y el buscador lo encuentra."""
    rows = [
        {"question": "¿Cómo estructuro un router en LangGraph?", "answer": "Usa add_conditional_edges hacia una función router.", "course": "langgraph"},
        {"question": "what is OVERFITTING?", "answer": "Repetida (otra mayúscula).", "course": "ml"},
        {"question": "¿Cómo estructuro un router en LangGraph?", "answer": "Repetida dentro de la carga.", "course": "langgraph"},
    ]
    result = add_faqs(base, rows, tmp_path / "respaldos")
    assert result["added"] == 1 and len(result["duplicates"]) == 2 and result["new_ids"] == ["faq-6"]
    assert contar(base, "is_faq = 1") == 3 and contar(base, "is_faq = 0") == 3
    assert contar(result["backup"], "is_faq = 1") == 2
    found = SqliteFaqRetriever(base, min_score=0.1).retrieve("router langgraph")
    assert found and found[0].record_id == "faq-6"


def test_reviews_are_listed_once_and_without_personal_data(base):
    """Las reseñas repetidas se muestran una vez y el correo queda oculto."""
    reviews = list_reviews(base)
    assert [review["author"] for review in reviews] == ["Leo R", "Ana P"]
    assert "[EMAIL]" in reviews[1]["text"] and "ana@correo.com" not in reviews[1]["text"]
    summary = database_summary(base)
    assert summary["reviews"] == 3 and summary["unique_reviews"] == 2 and summary["unique_faqs"] == 2
