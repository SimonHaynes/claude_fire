"""Report generation: charts, and the seven-section client PDF.

Needs the optional extra:  pip install "retireplan[report]"

`charts` is import-safe without it (it only builds SVG strings); `render`
imports jinja2/weasyprint lazily, so the core engine stays dependency-free.
"""
from .cashflow_chart import (
    KeyEvent, LifePhase, cashflow_chart_svg, derive_events, derive_phases,
)
from .charts import band_for, dial_svg, fan_chart_svg
from .checks import ReportContextError, check_report
from .render import render_html, render_pdf

__all__ = [
    "KeyEvent", "LifePhase", "ReportContextError", "band_for",
    "cashflow_chart_svg", "check_report", "derive_events", "derive_phases",
    "dial_svg", "fan_chart_svg", "render_html", "render_pdf",
]
