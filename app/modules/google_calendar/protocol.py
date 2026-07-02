from typing import Protocol


class GoogleCalendarClient(Protocol):
    """Operações sobre o Google Calendar de um usuário.

    `event` é o corpo de evento já no formato da Google Calendar API.
    As implementações recebem o `refresh_token` em texto puro (já
    descriptografado pelo service).
    """

    def create_event(self, refresh_token: str, event: dict) -> str:
        """Cria o evento e retorna o `google_event_id`."""
        ...

    def update_event(self, refresh_token: str, event_id: str, event: dict) -> None: ...

    def delete_event(self, refresh_token: str, event_id: str) -> None: ...

    def list_events(
        self, refresh_token: str, sync_token: str | None
    ) -> tuple[list[dict], str | None]:
        """Lista os eventos alterados desde `sync_token` (sync incremental).

        `sync_token` None = full sync (só eventos a partir de agora). Retorna
        `(eventos, next_sync_token)`. Cada evento é o recurso cru da Google
        Calendar API (inclui `status == "cancelled"` para os removidos). Se o
        token expirou (410 GONE), a implementação refaz um full sync
        transparentemente.
        """
        ...
