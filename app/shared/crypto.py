from cryptography.fernet import Fernet, MultiFernet


class TokenCipher:
    """Criptografia simétrica (Fernet) para segredos guardados no banco
    (refresh_token do Google, senhas dos perfis de e-mail).

    Aceita uma chave ou uma lista. Com lista (``MultiFernet``), encripta com a
    primeira e decripta com qualquer uma: para trocar a chave, coloque a nova
    na frente, rode a rotação e só depois remova a antiga.

    Gere uma chave com:
        python -c "from cryptography.fernet import Fernet; \
print(Fernet.generate_key().decode())"
    """

    def __init__(self, keys: str | list[str]) -> None:
        if isinstance(keys, str):
            keys = [keys]
        if not keys:
            raise ValueError("TokenCipher precisa de ao menos uma chave")
        self._fernet = MultiFernet([Fernet(k.encode()) for k in keys])

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode()).decode()

    def rotate(self, ciphertext: str) -> str:
        """Recriptografa com a primeira chave (a mais nova)."""
        return self._fernet.rotate(ciphertext.encode()).decode()
