import os
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from app.modules.email.branding import StaticBrandingProvider, build_branding
from app.modules.email.registry import TEMPLATES, notification_template_id
from app.modules.email.renderer import EmailRenderer, UnknownTemplateError
from app.modules.notifications.schema import EventType

SNAPSHOTS = Path(__file__).parent / "snapshots"

# Marca fixa: o snapshot não pode depender do banco.
BRANDING = {
    "office": {
        "name": "Souza & Lima Advocacia",
        "logo_url": "https://exemplo.com/logo.png",
        "address": "SQS 102, Bloco A, Brasília - DF",
        "phone": "(61) 3333-0000",
        "email": "contato@souzalima.adv.br",
        "whatsapp_url": "https://wa.me/5561999990000",
        "website_url": "https://souzalima.adv.br",
        "instagram_url": None,
        "linkedin_url": None,
        "cnpj": None,
    },
    "colors": {
        "primary": "#232C43",
        "accent": "#661C16",
        "button_text": "#FFFFFF",
        "link": "#661C16",
        "muted": "#6B7280",
    },
}


@pytest.fixture
def renderer() -> EmailRenderer:
    return EmailRenderer(
        StaticBrandingProvider(BRANDING), system_url="https://app.exemplo.com"
    )


@pytest.mark.parametrize("template_id", sorted(TEMPLATES))
class TestEveryTemplate:
    def test_renders_sample(self, renderer, template_id):
        rendered = renderer.render_sample(template_id)

        assert rendered.subject
        assert "\n" not in rendered.subject
        assert "<" not in rendered.subject
        assert rendered.text.strip()
        assert "<" not in rendered.text
        assert "Souza &amp; Lima Advocacia" in rendered.html
        assert "Souza & Lima Advocacia" in rendered.text

    def test_css_is_inlined(self, renderer, template_id):
        html = renderer.render_sample(template_id).html
        assert 'style="' in html
        # Só as media queries continuam no <style>.
        assert ".content {" not in html

    def test_matches_snapshot(self, renderer, template_id):
        rendered = renderer.render_sample(template_id)
        content = (
            f"Subject: {rendered.subject}\n\n{rendered.text}\n"
            f"----- HTML -----\n{rendered.html}"
        )
        path = SNAPSHOTS / f"{template_id}.snap"
        if os.getenv("UPDATE_SNAPSHOTS") or not path.exists():
            path.parent.mkdir(exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        expected = path.read_text(encoding="utf-8")
        assert content == expected, (
            f"{template_id} mudou. Se foi de propósito, rode com UPDATE_SNAPSHOTS=1"
        )


def test_every_notification_event_has_a_template():
    for event in EventType:
        assert notification_template_id(event) in TEMPLATES


def test_user_input_is_escaped_in_html_and_raw_in_text(renderer):
    context = {
        **TEMPLATES["payment_reminder_d1"].sample_context,
        "client_name": "<script>alert(1)</script>",
    }
    rendered = renderer.render("payment_reminder_d1", context)

    assert "<script>" not in rendered.html
    assert "&lt;script&gt;" in rendered.html
    assert "<script>alert(1)</script>" in rendered.text


def test_user_input_cannot_break_subject_header(renderer):
    context = {
        **TEMPLATES[notification_template_id(EventType.TASK_ASSIGNED)].sample_context,
        "task_title": "Revisar\r\nBcc: vitima@exemplo.com",
    }
    rendered = renderer.render(notification_template_id(EventType.TASK_ASSIGNED), context)
    assert "\n" not in rendered.subject and "\r" not in rendered.subject


def test_missing_variable_fails(renderer):
    with pytest.raises(UndefinedError):
        renderer.render("password_reset", {"user_name": "Maria"})


def test_optional_keys_have_defaults(renderer):
    context = {"client_name": "Ana", "due_date": "2026-10-27"}
    rendered = renderer.render("payment_reminder_d1", context)
    assert "Valor a consultar" in rendered.text
    assert "Serviços jurídicos / Honorários" in rendered.text


def test_unknown_template(renderer):
    with pytest.raises(UnknownTemplateError):
        renderer.render("nao_existe", {})


def test_layout_without_office_config():
    renderer = EmailRenderer(StaticBrandingProvider(build_branding(None)))
    rendered = renderer.render_sample("password_reset")
    assert "Escritório de Advocacia" in rendered.html
    assert "<img" not in rendered.html
    assert "#232C43" in rendered.html
    # Sem system_url, os botões "abrir no sistema" somem.
    notif = renderer.render_sample(notification_template_id(EventType.TASK_ASSIGNED))
    assert "/sistema/tarefas" not in notif.html


def test_brand_colors_are_applied(renderer):
    branding = {**BRANDING, "colors": {**BRANDING["colors"], "accent": "#123456"}}
    rendered = EmailRenderer(StaticBrandingProvider(branding)).render_sample(
        "password_reset"
    )
    assert "#123456" in rendered.html
