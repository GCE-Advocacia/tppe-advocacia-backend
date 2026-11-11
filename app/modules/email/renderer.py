import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from premailer import Premailer

from app.modules.email.filters import FILTERS
from app.modules.email.registry import TEMPLATES, TemplateSpec

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True)
class RenderedEmail:
    subject: str
    html: str
    text: str


class UnknownTemplateError(KeyError):
    pass


class BrandingProvider(Protocol):
    def get(self) -> dict: ...


class EmailRenderer:
    """Renderiza um tipo de e-mail com a marca do escritório.

    - ``.html`` com autoescape: nada que o usuário digitou vira HTML;
    - ``.txt`` e assunto sem escape (texto puro não tem ``&lt;``);
    - ``StrictUndefined``: variável esquecida quebra no teste, não em produção.
    """

    def __init__(
        self,
        branding: BrandingProvider,
        system_url: str = "",
        templates: dict[str, TemplateSpec] = TEMPLATES,
    ) -> None:
        self.branding = branding
        self.system_url = system_url.rstrip("/")
        self.templates = templates
        self._env = self._make_env(autoescape=select_autoescape(["html"]))
        self._text_env = self._make_env(autoescape=False)

    @staticmethod
    def _make_env(autoescape) -> Environment:
        env = Environment(
            loader=FileSystemLoader(TEMPLATES_DIR),
            autoescape=autoescape,
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
        )
        env.filters.update(FILTERS)
        return env

    def spec(self, template_id: str) -> TemplateSpec:
        try:
            return self.templates[template_id]
        except KeyError:
            raise UnknownTemplateError(template_id) from None

    def render(self, template_id: str, context: dict) -> RenderedEmail:
        spec = self.spec(template_id)
        full_context = {
            **spec.defaults,
            **context,
            **self.branding.get(),
            "system_url": self.system_url,
        }

        subject = self._text_env.from_string(spec.subject).render(full_context)
        html = self._env.get_template(f"{spec.path}.html").render(full_context)
        text = self._env.get_template(f"{spec.path}.txt").render(full_context)
        return RenderedEmail(
            # Quebra de linha no assunto viraria injeção de cabeçalho.
            subject=" ".join(subject.split()),
            html=_inline_css(html),
            text=_tidy_text(text),
        )

    def render_sample(self, template_id: str) -> RenderedEmail:
        return self.render(template_id, self.spec(template_id).sample_context)


def _inline_css(html: str) -> str:
    # Clientes de e-mail (Gmail, Outlook) ignoram boa parte do <style>: o CSS
    # vai para os atributos style. Media queries continuam no <style>.
    return Premailer(
        html,
        disable_validation=True,
        allow_network=False,
        keep_style_tags=False,
        remove_classes=False,
        strip_important=False,
        cssutils_logging_level=logging.CRITICAL,
    ).transform()


def _tidy_text(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    tidy: list[str] = []
    for line in lines:
        if line == "" and tidy and tidy[-1] == "":
            continue
        tidy.append(line)
    return "\n".join(tidy) + "\n"
