import logging

from app.modules.email.registry import notification_template_id
from app.modules.email.sender import TemplateSender
from app.modules.notifications.repository import NotificationPreferenceRepository
from app.modules.notifications.schema import EventType
from app.modules.users.repository import UserRepository
from app.shared.db.uow import unit_of_work

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(
        self,
        repository: NotificationPreferenceRepository,
        users: UserRepository,
        email_sender: TemplateSender,
    ) -> None:
        self.repository = repository
        self.users = users
        self.email_sender = email_sender

    def get_preferences(self, user_id: int) -> dict[EventType, bool]:
        stored = {p.event_type: p.enabled for p in self.repository.get_by_user(user_id)}
        return {event: stored.get(event, True) for event in EventType}

    def update_preferences(
        self, user_id: int, prefs: dict[EventType, bool]
    ) -> dict[EventType, bool]:
        with unit_of_work(self.repository.db):
            self.repository.upsert_many(user_id, prefs)
        return self.get_preferences(user_id)

    def notify(self, user_id: int, event_type: EventType, payload: dict) -> None:
        try:
            user = self.users.get_by_id(user_id)
            if user is None or not user.is_active:
                return

            if not self.get_preferences(user_id)[event_type]:
                return

            self.email_sender.send(
                notification_template_id(event_type), payload, to=user.email
            )
        except Exception:
            logger.exception(
                "Failed to send notification user_id=%s event=%s",
                user_id,
                event_type,
            )
