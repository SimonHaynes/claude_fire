"""HTML -> PDF rendering for the client report.

WeasyPrint rather than a headless browser: it is pure Python over the system
Pango/Cairo, so it works where installing a ~300MB browser is not an option.
Its CSS support is close to a browser's but not identical, so *look at the
output* — page-break control needs `break-inside: avoid` more often than you
would expect, and SVG shapes do not reliably inherit page-level CSS (which is
why `charts.py` sets every fill inline).

Requires the optional extra:  pip install "retireplan[report]"
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from .checks import check_report

PACKAGE_DIR = Path(__file__).parent
TEMPLATE_DIR = PACKAGE_DIR / "templates"
FONTS_DIR = PACKAGE_DIR / "assets" / "fonts"
DEFAULT_TEMPLATE = "report.html.jinja"


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def font_context() -> dict[str, str]:
    """Fonts as base64 for inlining, so the PDF carries no external references."""
    return {
        "fraunces_b64": _b64(FONTS_DIR / "fraunces.woff2"),
        "publicsans_b64": _b64(FONTS_DIR / "publicsans.woff2"),
    }


def render_html(
    context: dict[str, Any],
    template: str = DEFAULT_TEMPLATE,
    template_dir: Path | str | None = None,
) -> str:
    import jinja2

    check_report(context)
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir or TEMPLATE_DIR)),
        autoescape=jinja2.select_autoescape(["html", "jinja"]),
    )
    return env.get_template(template).render(**{**font_context(), **context})


def render_pdf(
    context: dict[str, Any],
    out_path: str | Path,
    template: str = DEFAULT_TEMPLATE,
    template_dir: Path | str | None = None,
    also_write_html: bool = True,
) -> Path:
    """Render `context` to a PDF, and by default the HTML beside it.

    Keeping the HTML makes layout debugging survivable: it opens in a browser
    instantly, whereas diagnosing a page break by re-rendering PDFs is slow
    and tells you less.
    """
    from weasyprint import HTML

    html = render_html(context, template=template, template_dir=template_dir)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(TEMPLATE_DIR)).write_pdf(str(out_path))
    if also_write_html:
        out_path.with_suffix(".html").write_text(html)
    return out_path
