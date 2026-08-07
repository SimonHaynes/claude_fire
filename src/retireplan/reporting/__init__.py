"""Report generation: charts, and the seven-section client PDF.

Needs the optional extra:  pip install "retireplan[report]"

`charts` is import-safe without it (it only builds SVG strings); `render`
imports jinja2/weasyprint lazily, so the core engine stays dependency-free.
"""
from .charts import band_for, dial_svg, fan_chart_svg
from .checks import ReportContextError, check_report
from .render import render_html, render_pdf

__all__ = [
    "ReportContextError", "band_for", "check_report", "dial_svg",
    "fan_chart_svg", "render_html", "render_pdf",
]
