class FakeGoogleCalendarClient:
    """Implementação fake de `GoogleCalendarClient` para testes.

    Guarda os eventos em memória. Defina `fail = True` para simular
    indisponibilidade do Google.
    """

    def __init__(self) -> None:
        self.events: dict[str, dict] = {}
        self.fail: bool = False
        self._counter: int = 0
        # Fila de respostas para list_events: cada item é (eventos, next_token).
        self.incoming: list[tuple[list[dict], str | None]] = []
        self.last_sync_token: str | None = "__unset__"

    def _maybe_fail(self) -> None:
        if self.fail:
            raise RuntimeError("Google Calendar unavailable (fake)")

    def create_event(self, refresh_token: str, event: dict) -> str:
        self._maybe_fail()
        self._counter += 1
        event_id = f"fake-event-{self._counter}"
        self.events[event_id] = event
        return event_id

    def update_event(self, refresh_token: str, event_id: str, event: dict) -> None:
        self._maybe_fail()
        self.events[event_id] = event

    def delete_event(self, refresh_token: str, event_id: str) -> None:
        self._maybe_fail()
        self.events.pop(event_id, None)

    def list_events(
        self, refresh_token: str, sync_token: str | None
    ) -> tuple[list[dict], str | None]:
        self._maybe_fail()
        self.last_sync_token = sync_token
        if self.incoming:
            return self.incoming.pop(0)
        return [], sync_token
