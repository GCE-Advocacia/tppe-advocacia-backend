import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import bcrypt

from app.db.database import SessionLocal, init_db
from app.modules.users.model import User
from app.shared.types import Role


def create_admin(name: str, email: str, password: str) -> None:
    init_db()
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            print(f"User with email '{email}' already exists.")
            return

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )
        admin = User(
            name=name,
            email=email,
            hashed_password=hashed,
            role=Role.ADMIN,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f"Admin created: id={admin.id}, email={admin.email}")
    finally:
        db.close()


if __name__ == "__main__":
    import getpass

    if len(sys.argv) == 4:
        name = sys.argv[1]
        email = sys.argv[2]
        password = sys.argv[3]
    elif len(sys.argv) > 1:
        print("Uso:")
        print("  Interativo: python scripts/create_admin.py")
        print("  Argumentos: python scripts/create_admin.py <nome> <email> <senha>")
        sys.exit(1)
    else:
        name = input("Name: ")
        email = input("Email: ")
        try:
            password = getpass.getpass("Password: ")
        except Exception:
            password = input("Password: ")

    create_admin(name, email, password)
