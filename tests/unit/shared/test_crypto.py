import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.shared.crypto import TokenCipher


def _cipher() -> TokenCipher:
    return TokenCipher(Fernet.generate_key().decode())


def test_encrypt_decrypt_roundtrip():
    cipher = _cipher()
    token = "1//0refresh-token-value"
    assert cipher.decrypt(cipher.encrypt(token)) == token


def test_ciphertext_is_not_plaintext():
    cipher = _cipher()
    encrypted = cipher.encrypt("secret-token")
    assert encrypted != "secret-token"


def test_keys_are_not_interchangeable():
    encrypted = _cipher().encrypt("token")
    other = _cipher()
    try:
        other.decrypt(encrypted)
        raised = False
    except Exception:
        raised = True
    assert raised


def _key() -> str:
    return Fernet.generate_key().decode()


def test_rejects_empty_key_list():
    with pytest.raises(ValueError):
        TokenCipher([])


def test_new_key_list_still_reads_old_ciphertext():
    old_key = _key()
    encrypted = TokenCipher(old_key).encrypt("senha")
    assert TokenCipher([_key(), old_key]).decrypt(encrypted) == "senha"


def test_rotation_reencrypts_and_old_key_can_be_dropped():
    old_key, new_key = _key(), _key()
    encrypted = TokenCipher(old_key).encrypt("senha")

    rotated = TokenCipher([new_key, old_key]).rotate(encrypted)

    assert TokenCipher(new_key).decrypt(rotated) == "senha"
    with pytest.raises(InvalidToken):
        TokenCipher(old_key).decrypt(rotated)
