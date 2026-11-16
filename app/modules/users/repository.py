from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.modules.users.model import User
from app.shared.types import Role


class UserRepository:
    """Este repositório nunca comita. Operações de escrita usam db.add + db.flush
    e o Service que orquestra a transação fecha com unit_of_work."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        return self.db.scalars(select(User).where(User.email == email)).first()

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.scalars(select(User).where(User.id == user_id)).first()

    def email_exists(self, email: str, exclude_id: int | None = None) -> bool:
        statement = select(User).where(User.email == email)
        if exclude_id is not None:
            statement = statement.where(User.id != exclude_id)
        return self.db.scalars(statement).first() is not None

    def get_all(
        self,
        role: Role | None = None,
        is_active: bool | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[User], int]:
        statement = select(User).options(selectinload(User.permissions))
        count_statement = select(func.count()).select_from(User)

        if role is not None:
            statement = statement.where(User.role == role)
            count_statement = count_statement.where(User.role == role)

        if is_active is not None:
            statement = statement.where(User.is_active == is_active)
            count_statement = count_statement.where(User.is_active == is_active)

        total = self.db.scalar(count_statement) or 0
        users = list(
            self.db.scalars(statement.offset((page - 1) * limit).limit(limit)).all()
        )

        return users, total

    def create(
        self,
        name: str,
        email: str,
        hashed_password: str,
        role: Role,
        created_by: int | None = None,
    ) -> User:
        user = User(
            name=name,
            email=email,
            hashed_password=hashed_password,
            role=role,
            created_by=created_by,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def get_by_reset_token_hash(self, token_hash: str) -> User | None:
        return self.db.scalars(
            select(User).where(User.reset_token_hash == token_hash)
        ).first()

    def update(self, user: User, data: dict) -> User:
        for key, value in data.items():
            setattr(user, key, value)
        self.db.flush()
        return user
