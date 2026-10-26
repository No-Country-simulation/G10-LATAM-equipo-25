"""Historial de dudas de la comunidad para saber cuáles son frecuentes.

Pertenece a infraestructura. Guarda cada duda procesada (su tema, la fecha,
el texto ya sanitizado y las FAQs oficiales encontradas) en un archivo SQLite
local, ``data/historial_dudas.db`` por defecto. Con eso arma el ranking de
"dudas frecuentes": qué temas se repiten, cuántas veces, en cuántas semanas y
si ya tienen respuesta oficial.

No usa IA ni gasta cuota: todo es conteo local. No guarda el autor ni el texto
original, sólo el texto con los datos personales ocultos.
"""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from communitylab_backend.domain.errors import StorageError

SCHEMA = """
CREATE TABLE IF NOT EXISTS dudas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    fecha TEXT NOT NULL,
    comunidad TEXT,
    tema TEXT NOT NULL,
    tema_clave TEXT NOT NULL,
    interaccion_id TEXT,
    texto TEXT,
    faq_ids TEXT
)
"""


class DoubtHistory:
    """Registro local de dudas y ranking de los temas más frecuentes.

    Pertenece a infraestructura. ``path`` es el archivo SQLite; se crea al
    guardar la primera duda. Los errores de disco se traducen a
    ``StorageError`` con un mensaje seguro.
    """

    def __init__(self, path: Path):
        """Recibe la ruta del archivo; no lo abre hasta que se usa."""
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        """Abre el archivo (creándolo si hace falta) y asegura que exista la tabla."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute(SCHEMA)
        return connection

    def record(self, request_id: str, community: str, doubts: list[dict], when: datetime | None = None) -> int:
        """Guarda las dudas de un lote y retorna cuántas guardó.

        Cada duda trae ``topic``, ``topic_key`` (el tema normalizado),
        ``interaction_id``, ``text`` (sanitizado) y ``faq_ids``: la lista de
        FAQs oficiales encontradas para su tema, o ``None`` si su tema no se
        buscó en este lote. Produce ``StorageError`` si no se puede escribir.
        """
        if not doubts:
            return 0
        moment = (when or datetime.now()).isoformat(timespec="seconds")
        rows = [(request_id, moment, community, doubt["topic"], doubt["topic_key"], doubt.get("interaction_id"), (doubt.get("text") or "")[:600], None if doubt.get("faq_ids") is None else json.dumps(doubt["faq_ids"])) for doubt in doubts]
        try:
            with closing(self._connect()) as connection, connection:
                connection.executemany("INSERT INTO dudas (request_id, fecha, comunidad, tema, tema_clave, interaccion_id, texto, faq_ids) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        except (OSError, sqlite3.Error) as exc:
            raise StorageError("No se pudo guardar el historial de dudas") from exc
        return len(rows)

    def attach_faqs(self, topic_key: str, faq_ids: list[str]) -> int:
        """Anota que el tema ``topic_key`` ya tiene FAQ oficial (``faq_ids``).

        Se usa cuando el equipo agrega a la base la respuesta de un tema que
        no tenía respaldo: el ranking lo marca resuelto al instante, sin
        esperar a que alguien vuelva a preguntar. Sólo cambia las dudas de
        ese tema que no tenían FAQ. Retorna cuántas actualizó. Produce
        ``StorageError`` si no se puede escribir.
        """
        if not faq_ids or not self.path.is_file():
            return 0
        try:
            with closing(self._connect()) as connection, connection:
                cursor = connection.execute("UPDATE dudas SET faq_ids = ? WHERE tema_clave = ? AND (faq_ids IS NULL OR faq_ids = '[]')", (json.dumps(faq_ids), topic_key))
                return cursor.rowcount
        except (OSError, sqlite3.Error) as exc:
            raise StorageError("No se pudo actualizar el historial de dudas") from exc

    def known_topics(self, limit: int = 15) -> list[str]:
        """Retorna los nombres de los temas más repetidos, para reutilizarlos.

        Gemini recibe esta lista al analizar un lote nuevo y usa el mismo
        nombre si una duda trata un tema conocido. Si el historial no existe,
        retorna una lista vacía.
        """
        if not self.path.is_file():
            return []
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute("SELECT tema_clave, COUNT(*) FROM dudas GROUP BY tema_clave ORDER BY COUNT(*) DESC, MAX(fecha) DESC LIMIT ?", (limit,)).fetchall()
                return [connection.execute("SELECT tema FROM dudas WHERE tema_clave = ? ORDER BY fecha DESC, id DESC LIMIT 1", (key,)).fetchone()[0] for key, _ in rows]
        except (OSError, sqlite3.Error):
            return []

    def ranking(self, days: int | None = None, limit: int = 20) -> dict:
        """Arma el ranking de dudas frecuentes.

        ``days`` limita a los últimos días (``None``: todo el historial). Por
        cada tema retorna su nombre más reciente, cuántas dudas tuvo, en
        cuántas semanas y en cuántos lotes apareció, la primera y la última
        fecha, si tiene FAQ oficial (``True``, ``False`` o ``None`` si nunca
        se buscó) y hasta dos ejemplos. Retorna también el total de dudas.
        Produce ``StorageError`` si el historial existe pero no se puede leer.
        """
        if not self.path.is_file():
            return {"total_doubts": 0, "topics": []}
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds") if days else "0000"
        try:
            with closing(self._connect()) as connection:
                total = connection.execute("SELECT COUNT(*) FROM dudas WHERE fecha >= ?", (since,)).fetchone()[0]
                groups = connection.execute(
                    "SELECT tema_clave, COUNT(*), COUNT(DISTINCT strftime('%Y-%W', fecha)), COUNT(DISTINCT request_id), MIN(fecha), MAX(fecha) "
                    "FROM dudas WHERE fecha >= ? GROUP BY tema_clave ORDER BY COUNT(*) DESC, MAX(fecha) DESC LIMIT ?", (since, limit)).fetchall()
                topics = []
                for key, count, weeks, batches, first, last in groups:
                    details = connection.execute("SELECT tema, texto, faq_ids FROM dudas WHERE tema_clave = ? AND fecha >= ? ORDER BY fecha DESC, id DESC", (key, since)).fetchall()
                    searched = [json.loads(faq) for _, _, faq in details if faq is not None]
                    official = sorted({identifier for faq in searched for identifier in faq})
                    topics.append({
                        "topic": details[0][0], "count": count, "weeks": weeks, "batches": batches,
                        "first_seen": first[:10], "last_seen": last[:10],
                        "has_official_faq": bool(official) if searched else None, "faq_ids": official[:5],
                        "examples": [text for _, text, _ in details[:2] if text],
                    })
        except (OSError, sqlite3.Error, ValueError) as exc:
            raise StorageError("No se pudo leer el historial de dudas") from exc
        return {"total_doubts": total, "topics": topics}
