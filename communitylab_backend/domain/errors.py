"""Errores del dominio que la capa API convierte en respuestas HTTP seguras."""


class BackendError(Exception):
    """Error base del dominio con un mensaje apto para mostrarse al cliente.

    La API lo traduce a HTTP. Evita exponer detalles de SDK o secretos.
    """


class InvalidInteractionError(BackendError):
    """Representa una interacción inválida en la capa de dominio.

    Permite a la API responder 422. No valida por sí sola ni expone texto
    original; la lanza el sanitizador cuando no puede crear una entrada segura.
    """


class ProviderUnavailableError(BackendError):
    """Representa un proveedor no disponible en la capa de dominio.

    Permite responder 503 desde API. Los adaptadores la producen y deben
    ocultar detalles de SDK, credenciales y solicitudes sensibles.
    """


class RetrievalError(BackendError):
    """Representa un fallo de recuperación en la capa de dominio.

    Lo usan adaptadores de ``RetrieverPort`` para responder 502 sin revelar
    rutas internas del índice ni datos de la consulta.
    """


class AssetGenerationError(BackendError):
    """Representa una generación inválida en la capa de dominio.

    Permite responder 502 cuando el proveedor no devuelve dos borradores
    ``draft``; no contiene una operación de publicación.
    """


class StorageError(BackendError):
    """Representa un fallo de persistencia en la capa de dominio.

    Lo producen adaptadores de ``ObjectStoragePort``; la API responde 502
    sin exponer rutas privadas o detalles de credenciales.
    """
