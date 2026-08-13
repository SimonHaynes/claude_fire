"""The year-by-year cash-flow chart: where each year's money comes from, and
what it has to cover.

One bar per plan year, stacked by source, from a *single deterministic
projection* — not from the Monte Carlo. A percentile band cannot be stacked:
the trial at the median for pension drawdown is not the trial at the median for
ISA withdrawals, so bands built from percentiles would sum to a year that no
simulated household ever lived. The caption this chart ships with has to say
that it is one path at average returns; the fan charts carry the range.

Three reference lines rather than three more colours: they are all pounds per
year on the same axis, so they are separated by weight and dash — solid heavy
for what is left after tax, solid light for total spending, dashed for
essentials. The gap between the top of a bar and the heavy line is the tax
bill; the gap between the two lighter lines is the discretionary spending a
guardrail is allowed to cut.

Palette: slots blue/aqua/violet/green/magenta/yellow from the dataviz skill's
documented categorical order, re-ordered and validated as a set for this
chart's *adjacent* pairlist (`scripts/validate_palette.py`, light mode on a
white surface): worst adjacent CVD ΔE 16.3, worst adjacent normal-vision ΔE
19.6, against floors of 8 and 15. Aqua, magenta and yellow sit below 3:1
against white, so the relief rule applies and the legend is not optional —
every band is named there, and identity is never colour alone. Red is the
reserved critical status, used only for an unfunded year.

Two deliberate deviations from the skill's mark specs, both forced by print
scale: stacked segments are separated by a 0.6pt surface hairline rather than a
2px gap (at 40 bars in 570pt a 2px gap erases any segment under about £4,000),
and the gap is dropped entirely on segments too short to survive it. Nothing
here is interactive — it is a PDF.

All fill/stroke is set inline, and width/height match the viewBox exactly, for
the WeasyPrint reasons documented in `charts.py`.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from .charts import GRID, INK, INK_MUTED, _fmt_compact

if TYPE_CHECKING:
    from ..cashflow import Projection, YearResult

CRITICAL = "#d03b3b"
SURFACE = "#ffffff"
#: The template's --ink-2. Dark enough to stay legible drawn straight over a
#: bar, which --ink-muted is not.
INK_2 = "#4c5a5c"

#: Validated as an ordered set for the adjacent pairlist. Re-ordering these or
#: adding a seventh means re-running the validator, not eyeballing the result.
_BLUE, _AQUA, _VIOLET, _GREEN, _MAGENTA, _YELLOW = (
    "#2a78d6", "#1baf7a", "#4a3aa7", "#008300", "#e87ba4", "#eda100",
)


@dataclass(frozen=True)
class Source:
    """One stacked band: what to call it, what colour, and how to read it off a
    year. Bottom of the stack first, and cool-to-warm up the stack so that
    money drawn from capital reads warm and sits above money that arrives."""

    key: str
    label: str
    color: str
    amount: Callable[["YearResult"], float]


#: The six bands partition everything a year has to spend — income plus capital
#: drawn — with no double-counting. Two traps: `dc_withdrawn_gross` already
#: contains `ufpls_tax_free_taken`, and `other_taxable_income` already contains
#: `income_annuity_income`. The annuity premium is not here at all: it moves
#: capital from a pension into an annuity and never reaches a spendable pound.
SOURCES: tuple[Source, ...] = (
    Source("employment", "Employment", _BLUE, lambda y: y.employment_income),
    Source("state_pension", "State Pension", _AQUA, lambda y: y.state_pension_income),
    Source("guaranteed", "DB pension and annuity", _VIOLET,
           lambda y: y.db_income + y.income_annuity_income),
    Source("other_income", "Other income", _GREEN,
           lambda y: y.other_taxable_income - y.income_annuity_income + y.tax_free_income),
    Source("pension_drawn", "Pension drawn", _MAGENTA,
           lambda y: y.dc_withdrawn_gross + y.pcls_taken + y.pension_lump_sum_taken),
    Source("savings_drawn", "ISA and GIA drawn", _YELLOW,
           lambda y: y.isa_withdrawn + y.gia_withdrawn),
)

#: Not income: the part of a year's spending nothing could fund, stacked on top
#: so the bar still reconciles to the spending line. Reserved critical red, and
#: labelled, because a reader must never have to infer a failed year from a hue.
SHORTFALL = Source("shortfall", "Not funded", CRITICAL, lambda y: y.unmet_shortfall)


@dataclass(frozen=True)
class LifePhase:
    """A named stretch of the plan, drawn as a labelled band under the axis.

    `from_year` is the first calendar year of the phase; the phase runs until
    the next one starts. Beyond "working" and "retired" these are the client's
    own account of their retirement, not something the engine can infer, so
    they are passed in rather than derived.
    """

    label: str
    from_year: int


@dataclass(frozen=True)
class KeyEvent:
    """A dated marker on the phase band. `icon` keys into `ICONS`; an unknown
    key draws the fallback dot rather than raising, so a typo in a report
    costs a glyph and not a build."""

    year: int
    label: str
    icon: str = "milestone"


#: Stroke-only glyphs on a 24x24 grid, centred on (12, 12) and scaled into the
#: marker circle. Stroke rather than fill so one `stroke-width` keeps every
#: icon at the same visual weight when scaled down to 13pt.
ICONS: dict[str, str] = {
    "start": "M9 6 L18 12 L9 18 Z",
    "work": "M4 9 H20 V19 H4 Z M9 9 V6 H15 V9",
    "retire": "M3 13 A9 9 0 0 1 21 13 Z M12 13 V20 M12 20 A2.5 2.5 0 0 0 16 20",
    "state": "M4 8 L8 12 L12 6 L16 12 L20 8 V17 H4 Z",
    "pension": "M4 10 A8 5 0 1 0 20 10 A8 5 0 1 0 4 10 M4 10 V15 A8 5 0 0 0 20 15 V10",
    "cash": "M3 7 H21 V17 H3 Z M12 9.5 A2.5 2.5 0 0 1 12 14.5 A2.5 2.5 0 0 1 12 9.5",
    "gift": "M3 11 H21 V20 H3 Z M12 11 V20 M12 11 C12 7 9 5 7.5 6.5 C6 8 8 11 12 11 "
            "C12 7 15 5 16.5 6.5 C18 8 16 11 12 11",
    "house": "M3 12 L12 4 L21 12 M6 11 V20 H18 V11",
    "travel": "M2 14 L22 8 M2 14 L8 16 M8 16 L12 20 L14 14 M14 14 L22 8",
    "annuity": "M12 3 L20 6 V12 C20 17 16 20 12 21 C8 20 4 17 4 12 V6 Z",
    "care": "M12 20 C6 15 3 12 3 9 A4 4 0 0 1 12 7 A4 4 0 0 1 21 9 C21 12 18 15 12 20 Z",
    "milestone": "M7 4 V21 M7 5 H19 L16 9 L19 13 H7",
}
_ICON_FALLBACK = "M12 8 A4 4 0 0 1 12 16 A4 4 0 0 1 12 8"

#: Ordinal, because the only thing distinguishing one phase from the next is
#: where it falls in the plan. Navy through slate to sage: distinct from the
#: bar hues by being desaturated, and dark enough throughout for white labels.
_PHASE_COLORS = ("#2c3a63", "#3d5878", "#4e7683", "#5f8d80", "#6f9c78")

_PAD_L, _PAD_R, _PAD_T = 54, 12, 14
#: Room for a whole event marker between the plot and the phase band. The
#: markers rest on the band rather than straddling it, so the band's height is
#: free to suit its label instead of having to clear half a circle.
_AXIS_H = 26
_BAND_H = 15
_EVENT_ROW_H = 10
_LEGEND_ROW_H = 13
_ICON_R = 6.6


def _live_years(projection: "Projection") -> list["YearResult"]:
    """Years with someone alive in them. The projection pads to a fixed length
    with frozen-balance years so trials can be reduced across a common grid;
    charting that tail draws a decade of empty bars."""
    last = max((i for i, y in enumerate(projection.years) if y.alive), default=-1)
    return projection.years[: last + 1]


def derive_phases(projection: "Projection") -> tuple[LifePhase, ...]:
    """Working / Retired / Needing care, which is all the engine itself knows.

    A report that wants "Travelling" or "Slowing down" has to say when those
    start — they are a client's plan for their retirement, not a model output.
    """
    years = _live_years(projection)
    if not years:
        return ()
    already_retired = years[0].is_retired
    phases = [LifePhase("Retired" if already_retired else "Working", years[0].year)]
    if not already_retired:
        retires = next((y for y in years if y.is_retired), None)
        if retires is not None:
            phases.append(LifePhase("Retired", retires.year))
    care = next((y for y in years if y.care_cost > 0), None)
    if care is not None and care.year > phases[-1].from_year:
        phases.append(LifePhase("Needing care", care.year))
    return tuple(phases)


def derive_events(projection: "Projection") -> tuple[KeyEvent, ...]:
    """Every dated fact the projection actually contains, once each.

    Deliberately only firsts, plus one-offs and gifts: a marker on every year a
    pension is drawn is not a key event, it is the bar chart again.
    """
    years = _live_years(projection)
    events: list[KeyEvent] = []

    def first(label: str, icon: str, test: Callable[["YearResult"], bool]) -> None:
        year = next((y for y in years if test(y)), None)
        if year is not None:
            events.append(KeyEvent(year.year, label, icon))

    first("Retire", "retire", lambda y: y.is_retired)
    first("Annuity bought", "annuity", lambda y: y.income_annuity_premium > 0)
    first("Tax-free cash", "cash",
          lambda y: y.pcls_taken + y.ufpls_tax_free_taken + y.pension_lump_sum_taken > 0)
    first("Pension drawdown", "pension", lambda y: y.dc_withdrawn_gross > 0)
    first("State Pension", "state", lambda y: y.state_pension_income > 0)
    first("Care begins", "care", lambda y: y.care_cost > 0)

    events += [KeyEvent(y.year, "One-off spend", "house") for y in years if y.one_off_spending > 0]
    events += [KeyEvent(y.year, "Gift", "gift") for y in years if y.gifts_given > 0]
    return tuple(sorted(events, key=lambda e: e.year))


def _icon_svg(icon: str, cx: float, cy: float, color: str) -> str:
    path = ICONS.get(icon, _ICON_FALLBACK)
    scale = (_ICON_R * 2 * 0.62) / 24
    tx, ty = cx - 12 * scale, cy - 12 * scale
    return (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{_ICON_R}" fill="{SURFACE}" '
        f'stroke="{color}" stroke-width="1.3"/>'
        f'<g transform="translate({tx:.2f} {ty:.2f}) scale({scale:.4f})">'
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.2" '
        f'stroke-linecap="round" stroke-linejoin="round"/></g>'
    )


def _place_events(events, x_of, rows: int = 2) -> list[tuple]:
    """(event, marker x, label row) for each event that fits.

    Two events in one year would draw one circle on top of another, so a year's
    markers are spread either side of its bar. Labels are then packed into the
    topmost row that clears whatever is already there; one that fits in no row
    is dropped rather than overprinted, since its date is in the timeline
    section anyway and a smear of overlapping words is worth less than nothing.
    """
    by_year: dict[int, list] = {}
    for event in events:
        by_year.setdefault(event.year, []).append(event)

    spread: list[tuple] = []
    for year, group in by_year.items():
        step = _ICON_R * 3.0
        left = x_of(year) - (len(group) - 1) * step / 2
        spread += [(event, left + k * step) for k, event in enumerate(group)]
    spread.sort(key=lambda pair: pair[1])

    placed: list[tuple] = []
    right_edge = [float("-inf")] * rows
    for event, x in spread:
        half = len(event.label) * 1.65 + 3
        for row in range(rows):
            if x - half >= right_edge[row]:
                right_edge[row] = x + half
                placed.append((event, x, row))
                break
    return placed


def _nice_axis(value: float) -> tuple[float, int]:
    """(top of axis, number of intervals) for a scale reaching `value`.

    The smallest 1/2/2.5/5 x 10^k step covering it in four to six intervals, so
    gridlines land on figures a reader recognises rather than on £134K.
    """
    if value <= 0:
        return 1.0, 4
    magnitude = 10 ** math.floor(math.log10(value / 4))
    for multiple in (1, 2, 2.5, 5, 10, 20):
        step = multiple * magnitude
        intervals = math.ceil(value / step)
        if 4 <= intervals <= 6:
            return step * intervals, intervals
    return value, 4


def cashflow_chart_svg(
    projection: "Projection",
    *,
    phases: tuple[LifePhase, ...] | None = None,
    events: tuple[KeyEvent, ...] | None = None,
    width: int = 462,
    height: int = 300,
) -> str:
    """The cash-flow chart for one deterministic projection.

    `phases` and `events` default to what the projection itself dates (see
    `derive_phases` / `derive_events`); pass your own to name the stretches of
    retirement a client actually described. Empty tuples suppress either.

    `height` is the whole SVG. The axis, phase band, event labels and legend
    take fixed room out of it, so a taller chart is a taller plot.

    **The default width is the report's own text measure in points**, so one
    SVG unit renders as one point and the font sizes here are the sizes on
    paper. Authoring wider and letting `width: 100%` scale it down shrinks
    every label with it — at 660 units in a 462pt column the event labels come
    out at 4.6pt, which is legible on screen and not on paper. Change this
    only alongside the font sizes.
    """
    years = _live_years(projection)
    if not years:
        raise ValueError("projection has no years with anyone alive in it")

    phases = derive_phases(projection) if phases is None else phases
    events = derive_events(projection) if events is None else events

    labels = [y.year for y in years]
    n = len(years)
    # A marker or a band for a year off the end of the plot would otherwise be
    # drawn against the left edge, which reads as an event in the first year.
    events = tuple(e for e in events if e.year in labels)
    phases = tuple(p for p in phases if p.from_year in labels)
    bands = [(s, [s.amount(y) for y in years]) for s in (*SOURCES, SHORTFALL)]
    bands = [(s, vs) for s, vs in bands if any(v > 0.5 for v in vs)]

    net_after_tax = [y.gross_income + _capital_drawn(y) - y.tax_paid - y.ni_paid for y in years]
    total_spend = [y.total_spending + y.debt_payments + y.one_off_spending + y.gifts_given
                   for y in years]
    essentials = [y.essential_spending + y.debt_payments for y in years]

    legend_rows = -(-(len(bands) + 3) // 3)
    chrome = (_AXIS_H + _BAND_H + _EVENT_ROW_H * 2 + _LEGEND_ROW_H * legend_rows + 8)
    plot_h = height - _PAD_T - chrome
    plot_w = width - _PAD_L - _PAD_R
    if plot_h < 60:
        raise ValueError(f"height={height} leaves {plot_h:.0f}pt of plot; raise it")

    totals = [sum(vs[i] for _, vs in bands) for i in range(n)]
    y_max, y_intervals = _nice_axis(max(*totals, *total_spend, 1.0))

    slot_w = plot_w / n
    bar_w = max(1.6, slot_w - min(1.4, slot_w * 0.18))
    bar_pad = (slot_w - bar_w) / 2

    def x_left(i: int) -> float:
        return _PAD_L + i * slot_w + bar_pad

    def x_mid_of_year(year: int) -> float:
        return x_left(labels.index(year)) + bar_w / 2

    def yf(v: float) -> float:
        return _PAD_T + plot_h - (v / y_max) * plot_h

    grid = []
    for i in range(y_intervals + 1):
        v = y_max * i / y_intervals
        y = yf(v)
        grid.append(
            f'<line x1="{_PAD_L}" y1="{y:.1f}" x2="{width - _PAD_R}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="0.6"/>'
            f'<text x="{_PAD_L - 7}" y="{y + 3.6:.1f}" text-anchor="end" '
            f'font-family="\'Public Sans\', sans-serif" font-size="7.5" '
            f'fill="{INK_MUTED}">{_fmt_compact(v)}</text>'
        )

    rects = []
    for i in range(n):
        cursor = yf(0.0)
        for source, values in bands:
            v = values[i]
            if v <= 0:
                continue
            h = (v / y_max) * plot_h
            gap = 0.6 if h > 2.4 else 0.0
            rects.append(
                f'<rect x="{x_left(i):.2f}" y="{cursor - h:.2f}" width="{bar_w:.2f}" '
                f'height="{h - gap:.2f}" fill="{source.color}"/>'
            )
            cursor -= h

    def step_d(values: list[float]) -> str:
        parts = []
        for i, v in enumerate(values):
            y = yf(v)
            parts.append(f'{"M" if i == 0 else "L"} {x_left(i):.2f} {y:.2f}')
            parts.append(f'L {x_left(i) + bar_w:.2f} {y:.2f}')
        return " ".join(parts)

    def step_line(values: list[float], color: str, w: float, dash: str = "") -> str:
        dasharray = f' stroke-dasharray="{dash}"' if dash else ""
        return (
            f'<path d="{step_d(values)}" fill="none" stroke="{color}" stroke-width="{w}"'
            f'{dasharray} stroke-linejoin="round"/>'
        )

    # Drawn straight onto the bars. A surface-coloured halo would separate them
    # from the fills more cleanly, but at these weights it reads as a white
    # smear along every line, so the two reference lines carry secondary ink
    # rather than muted ink to hold their contrast over the darker bands.
    lines = (
        step_line(total_spend, INK_2, 1.4)
        + step_line(essentials, INK_2, 1.3, dash="2.5 2")
        + step_line(net_after_tax, INK, 1.9)
    )

    tick_step = max(1, round(n / 8 / 5) * 5) if n > 12 else max(1, n // 6)
    x_idx = sorted({0, *range(0, n, tick_step), n - 1})
    axis_y = _PAD_T + plot_h + _AXIS_H - 2 * _ICON_R - 5
    xticks = "".join(
        f'<text x="{x_left(i) + bar_w / 2:.1f}" y="{axis_y:.1f}" text-anchor="middle" '
        f'font-family="\'Public Sans\', sans-serif" font-size="7.5" '
        f'fill="{INK_MUTED}">{labels[i]}</text>'
        for i in x_idx
    )

    band_top = _PAD_T + plot_h + _AXIS_H
    band_parts = []
    for j, phase in enumerate(phases):
        start = labels.index(phase.from_year)
        end = labels.index(phases[j + 1].from_year) if j + 1 < len(phases) else n
        if end <= start:
            continue
        x0 = _PAD_L + start * slot_w
        x1 = _PAD_L + end * slot_w
        color = _PHASE_COLORS[j % len(_PHASE_COLORS)]
        band_parts.append(
            f'<rect x="{x0:.1f}" y="{band_top:.1f}" width="{x1 - x0 - 1:.1f}" '
            f'height="{_BAND_H}" rx="2.5" fill="{color}"/>'
            # Optically centred: a baseline at the band's midpoint hangs the
            # label low, so it sits half a cap-height (8pt Public Sans) below.
            f'<text x="{(x0 + x1) / 2:.1f}" y="{band_top + _BAND_H / 2 + 2.9:.1f}" '
            f'text-anchor="middle" font-family="\'Public Sans\', sans-serif" '
            f'font-size="8" font-weight="600" fill="{SURFACE}">{phase.label}</text>'
        )

    # Resting on the band's upper edge, not straddling it: a marker that
    # overlaps the band prints through the phase label, which is the one piece
    # of text on it.
    marker_y = band_top - _ICON_R - 0.5
    markers, event_labels = [], []
    for event, x, row in _place_events(events, x_mid_of_year):
        markers.append(_icon_svg(event.icon, x, marker_y, INK))
        label_y = band_top + _BAND_H + 8 + row * _EVENT_ROW_H
        # A leader from the band down to the label. Two events in one year sit
        # side by side with their labels on different rows, and without a
        # leader the reader cannot tell which name belongs to which icon.
        event_labels.append(
            f'<line x1="{x:.1f}" y1="{band_top + _BAND_H:.1f}" x2="{x:.1f}" '
            f'y2="{label_y - 5.5:.1f}" stroke="{INK_MUTED}" stroke-width="0.5" '
            f'stroke-opacity="0.55"/>'
            f'<text x="{x:.1f}" y="{label_y:.1f}" '
            f'text-anchor="middle" font-family="\'Public Sans\', sans-serif" '
            f'font-size="6.6" fill="{INK_MUTED}">{event.label}</text>'
        )

    legend_top = band_top + _BAND_H + _EVENT_ROW_H * 2 + 6
    entries = [(s.label, s.color, "swatch") for s, _ in bands] + [
        ("After tax and NI", INK, "line"),
        ("Total spending", INK_MUTED, "line"),
        ("Essentials", INK_MUTED, "dash"),
    ]
    col_w = (width - _PAD_L - _PAD_R) / 3
    legend = []
    for k, (text, color, kind) in enumerate(entries):
        lx = _PAD_L + (k % 3) * col_w
        ly = legend_top + (k // 3) * _LEGEND_ROW_H
        if kind == "swatch":
            mark = (f'<rect x="{lx:.1f}" y="{ly - 5:.1f}" width="8" height="8" rx="1.5" '
                    f'fill="{color}" stroke="{GRID}" stroke-width="0.5"/>')
        else:
            dash = ' stroke-dasharray="2.5 2"' if kind == "dash" else ""
            mark = (f'<line x1="{lx:.1f}" y1="{ly - 1:.1f}" x2="{lx + 8:.1f}" y2="{ly - 1:.1f}" '
                    f'stroke="{color}" stroke-width="{1.9 if kind == "line" and color == INK else 1.4}"'
                    f'{dash}/>')
        legend.append(
            mark + f'<text x="{lx + 12:.1f}" y="{ly + 2:.1f}" '
            f'font-family="\'Public Sans\', sans-serif" font-size="7.4" '
            f'fill="{INK_MUTED}">{text}</text>'
        )

    return f'''<svg class="cashflow-chart" width="{width}" height="{height}" viewBox="0 0 {width} {height}"
      role="img" aria-label="Income by source for each year of the plan, {labels[0]} to {labels[-1]},
      with lines for spending and for income after tax">
      {"".join(grid)}
      {"".join(rects)}
      {lines}
      {xticks}
      {"".join(band_parts)}
      {"".join(markers)}
      {"".join(event_labels)}
      {"".join(legend)}
    </svg>'''


def _capital_drawn(year: "YearResult") -> float:
    """Money out of the portfolio, over and above income. `dc_withdrawn_gross`
    already contains any UFPLS tax-free cash, so only the separately-taken
    lump sums are added to it."""
    return (
        year.dc_withdrawn_gross + year.pcls_taken + year.pension_lump_sum_taken
        + year.isa_withdrawn + year.gia_withdrawn
    )
