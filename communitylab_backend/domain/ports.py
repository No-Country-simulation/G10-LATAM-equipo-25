"""Contratos del dominio para cambiar servicios sin cambiar el flujo.

Los adaptadores reciben texto sanitizado y devuelven modelos del dominio.
El backend local usa métodos síncronos; cada implementación externa debe
controlar sus tiempos de espera y traducir fallos a errores del dominio.
"""

from typing import Protocol

from .models import Analysis, ContentBrief, DraftAsset, Evidence, SanitizedInteraction


class SanitizationPort(Protocol):
    """Convierte texto de entrada en la proyección segura del dominio.

    Pertenece al dominio como contrato. La infraestructura implementa la regla;
    el puerto no almacena el texto ni llama a proveedores externos.
    """

    def sanitize(self, interaction_id: str, text: str, channel: str | None, kind: str | None) -> SanitizedInteraction:
        """Sanitiza ``text`` y conserva identidad, canal y tipo.

        Retorna una interacción segura. Puede producir
        ``InvalidInteractionError`` si el texto está vacío.
        """


class LLMProvider(Protocol):
    """Define análisis y generación sin vincular el dominio a Gemini.

    La aplicación lo utiliza después de sanitizar; la implementación pertenece
    a infraestructura. No recibe el autor ni el texto original.
    """

    name: str

    def analyze(self, interactions: list[SanitizedInteraction], known_topics: list[str] | None = None) -> Analysis:
        """Analiza interacciones sanitizadas y retorna señales para routing.

        ``interactions`` contiene el lote seguro. ``known_topics`` son temas de
        dudas ya vistos en lotes anteriores: si una duda trata uno de ellos,
        conviene reutilizar el mismo nombre para poder contar su frecuencia.
        Retorna ``Analysis`` con una ``InteractionSignal`` por interacción.
        Puede producir ``ProviderUnavailableError`` si el servicio no está
        disponible.
        """

    def generate(self, flow: str, analysis: Analysis, interactions: list[SanitizedInteraction], evidence: list[Evidence]) -> list[DraftAsset]:
        """Genera borradores para ``flow`` con señales y citas verificables.

        Retorna al menos dos ``DraftAsset`` pendientes. Puede producir
        ``ProviderUnavailableError`` o ``AssetGenerationError``. El grafo usa
        ``generate_assets``; este método se conserva por compatibilidad.
        """

    def generate_assets(self, briefs: list[ContentBrief], analysis: Analysis) -> list[DraftAsset]:
        """Redacta en una sola operación los activos de todos los ``briefs``.

        Retorna un ``DraftAsset`` en estado ``draft`` por cada tipo pedido en
        cada encargo (los de la rama ``faq`` llevan su ``topic``). Puede
        producir ``ProviderUnavailableError`` o ``AssetGenerationError`` si
        falta algún activo.
        """


class EmbeddingProvider(Protocol):
    """Define vectores para textos seguros sin depender de Cohere.

    La implementación vive en infraestructura; no administra el índice.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Recibe documentos sanitizados y retorna un vector por texto, en orden.

        Puede producir ``ProviderUnavailableError`` ante un fallo del servicio.
        """

    def embed_query(self, text: str) -> list[float]:
        """Recibe una consulta sanitizada y retorna su vector de búsqueda.

        Puede producir ``ProviderUnavailableError`` ante un fallo del servicio.
        """


class RerankerProvider(Protocol):
    """Ordena citas candidatas sin acoplar el dominio a Cohere.

    Debe conservar los identificadores de evidencia; no crea citas nuevas.
    """

    def rerank(self, query: str, candidates: list[Evidence]) -> list[Evidence]:
        """Ordena ``candidates`` para una ``query`` sanitizada.

        Retorna las citas reordenadas. Puede producir
        ``ProviderUnavailableError`` si el proveedor falla.
        """


class VectorStorePort(Protocol):
    """Busca vectores y devuelve evidencia, sin fijar una tecnología OCI.

    La implementación pertenece a infraestructura; no decide el routing.
    """

    def search(self, vector: list[float], limit: int) -> list[Evidence]:
        """Busca ``vector`` y retorna hasta ``limit`` citas sanitizadas.

        Puede producir ``RetrievalError`` ante índice o servicio inválido.
        """


class RetrieverPort(Protocol):
    """Recupera contexto para una consulta segura sin definir dónde vive.

    La aplicación usa este puerto; un adaptador local puede leer el RAG existente.
    """

    def retrieve(self, query: str, limit: int = 5) -> list[Evidence]:
        """Recibe ``query`` sanitizada y retorna hasta ``limit`` citas.

        Puede producir ``RetrievalError``. No fabrica respuestas ni etiquetas.
        """


class ObjectStoragePort(Protocol):
    """Guarda paquetes de borradores sin fijar almacenamiento local u OCI.

    La aplicación entrega datos sanitizados; este contrato no publica assets.
    """

    provider: str

    def save(self, request_id: str, package: dict) -> str:
        """Guarda ``package`` bajo ``request_id`` y retorna su ubicación.

        Tiene el efecto secundario de persistir datos. Puede producir
        ``StorageError`` si la escritura falla.
        """


class SecretProvider(Protocol):
    """Obtiene secretos sin vincular la aplicación a entorno u OCI Vault.

    La implementación nunca debe registrar ni guardar valores secretos.
    """

    def get(self, name: str) -> str | None:
        """Busca el secreto ``name`` y retorna su valor o ``None``.

        Puede producir ``ProviderUnavailableError`` ante fallo del servicio.
        """


class DoubtHistoryPort(Protocol):
    """Guarda las dudas procesadas para saber qué temas se repiten.

    Pertenece al dominio como contrato. La implementación local usa SQLite;
    otra podría usar una base en la nube sin cambiar la aplicación. Sólo
    recibe texto ya sanitizado, nunca el autor.
    """

    def record(self, request_id: str, community: str, doubts: list[dict]) -> int:
        """Guarda las dudas de un lote y retorna cuántas guardó.

        Puede producir ``StorageError`` si no se puede escribir.
        """

    def known_topics(self, limit: int = 15) -> list[str]:
        """Retorna los temas más repetidos, para que el análisis reutilice sus nombres."""

    def attach_faqs(self, topic_key: str, faq_ids: list[str]) -> int:
        """Marca que el tema ``topic_key`` ya tiene FAQ oficial y retorna cuántas dudas actualizó.

        Puede producir ``StorageError`` si no se puede escribir.
        """

    def ranking(self, days: int | None = None, limit: int = 20) -> dict:
        """Retorna el ranking de dudas frecuentes de los últimos ``days`` días (o de todo el historial).

        Puede producir ``StorageError`` si el historial no se puede leer.
        """


class KnowledgeBasePort(Protocol):
    """Lee y amplía la base de conocimiento (FAQs oficiales y reseñas reales).

    Pertenece al dominio como contrato. La implementación local usa
    ``motor_educativo.db``. Las reseñas sólo se leen; lo único que se puede
    escribir son FAQs nuevas.
    """

    def summary(self) -> dict:
        """Retorna los totales de la base (FAQs, reseñas, cursos, sentimiento y notas).

        Puede producir ``RetrievalError`` si la base no está disponible.
        """

    def faqs(self, limit: int) -> list[dict]:
        """Retorna hasta ``limit`` FAQs oficiales con ``record_id``, ``question``, ``answer`` y ``source``.

        Puede producir ``RetrievalError`` si la base no está disponible.
        """

    def reviews(self, course: str | None, sentiment: str | None, limit: int) -> list[dict]:
        """Retorna reseñas reales sin datos personales, filtradas por curso y sentimiento.

        Puede producir ``RetrievalError`` si la base no está disponible.
        """

    def courses(self) -> list[str]:
        """Retorna los cursos que tienen reseñas.

        Puede producir ``RetrievalError`` si la base no está disponible.
        """

    def add_faqs(self, rows: list[dict], dry_run: bool) -> dict:
        """Agrega FAQs ya validadas (o sólo muestra qué haría si ``dry_run``).

        Antes de escribir guarda una copia de seguridad. Retorna lo agregado,
        las repetidas, los ids nuevos y la copia. Puede producir
        ``RetrievalError`` o ``StorageError``.
        """
