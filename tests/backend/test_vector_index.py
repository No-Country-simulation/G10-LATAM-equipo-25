"""Pruebas del almacén vectorial local y del índice JSON."""

import json
import os

import pytest

from communitylab_backend.domain.errors import RetrievalError
from communitylab_backend.infrastructure.vector_index import LocalVectorStore, write_index

RECORDS = [{"record_id": "a", "snippet": "A", "source": "faq:x"}, {"record_id": "b", "snippet": "B", "source": "faq:y"}, {"record_id": "c", "snippet": "C", "source": "faq:z"}]
VECTORS = [[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]]


def make_store(tmp_path):
    """Crea un índice de prueba y devuelve su almacén."""
    path = tmp_path / "index.json"
    write_index(path, "modelo-falso", RECORDS, VECTORS)
    return LocalVectorStore(path)


def test_search_orders_by_cosine_similarity(tmp_path):
    """El vector más parecido sale primero, con su coseno como score."""
    result = make_store(tmp_path).search([1.0, 0.1], 3)
    assert [item.record_id for item in result] == ["a", "c", "b"]
    assert result[0].score > result[1].score > result[2].score
    assert result[0].snippet == "A" and result[0].source == "faq:x"


def test_search_respects_limit(tmp_path):
    """Devuelve como máximo ``limit`` citas."""
    assert len(make_store(tmp_path).search([1.0, 0.0], 2)) == 2


def test_dimension_mismatch_is_actionable(tmp_path):
    """Un vector de otra dimensión pide reconstruir el índice."""
    with pytest.raises(RetrievalError, match="reconstruir"):
        make_store(tmp_path).search([1.0, 0.0, 0.0], 3)


def test_missing_corrupt_and_empty_index_fail_cleanly(tmp_path):
    """Archivo ausente, dañado, vacío o de otra versión producen RetrievalError."""
    with pytest.raises(RetrievalError):
        LocalVectorStore(tmp_path / "no-existe.json").search([1.0], 1)
    broken = tmp_path / "roto.json"
    broken.write_text("no es json", encoding="utf-8")
    with pytest.raises(RetrievalError):
        LocalVectorStore(broken).search([1.0], 1)
    empty = tmp_path / "vacio.json"
    empty.write_text(json.dumps({"version": 1, "dimension": 2, "records": []}), encoding="utf-8")
    with pytest.raises(RetrievalError):
        LocalVectorStore(empty).search([1.0, 0.0], 1)
    old = tmp_path / "vieja.json"
    old.write_text(json.dumps({"version": 99, "dimension": 2, "records": []}), encoding="utf-8")
    with pytest.raises(RetrievalError):
        LocalVectorStore(old).search([1.0, 0.0], 1)


def test_null_vector_in_index_is_rejected(tmp_path):
    """Un vector de ceros en el índice se rechaza."""
    path = tmp_path / "nulo.json"
    write_index(path, "m", RECORDS[:1], [[0.0, 0.0]])
    with pytest.raises(RetrievalError):
        LocalVectorStore(path).search([1.0, 0.0], 1)


def test_index_reloads_when_file_changes(tmp_path):
    """Si el archivo cambia, la búsqueda usa el contenido nuevo."""
    store = make_store(tmp_path)
    assert store.search([1.0, 0.0], 1)[0].record_id == "a"
    write_index(store.path, "m", RECORDS, [[0.0, 1.0], [1.0, 0.0], [0.7, 0.7]])
    stat = os.stat(store.path)
    os.utime(store.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert store.search([1.0, 0.0], 1)[0].record_id == "b"


def test_write_index_validates_counts(tmp_path):
    """No escribe si los vectores no coinciden con los registros."""
    with pytest.raises(RetrievalError):
        write_index(tmp_path / "x.json", "m", RECORDS, VECTORS[:2])
    with pytest.raises(RetrievalError):
        write_index(tmp_path / "x.json", "m", [], [])
