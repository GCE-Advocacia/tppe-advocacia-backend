"""Provedores que o escritório escolhe na lista. Host, porta e segurança vêm
daqui; o admin só informa e-mail e senha de app. "Outro" deixa os campos
técnicos livres."""

from dataclasses import dataclass, field
from typing import Literal

PresetId = Literal["gmail", "outlook", "hostinger", "locaweb", "other"]
Security = Literal["starttls", "ssl", "none"]


@dataclass(frozen=True)
class ProviderPreset:
    id: PresetId
    name: str
    host: str | None
    port: int | None
    security: Security
    # Como gerar a senha de app, em linguagem simples, e onde.
    password_help: str
    help_url: str | None
    # Domínios das contas desse provedor (para avisar remetente de outra conta).
    domains: tuple[str, ...] = field(default_factory=tuple)
    # Gmail e Outlook só deixam enviar como o próprio e-mail da conta.
    sender_must_match: bool = False


PRESETS: dict[str, ProviderPreset] = {
    p.id: p
    for p in (
        ProviderPreset(
            id="gmail",
            name="Gmail / Google Workspace",
            host="smtp.gmail.com",
            port=587,
            security="starttls",
            password_help=(
                "O Google não aceita a senha normal da conta. Ative a verificação "
                "em duas etapas e crie uma senha de app de 16 letras."
            ),
            help_url="https://myaccount.google.com/apppasswords",
            domains=("gmail.com", "googlemail.com"),
            sender_must_match=True,
        ),
        ProviderPreset(
            id="outlook",
            name="Outlook / Microsoft 365",
            host="smtp.office365.com",
            port=587,
            security="starttls",
            password_help=(
                "Use uma senha de app da conta Microsoft. No Microsoft 365, o "
                "administrador precisa liberar o envio autenticado (SMTP AUTH)."
            ),
            help_url="https://account.microsoft.com/security",
            domains=("outlook.com", "hotmail.com", "live.com"),
            sender_must_match=True,
        ),
        ProviderPreset(
            id="hostinger",
            name="Hostinger",
            host="smtp.hostinger.com",
            port=465,
            security="ssl",
            password_help="Use a senha da caixa de e-mail criada no painel da Hostinger.",
            help_url="https://hpanel.hostinger.com/emails",
        ),
        ProviderPreset(
            id="locaweb",
            name="Locaweb",
            host="email-ssl.com.br",
            port=465,
            security="ssl",
            password_help="Use a senha da caixa de e-mail criada no painel da Locaweb.",
            help_url="https://painel.locaweb.com.br",
        ),
        ProviderPreset(
            id="other",
            name="Outro",
            host=None,
            port=None,
            security="starttls",
            password_help=(
                "Peça ao responsável pelo e-mail do escritório o servidor de "
                "saída (SMTP), a porta e a senha."
            ),
            help_url=None,
        ),
    )
}


def get_preset(preset_id: str | None) -> ProviderPreset | None:
    return PRESETS.get(preset_id) if preset_id else None


def domain_of(address: str | None) -> str:
    return (
        address.rsplit("@", 1)[-1].strip().lower() if address and "@" in address else ""
    )


def sender_warnings(
    from_email: str | None, account: str | None, preset_id: str | None
) -> list[str]:
    """Avisos (não bloqueiam) quando o remetente não pertence à conta."""
    if not from_email or not account:
        return []
    preset = get_preset(preset_id)
    if preset is not None and preset.sender_must_match:
        if from_email.lower() != account.lower():
            return [
                f"O {preset.name} só envia como {account}. Use esse mesmo e-mail "
                "como remetente, senão os e-mails podem ser recusados ou cair no spam."
            ]
        return []
    if domain_of(from_email) != domain_of(account):
        return [
            f"O remetente {from_email} é de outro domínio que a conta {account}. "
            "Muitos servidores recusam ou mandam para o spam. Use um e-mail "
            f"@{domain_of(account)}."
        ]
    return []
