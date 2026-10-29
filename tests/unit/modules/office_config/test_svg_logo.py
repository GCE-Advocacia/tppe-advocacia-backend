from io import BytesIO

import pytest
from fastapi import UploadFile
from PIL import Image

from app.modules.media.logo import normalize_favicon, normalize_logo
from app.shared.exceptions import InvalidLogoImageError


def svg(
    body='<rect width="80" height="40" fill="#235789"/>',
    dimensions='viewBox="0 0 80 40"',
):
    return f'<svg xmlns="http://www.w3.org/2000/svg" {dimensions}>{body}</svg>'.encode()


def upload(content):
    return UploadFile(filename="logo.svg", file=BytesIO(content))


@pytest.mark.parametrize(
    "dimensions",
    [
        'viewBox="0 0 80 40"',
        'width="80" height="40"',
        'width="100%" height="100%" viewBox="0 0 80 40"',
        'width="2cm" height="1cm"',
    ],
)
def test_svg_renders_at_logo_resolution_without_distortion(dimensions):
    image = Image.open(BytesIO(normalize_logo(upload(svg(dimensions=dimensions)))))
    assert image.format == "PNG"
    assert image.size == (1024, 512)
    assert image.getpixel((512, 256)) == (35, 87, 137, 255)
    assert not image.info


def test_local_gradients_css_and_reused_shapes_render_with_transparency():
    content = svg("""<style>.mark {fill:url(#gradient);opacity:0.5}</style>
        <defs><linearGradient id="gradient"><stop stop-color="red"/><stop offset="1" stop-color="blue"/></linearGradient>
        <path id="shape" d="M0 0H80V40H0Z"/></defs><use href="#shape" class="mark"/>""")
    image = Image.open(BytesIO(normalize_logo(upload(content))))
    assert image.size == (1024, 512)
    assert 125 <= image.getpixel((512, 256))[3] <= 130


def test_svg_can_be_used_as_favicon():
    image = Image.open(BytesIO(normalize_favicon(upload(svg()))))
    assert image.size == (256, 256)
    assert image.getchannel("A").getbbox() == (0, 64, 256, 192)


@pytest.mark.parametrize(
    "content",
    [
        b"<svg>",
        svg("", 'width="0" height="0"'),
        svg("", 'viewBox="0 0 nan 10"'),
        svg(""),
        svg("<script>alert(1)</script>"),
        svg("<foreignObject/>"),
        svg("<animate/>"),
        svg('<rect width="80" height="40" onload="alert(1)"/>'),
        svg('<image href="file:///etc/passwd"/>'),
        svg('<image href="http://127.0.0.1/private.png"/>'),
        svg('<use href="//example.test/a.svg#mark"/>'),
        svg(
            '<style>@import url("http://example.test/style.css");</style><rect width="80" height="40"/>'
        ),
        b'<!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg xmlns="http://www.w3.org/2000/svg" width="80" height="40"><text>&x;</text></svg>',
        svg(
            '<style>@import "http://example.test/style.css";</style><rect width="80" height="40"/>'
        ),
        svg(
            r'<style>@\69mport url("file:///etc/passwd");</style><rect width="80" height="40"/>'
        ),
        svg(
            '<rect width="80" height="40" fill="url(http://example.test/paint.svg#color)"/>'
        ),
        svg("<g>" * 66 + '<rect width="80" height="40"/>' + "</g>" * 66),
    ],
)
def test_invalid_or_active_svg_is_rejected_without_network_reads(content, monkeypatch):
    def fail_network(*args, **kwargs):
        pytest.fail("SVG must not fetch external resources")

    monkeypatch.setattr("urllib.request.urlopen", fail_network)
    with pytest.raises(InvalidLogoImageError):
        normalize_logo(upload(content))


def test_group_opacity_on_reused_shapes_is_composited_once():
    content = svg("""<defs><g id="shape"><rect width="60" height="40" fill="red"/>
        <rect x="20" width="60" height="40" fill="blue"/></g></defs>
        <use href="#shape" opacity="0.5"/>""")
    image = Image.open(BytesIO(normalize_logo(upload(content))))
    for x in (100, 512, 900):
        assert 125 <= image.getpixel((x, 256))[3] <= 130
    assert image.getpixel((100, 256))[0] > 250
    assert image.getpixel((512, 256))[2] > 250
