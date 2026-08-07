"""Reusable SVG chart/dial generators for the report, built per the dataviz
skill's conventions (status palette for the dial, area-wash + emphasized
median line for the fan chart, tabular-nums left to the caller's CSS).

Deliberately hand-rolled SVG rather than a charting library — the shapes
needed (a semicircular gauge, a percentile fan) are simple enough that exact
control over geometry is easier without one, and it keeps the report
pipeline dependency-free beyond WeasyPrint/Jinja2.

All fill/stroke/opacity is set via inline SVG presentation attributes, not
CSS classes — WeasyPrint doesn't reliably apply page-level CSS to SVG shape
elements (verified: a class-styled fill silently fell back to solid black).
Every SVG also declares explicit width/height attributes matching its
viewBox exactly, not just viewBox alone — relying on CSS `height: auto` to
infer aspect ratio produced a wildly oversized element that spilled across
several PDF pages. Colors are hardcoded hex here rather than reading
template.html.jinja's CSS custom properties (SVG presentation attributes
don't resolve `var()` reliably either) — keep ACCENT/INK below in sync with
the template's --accent/--ink by hand if either changes.
"""
from __future__ import annotations

import math

# Keep in sync with report/template.html.jinja's :root custom properties.
ACCENT = "#2c3a63"
INK = "#12191b"
INK_MUTED = "#7c8b8d"
GRID = "#e1e0d9"

# Status palette (fixed, from the dataviz skill — never re-themed)
GOOD = "#0ca30c"
WARNING = "#fab219"
CRITICAL = "#d03b3b"


def band_for(success_pct: float) -> tuple[str, str]:
    """(band_key, plain-English word) for a success percentage (0-100)."""
    if success_pct >= 95:
        return "green", "durable"
    if success_pct >= 90:
        return "yellow", "borderline"
    return "red", "needs a change"


def dial_svg(success_probability: float, size: int = 108) -> str:
    """A semicircular success-probability gauge: red [0,90) / yellow [90,95)
    / green [95,100], a triangle pointer at the current value, percentage in
    primary ink centered in the dial (never colored by the band — status
    color is a fill, not text; see the dataviz skill's contrast notes on why
    warning/critical can't carry a text label on a light surface)."""
    display_pct = math.floor(success_probability * 1000) / 10  # floor, never round across a band
    value_frac = success_probability
    band_key, _ = band_for(display_pct)

    cx, cy = 80, 90
    r_outer, r_inner = 74, 50
    gap_deg = 1.6
    half_gap = gap_deg / 2 / 180
    vb_w, vb_h = 160, 100
    height = round(size * vb_h / vb_w)

    def pt(r, frac):
        angle = math.radians(180 - 180 * frac)
        return cx + r * math.cos(angle), cy - r * math.sin(angle)

    def arc_path(f0, f1):
        ox0, oy0 = pt(r_outer, f0)
        ox1, oy1 = pt(r_outer, f1)
        ix0, iy0 = pt(r_inner, f0)
        ix1, iy1 = pt(r_inner, f1)
        large = 1 if abs((180 - 180 * f1) - (180 - 180 * f0)) > 180 else 0
        return (f"M {ox0:.2f} {oy0:.2f} A {r_outer} {r_outer} 0 {large} 1 {ox1:.2f} {oy1:.2f} "
                f"L {ix1:.2f} {iy1:.2f} A {r_inner} {r_inner} 0 {large} 0 {ix0:.2f} {iy0:.2f} Z")

    bands = [("red", CRITICAL, 0.0, 0.90), ("yellow", WARNING, 0.90, 0.95), ("green", GOOD, 0.95, 1.0)]
    band_paths = []
    for _, color, f0, f1 in bands:
        tf0 = f0 + (half_gap if f0 > 0 else 0)
        tf1 = f1 - (half_gap if f1 < 1 else 0)
        band_paths.append(f'<path d="{arc_path(tf0, tf1)}" fill="{color}"/>')

    angle = math.radians(180 - 180 * value_frac)
    tipx, tipy = pt(r_outer - 3, value_frac)
    basex, basey = pt(r_outer + 3 + 7.5, value_frac)
    perp = angle + math.pi / 2
    dx, dy = math.cos(perp), -math.sin(perp)
    b1x, b1y = basex + dx * 7.5 * 0.62, basey + dy * 7.5 * 0.62
    b2x, b2y = basex - dx * 7.5 * 0.62, basey - dy * 7.5 * 0.62
    pointer_pts = f"{tipx:.2f},{tipy:.2f} {b1x:.2f},{b1y:.2f} {b2x:.2f},{b2y:.2f}"

    return f'''<svg class="dial" width="{size}" height="{height}" viewBox="0 0 {vb_w} {vb_h}" role="img"
      aria-label="{display_pct:.1f} percent success probability, {band_key} band">
      {"".join(band_paths)}
      <polygon points="{pointer_pts}" fill="{INK}"/>
      <text x="80" y="76" text-anchor="middle" font-family="'Public Sans', sans-serif"
        font-weight="700" font-size="24" fill="{INK}">{display_pct:.1f}<tspan font-size="13" font-weight="600" fill="{INK_MUTED}">%</tspan></text>
    </svg>'''


def _fmt_compact(v: float) -> str:
    if abs(v) >= 1_000_000:
        return f"£{v/1_000_000:.1f}M"
    if abs(v) >= 1_000:
        return f"£{v/1_000:.0f}K"
    return f"£{v:,.0f}"


def fan_chart_svg(
    years: list[int],
    percentiles: dict[int, list[float]],
    horizon_years: int | None = None,
    width: int = 640,
    height: int = 280,
    label: str = "household wealth",
    alive_fraction: list[float] | None = None,
) -> str:
    """Value-over-time fan chart: p5-p95 wash, p10-p90 darker wash, p50
    median line emphasized with an end label. `percentiles` maps percentile
    (5/10/50/90/95) to a same-length list aligned with `years` — the same
    five bands the report's asset-mix table uses, so a chart and its table
    never disagree about which spread they're both calling "the range."

    **Defaults to the full horizon.** The end of the plotted line should
    land on the same year the report's bequest figures are read at
    (`result.n_years - 1`) — showing a shorter window here while quoting a
    bequest from a later one is exactly the kind of mismatch a reader
    catches and stops trusting the rest of the report over. Pass
    `horizon_years` only when you deliberately want a shorter window *and*
    are not placing a bequest-derived number next to it; a 40+ year full
    horizon does compress the early, more decision-relevant years toward
    the bottom of a linear axis when the tail is large — that is a real
    readability cost of showing the true end date, not a bug, and cropping
    the chart to hide it is the wrong fix for it.

    **Pass `alive_fraction` for any whole-household wealth chart.** Once
    mortality is sampled, a percentile band silently changes meaning as the
    cohort dies out: after the second death an estate is frozen, so a year in
    which most trials have ended is a median *of frozen estates*, not of
    living households. The visible symptom is a median that plateaus, and it
    reads as the money running out of steam when in fact households still
    alive are still compounding -- on one real plan the chart flattened at
    £6.5m while the still-living median was £8.0m and rising. This draws a
    rule at the year half the households have ended, so the reader can see
    where the line stops being about anyone alive.
    """
    n = len(years) if horizon_years is None else min(horizon_years, len(years))
    ys = years[:n]
    p5, p10, p50, p90, p95 = (percentiles[k][:n] for k in (5, 10, 50, 90, 95))

    pad_l, pad_r, pad_t, pad_b = 56, 16, 16, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    # A series that is exactly zero throughout (a GIA the drawdown never
    # needed, say) would otherwise divide by zero below. The skill tells
    # callers to skip a flat-zero asset type rather than chart it, but this
    # function should not crash if that check is missed -- render a flat
    # line at the bottom of a nominal axis instead of raising.
    y_max = max(max(p95) * 1.08, 1.0)
    y_min = 0.0

    # The year half the households have ended, if known.
    half_gone_at = None
    if alive_fraction:
        for i, share in enumerate(alive_fraction[:n]):
            if share < 0.5:
                half_gone_at = i
                break

    def xf(i):
        return pad_l + (i / (n - 1)) * plot_w if n > 1 else pad_l

    def yf(v):
        return pad_t + plot_h - (v - y_min) / (y_max - y_min) * plot_h

    def line_d(values):
        parts = [f"{'M' if i == 0 else 'L'} {xf(i):.1f} {yf(v):.1f}" for i, v in enumerate(values)]
        return " ".join(parts)

    def band_d(upper, lower):
        top = " ".join(f"{xf(i):.1f},{yf(v):.1f}" for i, v in enumerate(upper))
        bot = " ".join(f"{xf(i):.1f},{yf(v):.1f}" for i, v in reversed(list(enumerate(lower))))
        return f"M {top} L {bot} Z"

    y_ticks = 4
    grid = []
    for i in range(y_ticks + 1):
        v = y_min + (y_max - y_min) * i / y_ticks
        y = yf(v)
        grid.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" '
            f'stroke="{GRID}" stroke-width="0.6"/>'
            f'<text x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-family="\'Public Sans\', sans-serif" font-size="8" fill="{INK_MUTED}">{_fmt_compact(v)}</text>'
        )

    x_idx = sorted(set([0, n // 2, n - 1]))
    xticks = "".join(
        f'<text x="{xf(i):.1f}" y="{height - 6}" text-anchor="middle" '
        f'font-family="\'Public Sans\', sans-serif" font-size="8" fill="{INK_MUTED}">{ys[i]}</text>'
        for i in x_idx
    )

    end_x, end_y = xf(n - 1), yf(p50[-1])

    # Where the cohort has mostly ended, so a reader can see the point past
    # which the median is largely settled estates rather than living
    # households. Drawn as a rule rather than a truncation because the line
    # must still reach the year the bequest figures are read at.
    survivorship = ""
    if half_gone_at is not None and 0 < half_gone_at < n - 1:
        hx = xf(half_gone_at)
        survivorship = (
            f'<line x1="{hx:.1f}" y1="{pad_t}" x2="{hx:.1f}" y2="{height - pad_b}" '
            f'stroke="{INK_MUTED}" stroke-width="1" stroke-dasharray="3 3"/>'
            f'<text x="{hx + 4:.1f}" y="{pad_t + 9}" text-anchor="start" '
            f'font-family="\'Public Sans\', sans-serif" font-size="7.5" '
            f'fill="{INK_MUTED}">half of outcomes ended by {ys[half_gone_at]}</text>'
        )

    return f'''<svg class="fanchart" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img"
      aria-label="Projected {label} over time, 5th to 95th percentile range">
      {"".join(grid)}
      <path d="{band_d(p95, p5)}" fill="{ACCENT}" fill-opacity="0.10"/>
      <path d="{band_d(p90, p10)}" fill="{ACCENT}" fill-opacity="0.18"/>
      {survivorship}
      <path d="{line_d(p50)}" fill="none" stroke="{ACCENT}" stroke-width="2"/>
      <circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="3.5" fill="{ACCENT}"/>
      <text x="{end_x - 8:.1f}" y="{end_y - 10:.1f}" text-anchor="end"
        font-family="'Public Sans', sans-serif" font-size="8.5" font-weight="700" fill="{ACCENT}">{_fmt_compact(p50[-1])} median</text>
      {xticks}
    </svg>'''
