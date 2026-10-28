from sqlalchemy.exc import IntegrityError

from app.modules.audit_logs.service import AuditLogService
from app.modules.users.invite_model import UserInvite
from app.modules.users.invite_service import InviteService
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.modules.users.schema import UserCreate, UserUpdate
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import EmailAlreadyExistsError, UserNotFoundError
from app.shared.types import Role, UserStatus


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        invites: InviteService,
        audit: AuditLogService,
    ) -> None:
        self.repository = repository
        self.invites = invites
        self.audit = audit

    def list_users(
        self,
        role: Role | None,
        is_active: bool | None,
        page: int,
        limit: int,
    ) -> tuple[list[User], int]:
        return self.repository.get_all(
            role=role, is_active=is_active, page=page, limit=limit
        )

    def latest_invites(self, users: list[User]) -> dict[int, UserInvite]:
        return self.invites.latest_by_users([u.id for u in users])

    def get_user(self, user_id: int) -> User:
        user = self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        return user

    def create_user(self, payload: UserCreate, created_by: User) -> User:
        """Cria o usuário como ``INVITED``, sem senha, com um convite por link.

        Usuário e convite entram na mesma transação; o e-mail sai depois e,
        se falhar, o usuário continua criado (o admin pode reenviar).
        """
        try:
            with unit_of_work(self.repository.db):
                user = self.repository.create(
                    name=payload.name,
                    email=payload.email,
                    hashed_password=None,
                    role=Role.USER,
                    created_by=created_by.id,
                    status=UserStatus.INVITED,
                )
                issued = self.invites.issue(user, created_by)
        except IntegrityError as exc:
            raise EmailAlreadyExistsError() from exc

        self.invites.send_invite_email(user, issued, created_by.name)
        self.audit.log_user_created(user, created_by)
        return user

    def update_user(self, user_id: int, payload: UserUpdate, updated_by: User) -> User:
        user = self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()

        updates = payload.model_dump(exclude_unset=True)
        updates["updated_by"] = updated_by.id

        if "email" in updates and updates["email"] != user.email:
            if self.repository.email_exists(updates["email"], exclude_id=user_id):
                raise EmailAlreadyExistsError()

        is_deactivating = updates.get("is_active") is False and user.is_active is True
        with unit_of_work(self.repository.db):
            updated = self.repository.update(user, updates)

        if is_deactivating:
            self.audit.log_user_deactivated(updated, updated_by)
        elif {"name", "email", "role", "is_active", "can_view_payments"} & set(
            updates.keys()
        ):
            self.audit.log_user_updated(updated, updated_by)

        return updated
