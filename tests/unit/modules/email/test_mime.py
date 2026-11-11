import pytest

from app.modules.email.errors import EmailSendError
from app.modules.email.mime import build_mime, ensure_size_limit, html_to_text
from app.modules.email.protocol import Attachment, EmailMessage


def _message(**overrides) -> EmailMessage:
    data = {
        "to": ["cliente@exemplo.com"],
        "subject": "Assunto",
        "html": "<p>Olá <b>Maria</b></p>",
        "text": "Olá Maria",
    }
    data.update(overrides)
    return EmailMessage(**data)


class TestBuildMime:
    def test_alternative_with_text_and_html(self):
        mime = build_mime(_message(), "noreply@escritorio.com.br", "Escritório")

        assert mime.get_content_type() == "multipart/alternative"
        parts = [p.get_content_type() for p in mime.iter_parts()]
        assert parts == ["text/plain", "text/html"]
        assert str(mime["From"]) == "Escritório <noreply@escritorio.com.br>"
        assert mime["Subject"] == "Assunto"

    def test_attachment_makes_it_mixed(self):
        message = _message(
            attachments=[Attachment("boleto.pdf", "application/pdf", b"%PDF-1.4")]
        )
        mime = build_mime(message, "noreply@escritorio.com.br")

        assert mime.get_content_type() == "multipart/mixed"
        attachments = list(mime.iter_attachments())
        assert len(attachments) == 1
        assert attachments[0].get_filename() == "boleto.pdf"
        assert attachments[0].get_content() == b"%PDF-1.4"
        body = mime.get_body(("html",))
        assert "Maria" in body.get_content()

    def test_message_id_uses_sender_domain(self):
        mime = build_mime(_message(), "noreply@escritorio.com.br")
        assert mime["Message-ID"].endswith("@escritorio.com.br>")

    def test_custom_headers_and_explicit_message_id(self):
        message = _message(
            headers={"Message-ID": "<abc@escritorio.com.br>", "X-Email-Id": "42"}
        )
        mime = build_mime(message, "noreply@escritorio.com.br")
        assert mime["Message-ID"] == "<abc@escritorio.com.br>"
        assert mime["X-Email-Id"] == "42"

    def test_bcc_never_in_headers(self):
        message = _message(cc=["cc@x.com"], bcc=["oculto@x.com"], reply_to="r@x.com")
        mime = build_mime(message, "noreply@x.com")
        assert mime["Cc"] == "cc@x.com"
        assert mime["Reply-To"] == "r@x.com"
        assert "Bcc" not in mime
        assert "oculto@x.com" not in mime.as_string()
        assert message.recipients == ["cliente@exemplo.com", "cc@x.com", "oculto@x.com"]

    def test_text_fallback_from_html(self):
        mime = build_mime(_message(text=None), "noreply@x.com")
        assert mime.get_body(("plain",)).get_content().strip() == "Olá Maria"


def test_html_to_text_skips_style_and_breaks_blocks():
    html = "<style>p{color:red}</style><p>Linha 1</p><p>Linha   2</p>"
    assert html_to_text(html) == "Linha 1\n\nLinha 2"


def test_size_limit():
    big = _message(attachments=[Attachment("a.bin", "application/octet-stream", b"x" * (2 * 1024 * 1024))])
    ensure_size_limit(big, 3, "smtp")
    with pytest.raises(EmailSendError) as exc:
        ensure_size_limit(big, 1, "smtp")
    assert not exc.value.transient
    assert not exc.value.failover
