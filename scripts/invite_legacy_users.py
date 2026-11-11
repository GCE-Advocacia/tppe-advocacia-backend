"""Gera convite para usuários antigos que nunca trocaram a senha temporária.

Antes do convite por link, o usuário novo recebia uma senha temporária em
texto puro por e-mail. Este script troca essa senha por um convite: o
usuário passa a INVITED, a senha temporária deixa de valer e ele recebe um
link para definir a própria senha.

Não existe flag de "senha trocada", então o critério é: papel USER, criado
por um admin (``created_by`` preenchido) e nunca alterado depois
(``updated_at`` igual a ``created_at``). Confira a lista com ``--dry-run``
antes, ou passe os e-mails explicitamente com ``--email``.

Uso:
  python -m scripts.invite_legacy_users --dry-run
  python -m scripts.invite_legacy_users
  python -m scripts.invite_legacy_users --email a@x.com --email b@x.com
"""

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config.settings import get_settings  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.modules.users.invite_repository import InviteRepository  # noqa: E402
from app.modules.users.invite_service import InviteService  # noqa: E402
from app.modules.users.model import User  # noqa: E402
from app.modules.users.repository import UserRepository  # noqa: E402
from app.shared.db.uow import unit_of_work  # noqa: E402
from app.shared.deps.email import build_templated_sender  # noqa: E402
from app.shared.types import Role, UserStatus  # noqa: E402


def find_candidates(db: Session, emails: list[str] | None = None) -> list[User]:
    statement = select(User).where(
        User.status == UserStatus.ACTIVE, User.is_active.is_(True)
    )
    if emails:
        statement = statement.where(User.email.in_(emails))
    else:
        statement = statement.where(
            User.role == Role.USER,
            User.created_by.is_not(None),
            User.updated_at == User.created_at,
        )
    return list(db.scalars(statement.order_by(User.id)).all())


def invite_users(db: Session, invites: InviteService, users: list[User]) -> int:
    repo = UserRepository(db)
    sent = 0
    for user in users:
        with unit_of_work(db):
            repo.update(user, {"status": UserStatus.INVITED, "hashed_password": None})
            issued = invites.issue(user, created_by=None)
        if invites.send_invite_email(user, issued):
            sent += 1
    return sent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="só lista, não altera")
    parser.add_argument("--email", action="append", help="limita a estes e-mails")
    args = parser.parse_args()

    with SessionLocal() as db:
        users = find_candidates(db, args.email)
        for user in users:
            print(f"- {user.id} {user.name} <{user.email}>")
        print(f"{len(users)} usuário(s) encontrado(s).")
        if args.dry_run or not users:
            return 0

        invites = InviteService(
            InviteRepository(db),
            UserRepository(db),
            build_templated_sender(),
            get_settings(),
        )
        sent = invite_users(db, invites, users)
    print(f"Convites criados: {len(users)}; e-mails enviados: {sent}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
