from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.modules.auth.service import AuthService
from app.modules.email.sender import TemplateSender
from app.modules.users.repository import UserRepository
from app.shared.deps.email import get_queued_sender


def get_auth_service(
    db: Session = Depends(get_db),
    email_sender: TemplateSender = Depends(get_queued_sender),
) -> AuthService:
    return AuthService(UserRepository(db), email_sender)
