import hashlib
import uuid
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from django.test import override_settings

from apps.core.crypto import ClaveInvalida, cifrar_boleta, descifrar_boleta, nueva_boleta
from apps.core.hashing import generar_hash_participacion


@override_settings(HASH_SALT="mi-salt-prueba")
def test_generar_hash_participacion_usa_payload_y_salt(monkeypatch):
    proceso = SimpleNamespace(id=42)
    estudiante = SimpleNamespace(numero_documento="12345678")

    first_ts = "2026-10-08T12:00:00+00:00"
    second_ts = "2026-10-08T12:00:01+00:00"

    calls = iter([first_ts, second_ts])
    monkeypatch.setattr("apps.core.hashing.timezone.now", lambda: __import__("datetime").datetime.fromisoformat(calls.__next__()))

    hash_1, ts_1 = generar_hash_participacion(estudiante, proceso)
    hash_2, ts_2 = generar_hash_participacion(estudiante, proceso)

    assert ts_1 == first_ts
    assert ts_2 == second_ts
    assert hash_1 == hashlib.sha256(f"42|12345678|{first_ts}|mi-salt-prueba".encode("utf-8")).hexdigest()
    assert hash_2 == hashlib.sha256(f"42|12345678|{second_ts}|mi-salt-prueba".encode("utf-8")).hexdigest()
    assert hash_1 != hash_2


@override_settings(VOTE_KEY=Fernet.generate_key().decode())
def test_cifrado_boleta_redondea_y_rechaza_clave_incorrecta():
    boleta = nueva_boleta()
    token = cifrar_boleta(boleta)

    assert descifrar_boleta(token) == boleta

    with override_settings(VOTE_KEY=Fernet.generate_key().decode()):
        with pytest.raises(ClaveInvalida):
            descifrar_boleta(token)

    otro_uuid = uuid.uuid4()
    assert otro_uuid != boleta
