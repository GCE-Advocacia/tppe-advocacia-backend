import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-with-enough-length")
os.environ.setdefault("RESEND_API_KEY", "re_test")
# Chave Fernet fixa só para os testes (perfis de e-mail salvos pela tela).
os.environ.setdefault(
    "EMAIL_ENCRYPTION_KEYS", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
)
