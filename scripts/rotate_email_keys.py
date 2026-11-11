"""Recriptografa as senhas dos perfis de e-mail com a chave mais nova.

Uso:
  1. Coloque a chave nova NA FRENTE em EMAIL_ENCRYPTION_KEYS
     (ex.: EMAIL_ENCRYPTION_KEYS=nova,antiga) e reinicie a API e o scheduler.
  2. python -m scripts.rotate_email_keys
  3. Remova a chave antiga de EMAIL_ENCRYPTION_KEYS e reinicie de novo.

Tudo numa transação só: se algum segredo não abrir com nenhuma chave, nada
é alterado.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.config.settings import get_settings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.modules.email_settings.configs import get_email_cipher  # noqa: E402
from app.modules.email_settings.repository import EmailProfileRepository  # noqa: E402
from app.shared.crypto import TokenCipher  # noqa: E402
from app.shared.db.uow import unit_of_work  # noqa: E402


def rotate_all(db: Session, cipher: TokenCipher) -> int:
    repo = EmailProfileRepository(db)
    rotated = 0
    with unit_of_work(db):
        for profile in repo.list_all():
            if not profile.secret_encrypted:
                continue
            # Sem subir ``version``: o segredo em texto é o mesmo, a cadeia
            # em memória continua válida.
            repo.update(
                profile, {"secret_encrypted": cipher.rotate(profile.secret_encrypted)}
            )
            rotated += 1
    return rotated


def main() -> int:
    cipher = get_email_cipher(get_settings())
    with SessionLocal() as db:
        count = rotate_all(db, cipher)
    print(f"{count} segredo(s) recriptografado(s) com a chave nova.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
