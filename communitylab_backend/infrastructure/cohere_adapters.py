"""Adaptadores de Cohere para embeddings y reranking.

Implementan ``EmbeddingProvider`` y ``RerankerProvider`` del dominio. Reciben
sólo texto ya sanitizado y traducen cualquier fallo del SDK a
``ProviderUnavailableError`` sin exponer claves, prompts ni cabeceras.

Dependencia externa: ``cohere`` (SDK oficial, ``ClientV2``). Se importa de
forma diferida para que el backend arranque con proveedores ``mock`` aunque
el SDK no esté instalado.
"""

from dataclasses import replace

from communitylab_backend.domain.errors import ProviderUnavailableError
from communitylab_backend.domain.models import Evidence

# Cohere limita los textos por llamada; se parte el lote para no superarlo.
DEFAULT_BATCH_SIZE = 96
_NO_RETRY = {"max_retries": 0}


def _build_client(api_key: str | None, timeout_seconds: float):
    """Crea el cliente oficial de Cohere con ``timeout_seconds``.

    Pertenece a infraestructura. Produce ``ProviderUnavailableError`` si falta
    la clave o el SDK no está instalado; el mensaje no incluye la clave.
    """
    if not api_key:
        raise ProviderUnavailableError("Falta la clave de Cohere (COHERE_API_KEY)")
    try:
        import cohere
    except ImportError as exc:
        raise ProviderUnavailableError("El SDK de Cohere no está instalado") from exc
    return cohere.ClientV2(api_key=api_key, timeout=timeout_seconds)


def _translate_error(exc: Exception) -> ProviderUnavailableError:
    """Convierte un error del SDK en un error de dominio con mensaje seguro.

    Distingue el límite de uso (HTTP 429), que es la causa probable con una
    clave de prueba. No copia el texto de ``exc``: podría contener datos.
    """
    if getattr(exc, "status_code", None) == 429:
        return ProviderUnavailableError("Cohere alcanzó su límite de uso; reintentar más tarde")
    return ProviderUnavailableError("Cohere no está disponible")


class CohereEmbeddingAdapter:
    """Implementa ``EmbeddingProvider`` con Cohere Embed.

    Pertenece a infraestructura. Separa documentos (``search_document``) de
    consultas (``search_query``) porque Cohere optimiza cada tipo distinto.
    No administra el índice ni guarda vectores; sólo los calcula.
    """

    def __init__(self, api_key: str | None, model: str = "embed-v4.0", timeout_seconds: float = 30.0, batch_size: int = DEFAULT_BATCH_SIZE, output_dimension: int | None = None, client=None):
        """Configura modelo, tiempo de espera y tamaño de lote.

        ``client`` permite inyectar un cliente falso en pruebas. Con
        ``output_dimension`` fijo, todos los vectores comparten dimensión.
        Produce ``ProviderUnavailableError`` si falta la clave o el SDK.
        """
        self.model = model
        self.batch_size = max(1, batch_size)
        self.output_dimension = output_dimension
        self._client = client if client is not None else _build_client(api_key, timeout_seconds)

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        """Pide a Cohere los vectores de ``texts`` para un ``input_type``.

        Retorna un vector por texto, en orden. Produce
        ``ProviderUnavailableError`` ante un fallo o una respuesta incompleta.
        """
        options = {"output_dimension": self.output_dimension} if self.output_dimension else {}
        try:
            response = self._client.embed(model=self.model, texts=texts, input_type=input_type, embedding_types=["float"], request_options=_NO_RETRY, **options)
            floats = response.embeddings
            floats = getattr(floats, "float_", None) or getattr(floats, "float", None)
        except Exception as exc:
            raise _translate_error(exc) from exc
        if not floats or len(floats) != len(texts) or any(not vector for vector in floats):
            raise ProviderUnavailableError("Cohere devolvió una respuesta de embeddings incompleta")
        return [[float(value) for value in vector] for vector in floats]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Devuelve un vector por documento sanitizado, conservando el orden.

        Parte ``texts`` en lotes de ``batch_size``. Una lista vacía no llama
        al proveedor. Produce ``ProviderUnavailableError`` si un lote falla.
        """
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._embed(texts[start:start + self.batch_size], "search_document"))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """Devuelve el vector de búsqueda de una consulta sanitizada.

        Usa ``search_query``. Produce ``ProviderUnavailableError`` ante un
        fallo del servicio o un texto vacío.
        """
        if not text or not text.strip():
            raise ProviderUnavailableError("La consulta para embeddings está vacía")
        return self._embed([text], "search_query")[0]


class CohereRerankerAdapter:
    """Implementa ``RerankerProvider`` con Cohere Rerank.

    Pertenece a infraestructura. Reordena citas existentes y conserva sus
    ``record_id``; nunca crea ni descarta citas salvo que se fije ``top_n``.
    Actualiza ``score`` con la relevancia que calcula el reranker.
    """

    def __init__(self, api_key: str | None, model: str = "rerank-v4.0-pro", timeout_seconds: float = 30.0, top_n: int | None = None, client=None):
        """Configura modelo, tiempo de espera y recorte opcional ``top_n``.

        ``client`` permite inyectar un cliente falso en pruebas. Produce
        ``ProviderUnavailableError`` si falta la clave o el SDK.
        """
        self.model = model
        self.top_n = top_n
        self._client = client if client is not None else _build_client(api_key, timeout_seconds)

    def rerank(self, query: str, candidates: list[Evidence]) -> list[Evidence]:
        """Ordena ``candidates`` de mayor a menor relevancia para ``query``.

        Con cero o una cita devuelve la lista sin llamar al proveedor, para
        ahorrar cuota. Produce ``ProviderUnavailableError`` si Cohere falla o
        devuelve índices inválidos.
        """
        if len(candidates) <= 1:
            return list(candidates)
        limit = min(self.top_n or len(candidates), len(candidates))
        documents = [candidate.snippet.strip() or "(sin texto)" for candidate in candidates]
        try:
            response = self._client.rerank(model=self.model, query=query, documents=documents, top_n=limit, request_options=_NO_RETRY)
            results = list(response.results)
        except Exception as exc:
            raise _translate_error(exc) from exc
        ordered: list[Evidence] = []
        seen: set[int] = set()
        for result in results:
            index = result.index
            if not isinstance(index, int) or not 0 <= index < len(candidates) or index in seen:
                raise ProviderUnavailableError("Cohere devolvió un orden de citas inválido")
            seen.add(index)
            ordered.append(replace(candidates[index], score=float(result.relevance_score)))
        if not ordered:
            raise ProviderUnavailableError("Cohere no devolvió resultados de reranking")
        return ordered
