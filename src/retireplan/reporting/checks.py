"""Structural checks run over a report context before it renders.

Three rules in this project were, for a long time, prose that everybody agreed
with and that shipped broken anyway:

  * quote the estate net of tax, not gross;
  * do not hand the template a pre-escaped string;
  * do not write markdown into a template that has no markdown filter.

Each of those reached a rendered PDF at least once. Prose could not stop them
because the failure is invisible at the point it is made -- a gross bequest
looks like a number, `&amp;` looks like an ampersand in the source, and
`**bold**` looks like emphasis until it is printed. So they are checks now, and
they raise rather than warn: a report is a small number of numbers in front of
someone making a large decision, and rendering anyway is not a useful fallback.

`ReportContextError` is deliberately not catchable-by-accident -- if a check
fires, the fix is the context, never a suppression.
"""
from __future__ import annotations

import re
from typing import Any

#: Entities that mean a string was escaped before the template saw it. The
#: template autoescapes some fields and marks others `|safe`, so a
#: pre-escaped string renders wrong exactly one of those two ways.
_HTML_ENTITY = re.compile(r"&(?:amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);")

#: Markdown emphasis, which this template renders as literal asterisks.
_MARKDOWN_EMPHASIS = re.compile(r"\*\*[^*\n]+\*\*|(?<!\*)\*[^*\n]+\*(?!\*)")

#: Fields whose value reaches the reader as a name rather than as prose, and
#: which appear in both an autoescaped and a `|safe` position.
_PLAIN_TEXT_FIELDS = ("client_name",)


class ReportContextError(ValueError):
    """A report context would render something wrong or misleading."""


def _walk(node: Any, path: str = ""):
    """Yield every (path, string) in a nested context."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _walk(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _walk(value, f"{path}[{i}]")


def check_report(context: dict[str, Any]) -> None:
    """Raise `ReportContextError` if `context` breaks a report invariant.

    Called by `render_html`, so every rendered report is checked whether or not
    the caller remembered to.
    """
    problems: list[str] = []

    for field in _PLAIN_TEXT_FIELDS:
        value = context.get(field)
        if isinstance(value, str) and _HTML_ENTITY.search(value):
            problems.append(
                f"{field} contains an HTML entity ({value!r}). Pass it as plain "
                f"text -- 'Pat & Robin Smith', not 'Pat &amp; Robin Smith'. "
                f"The title autoescapes and the footer is |safe, so a "
                f"pre-escaped string renders wrong in one of the two."
            )

    for path, text in _walk(context):
        # SVG is generated, not authored, and legitimately contains markup.
        if "svg" in path.lower():
            continue
        match = _MARKDOWN_EMPHASIS.search(text)
        if match:
            problems.append(
                f"{path} contains markdown emphasis ({match.group(0)!r}). The "
                f"template has no markdown filter, so this renders as literal "
                f"asterisks. Use a real tag in a |safe field, or restructure."
            )

    problems.extend(_check_bequest_is_net(context))

    if problems:
        raise ReportContextError(
            "report context would render something wrong:\n  - "
            + "\n  - ".join(problems)
        )


def _check_bequest_is_net(context: dict[str, Any]) -> list[str]:
    """The results table must quote what reaches the heirs, not the estate.

    For a pension-heavy estate the gross figure overstates the inheritance by
    more than half, and the goal a client states is almost always about what
    the children actually receive. A previous report quoted gross for two
    revisions before anyone noticed.
    """
    rows = (context.get("section3") or {}).get("rows")
    if not isinstance(rows, (list, tuple)):
        return []

    problems = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        if "net_bequest_range" not in row:
            gross = "bequest_range" in row
            problems.append(
                f"section3.rows[{i}] has no net_bequest_range"
                + (
                    " (it has bequest_range, which is the gross estate before "
                    "IHT and the beneficiaries' income tax on an inherited "
                    "pension). Use net_bequest_percentiles."
                    if gross
                    else ". The results table must quote net_bequest_percentiles."
                )
            )
    return problems
