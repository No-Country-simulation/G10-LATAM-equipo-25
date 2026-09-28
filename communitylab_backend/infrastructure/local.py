"""Adaptadores locales de la capa de infraestructura.

Reutilizan el sanitizador existente, simulan análisis y guardan borradores.
El adaptador RAG opcional sólo lee el índice local; ninguno llama a APIs.
"""

import json
import os
from pathlib import Path

from dataset_builder.pii import sanitize as existing_sanitize

from communitylab_backend.domain.errors import InvalidInteractionError, RetrievalError, StorageError
from communitylab_backend.domain.models import Analysis, DraftAsset, Evidence, SanitizedInteraction


class ExistingSanitizerAdapter:
    """Adapta las reglas PII existentes al puerto de sanitización.

Pertenece a infraestructura. Usa ``dataset_builder.pii`` sin modificarlo;
no conserva el texto original ni llama a proveedores externos.
    """

    def sanitize(self, interaction_id: str, text: str, channel: str | None, kind: str | None) -> SanitizedInteraction:
        """Recibe ID, texto, canal y tipo; devuelve la interacción segura.

        Sustituye PII básica con etiquetas. Produce
        ``InvalidInteractionError`` si ``text`` está vacío.
        """
        if not text.strip():
            raise InvalidInteractionError("El texto de la interacción no puede estar vacío")
        safe, _ = existing_sanitize(text.strip(), {key: True for key in ("email", "phone", "url", "ip", "user")})
        return SanitizedInteraction(interaction_id, safe, channel, kind)


class MockLLMProvider:
    """Simula el puerto LLM con reglas locales y resultados reproducibles.

    Pertenece a infraestructura. Permite probar el flujo sin credenciales;
    sus señales y borradores son de demostración, no juicios humanos ni
    contenido aprobado para publicación.
    """

    name = "mock"

    def __init__(self, success_keywords: str = "conseguí trabajo,logré,certifiqué,got a job", faq_keywords: str = "cómo,como,error,problema,help,?", success_types: str = "testimonial"):
        """Configura palabras de éxito, FAQ y tipos de historia.

        Recibe listas separadas por comas. No lee servicios ni archivos;
        estas reglas sólo determinan señales para la demo local.
        """
        self.success_keywords = tuple(word.strip().lower() for word in success_keywords.split(",") if word.strip())
        self.faq_keywords = tuple(word.strip().lower() for word in faq_keywords.split(",") if word.strip())
        self.success_types = tuple(word.strip().lower() for word in success_types.split(",") if word.strip())

    def analyze(self, interactions: list[SanitizedInteraction]) -> Analysis:
        """Deriva sentimiento, temas y señales del lote sanitizado.

        ``interactions`` debe contener texto seguro. Retorna ``Analysis``
        determinista; no realiza inferencia real ni llamadas externas.
        """
        text = " ".join(item.text_sanitized.lower() for item in interactions)
        positive = any(word in text for word in ("gracias", "logré", "conseguí", "excelente", "success"))
        negative = any(word in text for word in ("error", "problema", "falló", "help"))
        sentiment = "mixed" if positive and negative else "positive" if positive else "negative" if negative else "neutral"
        topic_rules = {"empleo": ("trabajo", "empleo", "job"), "certificación": ("certificación", "certifiqué", "exam"), "aprendizaje": ("curso", "python", "aprender", "study"), "comunidad": ("comunidad", "community", "grupo")}
        topics = [name for name, words in topic_rules.items() if any(word in text for word in words)] or ["general"]
        story = any((item.type or "").lower() in self.success_types for item in interactions) or any(word in text for word in self.success_keywords)
        question = any((item.type or "").lower() == "question" for item in interactions) or any(word in text for word in self.faq_keywords)
        insights = ["Posible historia de éxito"] if story else ["Pregunta recurrente"] if question else ["Actividad de la comunidad"]
        return Analysis(sentiment, topics, insights, story, question)

    def generate(self, flow: str, analysis: Analysis, interactions: list[SanitizedInteraction], evidence: list[Evidence]) -> list[DraftAsset]:
        """Crea dos borradores de ejemplo para la ruta seleccionada.

        Recibe ``flow``, señales, interacciones sanitizadas y citas. Retorna
        ``DraftAsset`` con IDs de evidencia existentes y estado ``draft``;
        no guarda ni publica contenido. Requiere un lote no vacío.
        """
        excerpt = interactions[0].text_sanitized[:240]
        references = [item.record_id for item in evidence]
        topic = ", ".join(analysis.topics)
        if flow == "success_story":
            return [DraftAsset("success_story", "Historia de la comunidad", f"Borrador para validar con la persona: {excerpt}", evidence_ids=references), DraftAsset("linkedin_post", "Logros de nuestra comunidad", f"La comunidad comparte avances en {topic}. {excerpt}", evidence_ids=references)]
        if flow == "faq":
            return [DraftAsset("faq_content", "Pregunta frecuente", f"Pregunta detectada: {excerpt}\nRespuesta pendiente de revisión humana con evidencia.", evidence_ids=references), DraftAsset("newsletter_highlight", "Dudas de la semana", f"Tema para responder: {topic}. {excerpt}", evidence_ids=references)]
        return [DraftAsset("linkedin_post", "Novedades de la comunidad", f"Esta semana conversamos sobre {topic}. {excerpt}", evidence_ids=references), DraftAsset("newsletter_highlight", "Resumen de la comunidad", f"Destacado: {excerpt}", evidence_ids=references)]


class MockRetriever:
    """Recuperador vacío para la demostración sin índice.

    Implementa ``RetrieverPort`` en infraestructura; no fabrica evidencia.
    """

    def retrieve(self, query: str, limit: int = 5) -> list[Evidence]:
        """Recibe consulta segura y límite; devuelve una lista vacía.

        No tiene efectos secundarios ni dependencias externas.
        """
        return []


class ExistingLocalRagAdapter:
    """Lee el índice FULL existente mediante el puerto recuperador.

    Pertenece a infraestructura y usa ``dataset_builder.rag`` en modo léxico.
    No crea embeddings, no reconstruye el índice ni adjudica relevancia.
    """

    def retrieve(self, query: str, limit: int = 5) -> list[Evidence]:
        """Busca ``query`` sanitizada y devuelve hasta ``limit`` citas.

        Sólo lee el índice local. Produce ``RetrievalError`` si faltan
        archivos o el formato es incompatible.
        """
        try:
            from dataset_builder.rag import load_config, search

            config = load_config()
            config["final_top_k"] = limit
            hits = search(query, config, mode="lexical", offline=True)
            return [Evidence(hit["record_id"], hit["snippet"], hit["source"], float(hit["score"])) for hit in hits]
        except (OSError, ValueError, KeyError, ImportError) as exc:
            raise RetrievalError("El índice RAG local no está disponible o es incompatible") from exc


class LocalObjectStorageAdapter:
    """Guarda paquetes JSON sanitizados en un directorio local.

    Implementa ``ObjectStoragePort`` en infraestructura. Escribe mediante
    un archivo temporal para evitar paquetes incompletos; no publica assets.
    """

    provider = "local"

    def __init__(self, directory: Path):
        """Recibe el directorio ``directory`` destinado a borradores locales.

        La creación del directorio se difiere hasta ``save``.
        """
        self.directory = directory

    def save(self, request_id: str, package: dict) -> str:
        """Guarda ``package`` con el nombre ``request_id`` y retorna la ruta.

        Crea el directorio y reemplaza atómicamente el destino. Puede
        producir ``StorageError`` ante un fallo del sistema de archivos.
        """
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            destination = self.directory / f"{request_id}.json"
            temporary = self.directory / f"{request_id}.tmp"
            temporary.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, destination)
            return str(destination)
        except OSError as exc:
            raise StorageError("No se pudo guardar el paquete local de borradores") from exc


class EnvironmentSecretProvider:
    """Implementa el puerto de secretos mediante variables de entorno.

    Pertenece a infraestructura. Lee bajo demanda; no guarda ni registra
    el valor y permite reemplazo posterior por OCI Vault.
    """

    def get(self, name: str) -> str | None:
        """Busca ``name`` en el entorno y devuelve el valor o ``None``.

        No tiene efectos secundarios y no imprime el secreto.
        """
        return os.environ.get(name)
