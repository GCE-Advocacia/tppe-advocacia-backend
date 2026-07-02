from __future__ import annotations

from google_auth_oauthlib.flow import Flow

from app.config.settings import Settings

# Sync bidirecional: `calendar.events` cobre ler e gerenciar eventos.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
_TOKEN_URI = "https://oauth2.googleapis.com/token"  # public OAuth URL  # nosec B105


class GoogleOAuthFlow:
    """Encapsula o fluxo OAuth 2.0 do Google (Authorization Code).

    Construir esta classe exige que as credenciais do Google estejam
    configuradas — o service só a instancia quando `google_configured`.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _client_config(self) -> dict:
        return {
            "web": {
                "client_id": self._settings.google_client_id,
                "client_secret": self._settings.google_client_secret,
                "auth_uri": _AUTH_URI,
                "token_uri": _TOKEN_URI,
                "redirect_uris": [self._settings.google_redirect_uri],
            }
        }

    def _flow(self, state: str | None = None) -> Flow:
        flow = Flow.from_client_config(
            self._client_config(), scopes=SCOPES, state=state
        )
        flow.redirect_uri = self._settings.google_redirect_uri
        return flow

    def build_auth_url(self, state: str) -> str:
        """URL de consentimento do Google. `state` carrega o user_id assinado."""
        url, _ = self._flow(state=state).authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )
        return url

    def exchange_code(self, code: str) -> tuple[str, str]:
        """Troca o `code` do callback por tokens.

        Retorna (refresh_token, scope). `prompt=consent` no auth garante
        que o Google devolva um refresh_token.
        """
        flow = self._flow()
        flow.fetch_token(code=code)
        credentials = flow.credentials
        scope = " ".join(credentials.scopes or SCOPES)
        return credentials.refresh_token, scope
