from unittest.mock import MagicMock

import pytest

from app.modules.email.branding import StaticBrandingProvider
from app.modules.email.fake_service import FakeEmailService
from app.modules.email.renderer import EmailRenderer
from app.modules.email.sender import TemplatedEmailSender
from app.modules.notifications.model import NotificationPreference
from app.modules.notifications.schema import EventType
from app.modules.notifications.service import NotificationService


def make_pref(event_type: EventType, enabled: bool) -> NotificationPreference:
    pref = MagicMock(spec=NotificationPreference)
    pref.event_type = event_type
    pref.enabled = enabled
    return pref


def make_user(*, id: int = 1, email: str = "u@test.com", is_active: bool = True):
    user = MagicMock()
    user.id = id
    user.email = email
    user.is_active = is_active
    return user


@pytest.fixture
def repo():
    return MagicMock()


@pytest.fixture
def users():
    return MagicMock()


@pytest.fixture
def outbox():
    return FakeEmailService()


@pytest.fixture
def email(outbox):
    # Sender de verdade (renderiza o template), espiado pelo MagicMock.
    return MagicMock(
        wraps=TemplatedEmailSender(EmailRenderer(StaticBrandingProvider()), outbox)
    )


@pytest.fixture
def service(repo, users, email):
    svc = NotificationService.__new__(NotificationService)
    svc.repository = repo
    svc.users = users
    svc.email_sender = email
    return svc


class TestGetPreferences:
    def test_returns_all_event_types_with_default_true_when_none_stored(
        self, service, repo
    ):
        repo.get_by_user.return_value = []

        prefs = service.get_preferences(1)

        assert prefs == {event: True for event in EventType}

    def test_overrides_default_with_stored_value(self, service, repo):
        repo.get_by_user.return_value = [
            make_pref(EventType.LEAD_ASSIGNED, False),
        ]

        prefs = service.get_preferences(1)

        assert prefs[EventType.LEAD_ASSIGNED] is False
        assert prefs[EventType.PROCESS_MOVEMENT_CREATED] is True
        assert prefs[EventType.PROCESS_STATUS_CHANGED] is True
        assert prefs[EventType.TASK_ASSIGNED] is True


class TestUpdatePreferences:
    def test_calls_upsert_and_returns_full_state(self, service, repo):
        repo.get_by_user.return_value = [
            make_pref(EventType.LEAD_ASSIGNED, False),
        ]
        update = {EventType.LEAD_ASSIGNED: False}

        prefs = service.update_preferences(1, update)

        repo.upsert_many.assert_called_once_with(1, update)
        assert prefs[EventType.LEAD_ASSIGNED] is False


class TestNotify:
    def test_sends_email_when_preference_enabled(
        self, service, repo, users, email, outbox
    ):
        users.get_by_id.return_value = make_user(email="dest@test.com")
        repo.get_by_user.return_value = []

        service.notify(
            1,
            EventType.LEAD_ASSIGNED,
            {
                "lead_id": 7,
                "lead_name": "João",
                "lead_email": "j@test.com",
                "lead_phone": None,
            },
        )

        email.send.assert_called_once()
        assert email.send.call_args.args[0] == "notification.lead_assigned"
        assert email.send.call_args.kwargs["to"] == "dest@test.com"
        assert outbox.sent[0]["to"] == "dest@test.com"
        assert "João" in outbox.sent[0]["html"]
        assert "João" in outbox.messages[0].text

    def test_skips_when_preference_disabled(self, service, repo, users, email):
        users.get_by_id.return_value = make_user()
        repo.get_by_user.return_value = [
            make_pref(EventType.LEAD_ASSIGNED, False),
        ]

        service.notify(
            1,
            EventType.LEAD_ASSIGNED,
            {
                "lead_id": 1,
                "lead_name": "x",
                "lead_email": "x@x.com",
                "lead_phone": None,
            },
        )

        email.send.assert_not_called()

    def test_skips_when_user_not_found(self, service, repo, users, email):
        users.get_by_id.return_value = None

        service.notify(99, EventType.LEAD_ASSIGNED, {})

        email.send.assert_not_called()
        repo.get_by_user.assert_not_called()

    def test_skips_when_user_inactive(self, service, repo, users, email):
        users.get_by_id.return_value = make_user(is_active=False)

        service.notify(1, EventType.LEAD_ASSIGNED, {})

        email.send.assert_not_called()
        repo.get_by_user.assert_not_called()

    def test_swallows_email_send_exception(self, service, repo, users, email):
        users.get_by_id.return_value = make_user()
        repo.get_by_user.return_value = []
        email.send.side_effect = RuntimeError("smtp down")

        service.notify(
            1,
            EventType.LEAD_ASSIGNED,
            {
                "lead_id": 1,
                "lead_name": "x",
                "lead_email": "x@x.com",
                "lead_phone": None,
            },
        )

    def test_swallows_template_render_exception(
        self, service, repo, users, email, outbox
    ):
        users.get_by_id.return_value = make_user()
        repo.get_by_user.return_value = []

        service.notify(1, EventType.LEAD_ASSIGNED, {})

        assert outbox.sent == []

    def test_swallows_user_lookup_failure(self, service, repo, users, email):
        users.get_by_id.side_effect = RuntimeError("db down")

        service.notify(1, EventType.LEAD_ASSIGNED, {})

        email.send.assert_not_called()

    def test_swallows_preferences_lookup_failure(self, service, repo, users, email):
        users.get_by_id.return_value = make_user()
        repo.get_by_user.side_effect = RuntimeError("db down")

        service.notify(1, EventType.LEAD_ASSIGNED, {})

        email.send.assert_not_called()
