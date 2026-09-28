"""Puntos de integración pendientes de la capa de infraestructura.

Cada clase muestra dónde implementará el equipo un proveedor externo.
Los stubs sólo producen ``ProviderUnavailableError``; no usan credenciales.
"""

from communitylab_backend.domain.errors import ProviderUnavailableError


class GeminiLLMAdapter:
    """Reserva la implementación de ``LLMProvider`` para Gemini.

    Pertenece a infraestructura. Debe analizar texto sanitizado y crear
    borradores estructurados; el stub actual no contacta Gemini.
    """

    name = "gemini"

    def analyze(self, interactions):
        """Recibe interacciones sanitizadas; deberá devolver ``Analysis``.

        Actualmente produce ``ProviderUnavailableError`` sin llamada externa.
        """
        raise ProviderUnavailableError("La integración de Gemini está pendiente")

    def generate(self, flow, analysis, interactions, evidence):
        """Recibe ruta, análisis, interacciones y citas; deberá devolver drafts.

        Actualmente produce ``ProviderUnavailableError`` sin llamada externa.
        """
        raise ProviderUnavailableError("La integración de Gemini está pendiente")


class CohereEmbeddingAdapter:
    """Reserva ``EmbeddingProvider`` para Cohere Embed 4.

    Pertenece a infraestructura. La implementación futura deberá separar
    documentos y consultas; el stub no contacta Cohere.
    """

    def embed_documents(self, texts):
        """Recibe textos seguros; deberá devolver un vector por documento.

        Actualmente produce ``ProviderUnavailableError``.
        """
        raise ProviderUnavailableError("La integración de Cohere Embed está pendiente")

    def embed_query(self, text):
        """Recibe una consulta segura; deberá devolver su vector.

        Actualmente produce ``ProviderUnavailableError``.
        """
        raise ProviderUnavailableError("La integración de Cohere Embed está pendiente")


class CohereRerankerAdapter:
    """Reserva ``RerankerProvider`` para Cohere Rerank 4.

    Pertenece a infraestructura. Deberá conservar IDs de citas; el stub
    actual no llama a Cohere ni crea evidencia.
    """

    def rerank(self, query, candidates):
        """Recibe consulta segura y citas; deberá devolverlas ordenadas.

        Actualmente produce ``ProviderUnavailableError``.
        """
        raise ProviderUnavailableError("La integración de Cohere Rerank está pendiente")


class OCIVectorStoreAdapter:
    """Reserva ``VectorStorePort`` para el servicio vectorial OCI elegido.

    Pertenece a infraestructura. Deberá devolver citas sanitizadas; el
    stub no abre conexiones ni modifica el índice RAG existente.
    """

    def search(self, vector, limit):
        """Recibe vector y límite; deberá devolver evidencia citada.

        Actualmente produce ``ProviderUnavailableError``.
        """
        raise ProviderUnavailableError("La integración de OCI Vector Store está pendiente")


class OCIObjectStorageAdapter:
    """Reserva ``ObjectStoragePort`` para OCI Object Storage.

    Pertenece a infraestructura. Guardará paquetes sanitizados cuando el
    equipo la implemente; esta integración bloquea el MVP final.
    """

    provider = "oci"

    def save(self, request_id, package):
        """Recibe ID y paquete seguro; deberá devolver ubicación del objeto.

        Actualmente produce ``ProviderUnavailableError`` y no persiste nada.
        """
        raise ProviderUnavailableError("La integración de OCI Object Storage está pendiente")


class OCIVaultAdapter:
    """Reserva ``SecretProvider`` para OCI Vault.

    Pertenece a infraestructura. Deberá obtener secretos sin registrarlos;
    el stub no abre conexiones ni necesita credenciales.
    """

    def get(self, name):
        """Recibe nombre lógico; deberá devolver secreto o ``None``.

        Actualmente produce ``ProviderUnavailableError``.
        """
        raise ProviderUnavailableError("La integración de OCI Vault está pendiente")
