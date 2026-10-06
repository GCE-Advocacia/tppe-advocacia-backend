"""Render static SVG uploads without loading resources from disk or the network."""

import math
import re
from xml.etree.ElementTree import ParseError, tostring

import tinycss2
from cairocffi import CairoError
from cairosvg.surface import PNGSurface
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import fromstring

from app.shared.exceptions import InvalidLogoImageError, InvalidMimeTypeError

_SVG_NS = "http://www.w3.org/2000/svg"
_MAX_ELEMENTS = 10_000
_MAX_DEPTH = 64
_LENGTH = re.compile(r"^\s*(\d+(?:\.\d*)?|\.\d+)\s*(px|pt|pc|mm|cm|in)?\s*$")
_UNITS = {
    None: 1,
    "px": 1,
    "pt": 96 / 72,
    "pc": 16,
    "mm": 96 / 25.4,
    "cm": 96 / 2.54,
    "in": 96,
}


class _LogoSurface(PNGSurface):
    def draw(self, node):
        # CairoSVG 2.9.1 skips group opacity on <use> because its referenced
        # children are drawn indirectly. Composite that node as a group.
        opacity = float(node.get("opacity", 1))
        if node.tag != "use" or opacity >= 1:
            return super().draw(node)
        self.context.push_group()
        node["opacity"] = "1"
        try:
            super().draw(node)
        finally:
            node["opacity"] = str(opacity)
            self.context.pop_group_to_source()
        self.context.paint_with_alpha(max(0, opacity))


def _validate_css(value: str) -> None:
    tokens = list(tinycss2.parse_component_value_list(value))
    while tokens:
        token = tokens.pop()
        if token.type == "error" or (
            token.type == "at-keyword" and token.value.lower() == "import"
        ):
            raise InvalidLogoImageError()
        if token.type == "url" and not token.value.strip().startswith("#"):
            raise InvalidLogoImageError()
        if token.type == "function":
            if token.lower_name == "url":
                parts = [
                    part
                    for part in token.arguments
                    if part.type not in {"whitespace", "comment"}
                ]
                if (
                    len(parts) != 1
                    or parts[0].type != "string"
                    or not parts[0].value.strip().startswith("#")
                ):
                    raise InvalidLogoImageError()
            tokens.extend(token.arguments)
        tokens.extend(getattr(token, "content", ()) or ())


def _length(value: str | None) -> float | None:
    match = _LENGTH.fullmatch(value or "")
    if not match:
        return None
    length = float(match[1]) * _UNITS[match[2]]
    if not math.isfinite(length) or length <= 0:
        raise InvalidLogoImageError()
    return length


def _deny_resource(*args, **kwargs):
    # This is also used for CSS imports and indirect references inside <use>.
    raise InvalidLogoImageError()


def render_svg(content: bytes, max_dimension: int) -> bytes:
    try:
        root = fromstring(
            content, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
        if root.tag not in {"svg", f"{{{_SVG_NS}}}svg"}:
            raise InvalidMimeTypeError(
                ["image/png", "image/jpeg", "image/webp", "image/svg+xml"]
            )
        stack = [(root, 0)]
        count = 0
        while stack:
            element, depth = stack.pop()
            count += 1
            if count > _MAX_ELEMENTS or depth > _MAX_DEPTH:
                raise InvalidLogoImageError()
            name = element.tag.rsplit("}", 1)[-1]
            if name.lower() in {
                "script",
                "foreignobject",
                "animate",
                "animatetransform",
                "animatemotion",
                "set",
            }:
                raise InvalidLogoImageError()
            if name.lower() == "style" and element.text:
                _validate_css(element.text)
            for attribute, value in element.attrib.items():
                local = attribute.rsplit("}", 1)[-1].lower()
                if local in {
                    "style",
                    "fill",
                    "stroke",
                    "filter",
                    "clip-path",
                    "mask",
                    "marker",
                    "marker-start",
                    "marker-mid",
                    "marker-end",
                    "cursor",
                }:
                    _validate_css(value)
                if local.startswith("on") or (
                    local == "href" and not value.strip().startswith("#")
                ):
                    raise InvalidLogoImageError()
                if attribute == "{http://www.w3.org/XML/1998/namespace}base":
                    raise InvalidLogoImageError()
            stack.extend((child, depth + 1) for child in element)

        viewbox = root.get("viewBox")
        box = None
        if viewbox:
            box = [float(number) for number in re.split(r"[\s,]+", viewbox.strip())]
            if (
                len(box) != 4
                or not all(math.isfinite(number) for number in box)
                or min(box[2:]) <= 0
            ):
                raise InvalidLogoImageError()
        width, height = _length(root.get("width")), _length(root.get("height"))
        if box:
            width = width or (height * box[2] / box[3] if height else box[2])
            height = height or width * box[3] / box[2]
        if not width or not height or not math.isfinite(width / height):
            raise InvalidLogoImageError()
        scale = max_dimension / max(width, height)
        output_width = max(1, round(width * scale))
        output_height = max(1, round(height * scale))
        # Supply an explicit viewport for SVGs exported with percentages/viewBox.
        root.set("width", str(width))
        root.set("height", str(height))
        return _LogoSurface.convert(
            bytestring=tostring(root),
            unsafe=False,
            url_fetcher=_deny_resource,
            output_width=output_width,
            output_height=output_height,
        )
    except (
        DefusedXmlException,
        ParseError,
        ValueError,
        TypeError,
        OverflowError,
        ZeroDivisionError,
        CairoError,
        RecursionError,
        OSError,
    ) as exc:
        raise InvalidLogoImageError() from exc
