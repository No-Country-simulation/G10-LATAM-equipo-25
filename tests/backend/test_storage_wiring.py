"""Pruebas de la elección del almacenamiento en la composición de la API."""

import sys
import types

import pytest

from communitylab_backend.config.settings import Settings
from communitylab_backend.domain.errors import ProviderUnavailableError


@pytest.fixture
def dependencies(monkeypatch):
    """Importa la composición con un ``dataset_builder`` falso.

    El módulo real no está en el repositorio; el falso solo satisface el
    ``import`` de ``local.py`` y no se usa en estas pruebas.
    """
    package = types.ModuleType("dataset_builder")
    pii = types.ModuleType("dataset_builder.pii")
    pii.sanitize = lambda text, *args, **kwargs: text
    monkeypatch.setitem(sys.modules, "dataset_builder", package)
    monkeypatch.setitem(sys.modules, "dataset_builder.pii", pii)
    from communitylab_backend.api import dependencies as module
    return module


def settings(**values):
    """Crea ``Settings`` aislados del archivo ``.env`` local."""
    return Settings(_env_file=None, **values)


def test_default_storage_is_still_local(dependencies):
    """Sin configurar nada se sigue guardando en una carpeta local."""
    assert type(dependencies.build_storage(settings())).__name__ == "LocalObjectStorageAdapter"


def test_oci_storage_requires_namespace_and_bucket(dependencies):
    """Con ``oci`` y sin namespace o bucket la composición falla con un mensaje claro."""
    with pytest.raises(ProviderUnavailableError, match="OCI_NAMESPACE"):
        dependencies.build_storage(settings(storage_provider="oci"))


def test_oci_storage_is_built_from_settings(dependencies, tmp_path):
    """Con datos completos y un archivo de configuración válido se arma el adaptador de OCI."""
    pytest.importorskip("oci")
    key = tmp_path / "key.pem"
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key.write_bytes(rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    config = tmp_path / "config"
    config.write_text(f"[DEFAULT]\nuser=ocid1.user.oc1..aaaa\nfingerprint=aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99\nkey_file={key}\ntenancy=ocid1.tenancy.oc1..aaaa\nregion=sa-saopaulo-1\n", encoding="utf-8")
    storage = dependencies.build_storage(settings(storage_provider="oci", oci_namespace="ns", oci_bucket="bk", oci_config_file=config, oci_object_prefix="paquetes"))
    assert storage.provider == "oci" and storage.object_name("abc") == "paquetes/abc.json"
