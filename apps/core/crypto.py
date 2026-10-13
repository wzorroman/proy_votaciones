import uuid

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class ClaveInvalida(Exception):
    """Se lanza cuando la clave Fernet no puede descifrar el token."""


def _fernet():
    return Fernet(settings.VOTE_KEY.encode())


def nueva_boleta() -> uuid.UUID:
    return uuid.uuid4()


def cifrar_boleta(boleta: uuid.UUID) -> str:
    return _fernet().encrypt(str(boleta).encode()).decode()


def descifrar_boleta(token: str) -> uuid.UUID:
    try:
        valor = _fernet().decrypt(token.encode()).decode()
        return uuid.UUID(valor)
    except InvalidToken as exc:
        raise ClaveInvalida("VOTE_KEY incorrecta o token corrupto") from exc
