from app.modules.email.protocol import EmailMessage, EmailProvider, SendResult
from app.modules.email.renderer import EmailRenderer


class TemplatedEmailSender:
    """Renderiza um tipo de e-mail e entrega.

    A assinatura de ``send`` espelha a do ``EmailOutbox.enqueue`` (Pessoa 3):
    quando a fila entrar, os services trocam só esta dependência.
    """

    def __init__(self, renderer: EmailRenderer, email_service: EmailProvider) -> None:
        self.renderer = renderer
        self.email_service = email_service

    def send(
        self,
        template_id: str,
        context: dict,
        to: str | list[str],
        *,
        headers: dict[str, str] | None = None,
    ) -> SendResult:
        rendered = self.renderer.render(template_id, context)
        recipients = [to] if isinstance(to, str) else list(to)
        return self.email_service.deliver(
            EmailMessage(
                to=recipients,
                subject=rendered.subject,
                html=rendered.html,
                text=rendered.text,
                headers=headers or {},
            )
        )
