from cryptography.fernet import Fernet

from app.modules.email_settings.model import EmailProfile
from app.modules.users.model import User  # noqa: F401 - FK de updated_by
from app.shared.crypto import TokenCipher
from scripts.rotate_email_keys import rotate_all


def _key() -> str:
    return Fernet.generate_key().decode()


def test_rotation_reencrypts_and_keeps_reading(db):
    old_key, new_key = _key(), _key()
    db.add_all(
        [
            EmailProfile(
                name="Primário",
                priority=1,
                provider="smtp",
                security="starttls",
                secret_encrypted=TokenCipher(old_key).encrypt("senha-1"),
            ),
            EmailProfile(
                name="Reserva", priority=2, provider="smtp", security="starttls"
            ),
        ]
    )
    db.commit()

    count = rotate_all(db, TokenCipher([new_key, old_key]))

    assert count == 1
    primary = db.query(EmailProfile).filter_by(priority=1).one()
    # A chave antiga já pode sair: só a nova abre.
    assert TokenCipher(new_key).decrypt(primary.secret_encrypted) == "senha-1"
    assert primary.version == 1
