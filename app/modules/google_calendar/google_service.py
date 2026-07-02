from __future__ import annotations

from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config.settings import Settings
from app.modules.google_calendar.oauth import SCOPES

_TOKEN_URI = "https://oauth2.googleapis.com/token"  # public OAuth URL  # nosec B105
_CALENDAR_ID = "primary"


class GoogleCalendarApiClient:
    """Implementação real de `GoogleCalendarClient` via Google Calendar API.

    A cada chamada constrói credenciais a partir do refresh_token — a lib
    do Google obtém um access_token novo automaticamente.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _service(self, refresh_token: str):
        credentials = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=_TOKEN_URI,
            client_id=self._settings.google_client_id,
            client_secret=self._settings.google_client_secret,
            scopes=SCOPES,
        )
        return build("calendar", "v3", credentials=credentials, cache_discovery=False)

    def create_event(self, refresh_token: str, event: dict) -> str:
        created = (
            self._service(refresh_token)
            .events()
            .insert(calendarId=_CALENDAR_ID, body=event)
            .execute()
        )
        return created["id"]

    def update_event(self, refresh_token: str, event_id: str, event: dict) -> None:
        self._service(refresh_token).events().update(
            calendarId=_CALENDAR_ID, eventId=event_id, body=event
        ).execute()

    def delete_event(self, refresh_token: str, event_id: str) -> None:
        self._service(refresh_token).events().delete(
            calendarId=_CALENDAR_ID, eventId=event_id
        ).execute()

    def list_events(
        self, refresh_token: str, sync_token: str | None
    ) -> tuple[list[dict], str | None]:
        service = self._service(refresh_token)
        try:
            return self._collect(service, sync_token)
        except HttpError as exc:
            if exc.resp.status == 410:
                # syncToken expirou: Google exige full resync do zero.
                return self._collect(service, None)
            raise

    def _collect(
        self, service, sync_token: str | None
    ) -> tuple[list[dict], str | None]:
        params: dict = {
            "calendarId": _CALENDAR_ID,
            "singleEvents": True,
            "showDeleted": True,
        }
        if sync_token:
            params["syncToken"] = sync_token
        else:
            # Full sync: só o que começa a partir de agora, evita puxar
            # histórico gigante. timeMin não pode coexistir com syncToken.
            params["timeMin"] = datetime.now(timezone.utc).isoformat()

        events: list[dict] = []
        next_sync_token: str | None = None
        page_token: str | None = None
        while True:
            if page_token:
                params["pageToken"] = page_token
            response = service.events().list(**params).execute()
            events.extend(response.get("items", []))
            next_sync_token = response.get("nextSyncToken") or next_sync_token
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return events, next_sync_token
