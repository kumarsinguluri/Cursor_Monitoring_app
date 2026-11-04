"""Small inline SVG charts. Values are numbers produced by this app."""

import math
from html import escape

from markupsafe import Markup

_WIDTH = 640
_HEIGHT = 160


def cpu_chart(values):
    return render_chart(values, "CPU history", color="#0c6b4d", y_max=100)


def memory_chart(values):
    return render_chart(values, "Memory history", color="#8a5a2c", y_max=100)


def network_chart(received, sent):
    return render_lines(
        [
            {"name": "Received", "values": received or [], "color": "#0c6b4d"},
            {"name": "Sent", "values": sent or [], "color": "#2c5f8a"},
        ],
        "Network throughput",
    )


def render_chart(values, label, color="#0c6b4d", y_max=None):
    return render_lines(
        [{"name": label, "values": values or [], "color": color}],
        label,
        y_max=y_max,
    )


def render_lines(lines, label, y_max=None):
    prepared = []
    peak = 0.0
    for line in lines:
        numbers = _numbers(line.get("values"))
        peak = max(peak, max(numbers) if numbers else 0.0)
        prepared.append(
            {
                "name": escape(str(line.get("name") or label)),
                "values": numbers,
                "color": _color(line.get("color")),
            }
        )
    scale = max(float(y_max or 0), peak, 1.0)
    title = escape(str(label))
    if not any(line["values"] for line in prepared):
        body = (
            f'<text x="16" y="{_HEIGHT / 2:.0f}" fill="#5e584e" font-size="14">'
            "No samples yet</text>"
        )
    else:
        body = _grid() + "".join(_draw(line, scale) for line in prepared)
    svg = (
        f'<svg class="chart" viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img">'
        f"<title>{title}</title>{body}</svg>"
    )
    return Markup(svg)


def _numbers(values):
    clean = []
    for value in values or []:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(number):
            continue
        clean.append(number)
    return clean


def _color(value):
    if isinstance(value, str) and len(value) == 7 and value[0] == "#":
        hex_part = value[1:]
        if all(ch in "0123456789abcdefABCDEF" for ch in hex_part):
            return value
    return "#0c6b4d"


def _grid():
    mid = 8 + (_HEIGHT - 16) * 0.5
    return (
        f'<line x1="2" y1="{_HEIGHT - 4}" x2="{_WIDTH - 2}" y2="{_HEIGHT - 4}" '
        'stroke="#d9d3c5" stroke-width="1"/>'
        f'<line x1="2" y1="{mid:.1f}" x2="{_WIDTH - 2}" y2="{mid:.1f}" '
        'stroke="#ece7dc" stroke-width="1"/>'
    )


def _coords(values, scale):
    count = len(values)
    coords = []
    for index, value in enumerate(values):
        if count == 1:
            x = _WIDTH / 2
        else:
            x = 2 + (_WIDTH - 4) * (index / (count - 1))
        clamped = min(max(value, 0.0), scale)
        y = 8 + (_HEIGHT - 16) * (1 - clamped / scale)
        coords.append((x, y))
    return coords


def _draw(line, scale):
    coords = _coords(line["values"], scale)
    if not coords:
        return ""
    color = line["color"]
    if len(coords) == 1:
        x, y = coords[0]
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}"/>'
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = ""
    if len(line) and line["name"]:
        start_x = coords[0][0]
        end_x = coords[-1][0]
        area_points = f"{points} {end_x:.1f},{_HEIGHT - 4} {start_x:.1f},{_HEIGHT - 4}"
        area = (
            f'<polygon points="{area_points}" fill="{color}" fill-opacity="0.12" '
            'stroke="none"/>'
        )
    return (
        area
        + f'<polyline fill="none" stroke="{color}" stroke-width="2" '
        f'points="{points}"/>'
    )
