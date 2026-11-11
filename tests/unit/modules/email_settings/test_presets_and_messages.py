import smtplib
import socket

import pytest

from app.modules.email.errors import EmailSendError
from app.modules.email_settings.messages import explain_exception, explain_send_error
from app.modules.email_settings.presets import PRESETS, sender_warnings
from app.modules.email_settings.schema import EmailProfileForm
from app.modules.email_settings.service import EmailSettingsService


@pytest.mark.parametrize(
    ("preset", "host", "port", "security"),
    [
        ("gmail", "smtp.gmail.com", 587, "starttls"),
        ("outlook", "smtp.office365.com", 587, "starttls"),
        ("hostinger", "smtp.hostinger.com", 465, "ssl"),
        ("locaweb", "email-ssl.com.br", 465, "ssl"),
    ],
)
def test_each_preset_fills_host_port_and_security(preset, host, port, security):
    form = EmailProfileForm(
        preset=preset, host="ignorado", port=1, security="none", username="a@b.com"
    )

    filled = EmailSettingsService.apply_preset(form)

    assert (filled.host, filled.port, filled.security) == (host, port, security)


def test_other_keeps_typed_fields():
    form = EmailProfileForm(preset="other", host="smtp.meu.com", port=2525)

    filled = EmailSettingsService.apply_preset(form)

    assert (filled.host, filled.port) == ("smtp.meu.com", 2525)


def test_sender_defaults_to_the_account_email():
    form = EmailProfileForm(preset="gmail", username="escritorio@gmail.com")

    assert EmailSettingsService.apply_preset(form).from_email == "escritorio@gmail.com"


def test_resend_is_not_accepted_from_the_screen():
    with pytest.raises(ValueError):
        EmailProfileForm(provider="resend")


def test_every_preset_has_password_help():
    assert all(p.password_help for p in PRESETS.values())
    assert PRESETS["gmail"].help_url


class TestSenderWarnings:
    def test_gmail_must_send_as_the_account(self):
        warnings = sender_warnings("contato@escritorio.com.br", "fulano@gmail.com", "gmail")

        assert warnings and "fulano@gmail.com" in warnings[0]

    def test_other_domain_is_warned(self):
        warnings = sender_warnings("contato@outro.com", "conta@escritorio.com.br", "hostinger")

        assert warnings and "@escritorio.com.br" in warnings[0]

    def test_same_domain_is_fine(self):
        assert sender_warnings("contato@escritorio.com.br", "ti@escritorio.com.br", "other") == []


class TestPlainLanguage:
    def test_535_on_gmail_suggests_app_password(self):
        explained = explain_exception(
            smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted"),
            PRESETS["gmail"],
        )

        assert explained.message == "O e-mail ou a senha não foram aceitos."
        assert "Use uma senha de app, não a senha normal" in explained.hint

    def test_timeout_mentions_blocked_port(self):
        explained = explain_exception(TimeoutError(), None, 587)

        assert "porta 587" in explained.hint
        assert "bloqueada" in explained.hint

    def test_sender_refused(self):
        explained = explain_exception(
            smtplib.SMTPSenderRefused(553, b"5.7.1 Sender address rejected", "x@y.com"),
            None,
        )

        assert "remetente" in explained.message

    def test_unknown_host(self):
        assert "não foi encontrado" in explain_exception(socket.gaierror(), None).message

    def test_classified_send_error_535(self):
        err = EmailSendError(
            "Autenticação recusada: 535 5.7.8 bad", transient=False, failover=True,
            provider="own", smtp_code=535,
        )

        assert explain_send_error(err, PRESETS["outlook"]).message == (
            "O e-mail ou a senha não foram aceitos."
        )

    def test_classified_timeout(self):
        err = EmailSendError(
            "Conexão com o servidor falhou: timed out", transient=True, failover=True,
            provider="own",
        )

        assert "não respondeu" in explain_send_error(err, None).message
