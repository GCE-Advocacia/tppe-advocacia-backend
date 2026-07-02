import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.database import SessionLocal, init_db
from app.modules.users.model import User


def delete_user(email: str) -> None:
    init_db()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            print(f"Nenhum usuário encontrado com email '{email}'.")
            return

        print(f"Usuário encontrado: id={user.id}, nome='{user.name}', role={user.role}")
        confirm = input("Confirmar exclusão? [s/N] ").strip().lower()
        if confirm != "s":
            print("Operação cancelada.")
            return

        db.delete(user)
        db.commit()
        print(f"Usuário '{email}' removido com sucesso.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python scripts/delete_user.py <email>")
        sys.exit(1)

    delete_user(sys.argv[1])
