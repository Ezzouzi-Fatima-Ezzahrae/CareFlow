"""Deterministic chart generation for clinical timelines.

Returns PNG bytes that MCP hosts (Prompt Opinion, Claude Desktop, etc.) render
inline in the chat. No LLM. Pure matplotlib + the events table.
"""
from __future__ import annotations
import io
from collections import defaultdict
from datetime import datetime
from typing import Iterable

import matplotlib
matplotlib.use("Agg")  # non-interactive backend; required for server-side rendering
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


# Color palette — matches CareFlow's brand
SEVERITY_COLORS = {
    "info":     "#10B981",  # green
    "warn":     "#F59E0B",  # amber
    "critical": "#DC2626",  # red
}
TEAL = "#0F766E"
INK = "#0F172A"
MUTED = "#64748B"
BG_GRID = "#E2E8F0"


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _save_png(fig) -> bytes:
    """Save the figure as a small, well-compressed PNG so the base64 payload
    that flows through the LLM stays tight (every byte costs LLM context)."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=90, bbox_inches="tight",
                facecolor="white", edgecolor="none",
                pil_kwargs={"optimize": True, "compress_level": 9})
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _style_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(MUTED)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED)
    ax.yaxis.label.set_color(INK)
    ax.xaxis.label.set_color(INK)
    ax.title.set_color(INK)


# ---------------------------------------------------------------------------
# 1. Health dashboard — horizontal bar chart of every numeric metric
# ---------------------------------------------------------------------------

def render_health_dashboard(events: Iterable[dict]) -> bytes:
    """One image showing every numeric vital and lab, color-coded by severity.

    Bars are red for critical, amber for warn, green for normal. Each value is
    annotated with its number and unit.
    """
    # Take the LATEST value for each unique code.
    latest: dict[str, dict] = {}
    for e in events:
        if e.get("event_type") not in ("vital", "lab"):
            continue
        if e.get("value_num") is None or not e.get("code"):
            continue
        code = e["code"]
        when = e.get("recorded_at") or ""
        if code not in latest or (when and when > (latest[code].get("recorded_at") or "")):
            latest[code] = e

    if not latest:
        return _empty_chart("No numeric metrics to display")

    # Order: critical first, then warn, then info — most actionable up top.
    severity_order = {"critical": 0, "warn": 1, "info": 2}
    items = sorted(
        latest.values(),
        key=lambda e: (severity_order.get(e.get("severity", "info"), 99), e.get("code") or ""),
    )

    codes = [e["code"] for e in items]
    values = [e["value_num"] for e in items]
    colors = [SEVERITY_COLORS.get(e.get("severity", "info"), MUTED) for e in items]
    units = [e.get("unit") or "" for e in items]

    height = max(2.5, len(items) * 0.42 + 1.0)
    fig, ax = plt.subplots(figsize=(9, height), dpi=130)

    y_pos = list(range(len(codes)))
    bars = ax.barh(y_pos, values, color=colors, height=0.62, edgecolor="white", linewidth=1.2)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(codes, fontsize=10)
    ax.invert_yaxis()
    ax.set_title("Patient health dashboard — latest values, color-coded by severity",
                 fontsize=13, fontweight="bold", pad=12)
    ax.grid(True, alpha=0.4, axis="x", color=BG_GRID, linestyle="-", linewidth=0.6)
    ax.set_axisbelow(True)
    _style_axes(ax)

    # Value annotations
    vmax = max(values) if values else 1
    for i, (val, _bar) in enumerate(zip(values, bars)):
        ax.text(val + vmax * 0.015, i, f"{val} {units[i]}".strip(),
                va="center", ha="left", fontsize=9, color=INK)

    # Legend
    legend = [
        Patch(facecolor=SEVERITY_COLORS["info"],     label="Normal"),
        Patch(facecolor=SEVERITY_COLORS["warn"],     label="Warning"),
        Patch(facecolor=SEVERITY_COLORS["critical"], label="Critical"),
    ]
    ax.legend(handles=legend, loc="lower right", framealpha=0.95,
              edgecolor=BG_GRID, fontsize=9)

    return _save_png(fig)


# ---------------------------------------------------------------------------
# 2. Single-metric trend over time — line chart with severity-colored points
# ---------------------------------------------------------------------------

def render_metric_chart(events: Iterable[dict], code: str) -> bytes:
    """Line chart of one metric across all visits.
    Each point is colored by severity at that visit.
    """
    series = []
    for e in events:
        if e.get("code") != code or e.get("value_num") is None:
            continue
        d = _parse_iso(e.get("recorded_at"))
        series.append((d, e["value_num"], e.get("severity", "info"), e.get("unit") or ""))

    series.sort(key=lambda x: (x[0] is None, x[0] or datetime.min))
    if len(series) < 1:
        return _empty_chart(f"No data for {code}")

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=130)

    if len(series) == 1:
        # Single point — show as a big dot with the value.
        d, v, sev, unit = series[0]
        ax.scatter([d or datetime.now()], [v],
                   color=SEVERITY_COLORS.get(sev, TEAL), s=220, zorder=5,
                   edgecolor="white", linewidth=2)
        ax.text(d or datetime.now(), v, f"  {v} {unit}",
                va="center", fontsize=11, color=INK)
    else:
        # Connect points with the brand teal, color points by their own severity.
        xs = [p[0] for p in series]
        ys = [p[1] for p in series]
        ax.plot(xs, ys, "-", color=TEAL, linewidth=2.2, zorder=2, alpha=0.7)
        for d, v, sev, unit in series:
            ax.scatter([d], [v],
                       color=SEVERITY_COLORS.get(sev, TEAL),
                       s=140, zorder=5, edgecolor="white", linewidth=2)

    unit = series[-1][3] or ""
    ax.set_title(f"{code} over time", fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel(unit if unit else "value", fontsize=10)
    ax.grid(True, alpha=0.4, color=BG_GRID, linestyle="-", linewidth=0.6)
    ax.set_axisbelow(True)
    _style_axes(ax)

    # Auto-format dates if matplotlib can
    fig.autofmt_xdate(rotation=20)

    # Annotate first and last numeric values to make the change obvious
    if len(series) >= 2:
        first_v = series[0][1]
        last_v  = series[-1][1]
        delta = last_v - first_v
        arrow = "↑" if delta > 0 else "↓" if delta < 0 else "·"
        ax.text(0.02, 0.97, f"first: {first_v} {unit}", transform=ax.transAxes,
                fontsize=9, va="top", color=MUTED)
        ax.text(0.02, 0.91, f"latest: {last_v} {unit}  {arrow} {abs(round(delta, 2))}",
                transform=ax.transAxes, fontsize=9, va="top",
                color=SEVERITY_COLORS.get(series[-1][2], INK), fontweight="bold")

    # Legend
    legend = [
        Patch(facecolor=SEVERITY_COLORS["info"],     label="Normal"),
        Patch(facecolor=SEVERITY_COLORS["warn"],     label="Warning"),
        Patch(facecolor=SEVERITY_COLORS["critical"], label="Critical"),
    ]
    ax.legend(handles=legend, loc="lower right", framealpha=0.95,
              edgecolor=BG_GRID, fontsize=9)

    return _save_png(fig)


# ---------------------------------------------------------------------------
# 3. Multi-visit progress timeline — small multiples of every metric over time
# ---------------------------------------------------------------------------

# Priority for which metrics to show first when there are too many
METRIC_PRIORITY = [
    "HbA1c", "fasting_glucose", "glucose",
    "systolic_bp", "diastolic_bp",
    "ldl", "hdl", "total_cholesterol", "triglycerides",
    "creatinine", "egfr", "bun",
    "bnp", "troponin",
    "weight_kg", "bmi",
    "heart_rate", "spo2", "temperature_c",
    "potassium", "sodium", "hemoglobin",
]


def render_progress_timeline(events: Iterable[dict], max_panels: int = 8) -> bytes:
    """Multi-panel chart — every numeric metric plotted across all visits.
    One subplot per metric, sharing the time axis.
    Each point colored by severity (red=critical, amber=warn, green=normal).
    Useful when the doctor uploads 3+ records spanning months.
    """
    # Group events by code
    by_code: dict[str, list[tuple[datetime | None, float, str, str]]] = defaultdict(list)
    for e in events:
        if e.get("event_type") not in ("vital", "lab"):
            continue
        if e.get("value_num") is None or not e.get("code"):
            continue
        d = _parse_iso(e.get("recorded_at"))
        by_code[e["code"]].append(
            (d, e["value_num"], e.get("severity", "info"), e.get("unit") or "")
        )

    # Keep only metrics with at least 2 data points (otherwise a "trend" is meaningless)
    # but if NO metric has 2+ points, fall back to all metrics with 1 point each.
    multi = {c: v for c, v in by_code.items() if len(v) >= 2}
    if multi:
        usable = multi
    else:
        usable = by_code

    if not usable:
        return _empty_chart("No numeric metrics to plot a progress timeline")

    # Order: priority list first, then alphabetical
    def _rank(code: str) -> int:
        try:
            return METRIC_PRIORITY.index(code)
        except ValueError:
            return 9999
    codes = sorted(usable.keys(), key=lambda c: (_rank(c), c))[:max_panels]

    n = len(codes)
    cols = 2 if n > 1 else 1
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols,
                             figsize=(11, max(3, rows * 2.4)),
                             dpi=130, sharex=False)
    if n == 1:
        axes = [axes]
    else:
        axes = list(axes.flatten())

    for i, code in enumerate(codes):
        ax = axes[i]
        series = sorted(usable[code], key=lambda x: (x[0] is None, x[0] or datetime.min))
        xs = [p[0] for p in series]
        ys = [p[1] for p in series]
        sev = [p[2] for p in series]
        unit = series[-1][3] if series else ""

        # Connecting line in teal
        if len(series) >= 2:
            ax.plot(xs, ys, "-", color=TEAL, linewidth=2, alpha=0.65, zorder=2)
        # Points colored by severity
        for d, v, s, _u in series:
            ax.scatter([d], [v],
                       color=SEVERITY_COLORS.get(s, TEAL),
                       s=80, zorder=5,
                       edgecolor="white", linewidth=1.5)

        ax.set_title(code, fontsize=11, fontweight="bold", pad=4, loc="left")
        if unit:
            ax.set_ylabel(unit, fontsize=8, color=MUTED)
        ax.grid(True, alpha=0.35, color=BG_GRID, linestyle="-", linewidth=0.5)
        ax.set_axisbelow(True)
        _style_axes(ax)
        ax.tick_params(axis="x", labelsize=8, rotation=15)
        ax.tick_params(axis="y", labelsize=8)

        # Annotate first → last delta in the corner
        if len(series) >= 2:
            delta = ys[-1] - ys[0]
            arrow = "↑" if delta > 0 else "↓" if delta < 0 else "·"
            color = SEVERITY_COLORS.get(sev[-1], INK)
            ax.text(0.97, 0.95, f"{arrow} {abs(round(delta, 2))}",
                    transform=ax.transAxes, ha="right", va="top",
                    fontsize=9, fontweight="bold", color=color)

    # Hide unused axes
    for j in range(n, len(axes)):
        axes[j].axis("off")

    fig.suptitle("Patient progress timeline — every metric, every visit",
                 fontsize=14, fontweight="bold", color=INK, y=0.995)
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    # Add a global legend at the bottom
    legend = [
        Patch(facecolor=SEVERITY_COLORS["info"],     label="Normal"),
        Patch(facecolor=SEVERITY_COLORS["warn"],     label="Warning"),
        Patch(facecolor=SEVERITY_COLORS["critical"], label="Critical"),
    ]
    fig.legend(handles=legend, loc="lower center", ncol=3,
               bbox_to_anchor=(0.5, -0.02), fontsize=9, frameon=False)

    return _save_png(fig)


# ---------------------------------------------------------------------------
# 4. Severity distribution — pie/donut showing proportion of flagged events
# ---------------------------------------------------------------------------

def render_severity_distribution(events: Iterable[dict]) -> bytes:
    """Donut chart showing the proportion of normal / warning / critical events.

    Useful as a single-glance risk indicator for a patient.
    """
    counts: dict[str, int] = defaultdict(int)
    for e in events:
        sev = e.get("severity", "info")
        if sev in SEVERITY_COLORS:
            counts[sev] += 1

    if sum(counts.values()) == 0:
        return _empty_chart("No events to summarize")

    labels = []
    sizes = []
    colors = []
    for sev in ("critical", "warn", "info"):
        n = counts.get(sev, 0)
        if n == 0:
            continue
        label_map = {"info": "Normal", "warn": "Warning", "critical": "Critical"}
        labels.append(f"{label_map[sev]} ({n})")
        sizes.append(n)
        colors.append(SEVERITY_COLORS[sev])

    fig, ax = plt.subplots(figsize=(6, 5), dpi=130)
    wedges, _texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors,
        autopct="%1.0f%%", startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 2},
        textprops={"fontsize": 10, "color": INK},
    )
    for at in autotexts:
        at.set_color("white")
        at.set_fontweight("bold")

    ax.set_title("Event severity distribution",
                 fontsize=13, fontweight="bold", pad=14, color=INK)

    # Highlight the critical count in the center
    crit = counts.get("critical", 0)
    warn = counts.get("warn", 0)
    risk_label = "HIGH" if crit else ("MODERATE" if warn else "LOW")
    risk_color = SEVERITY_COLORS["critical"] if crit else (
        SEVERITY_COLORS["warn"] if warn else SEVERITY_COLORS["info"])
    ax.text(0, 0.05, risk_label, ha="center", va="center",
            fontsize=22, fontweight="bold", color=risk_color)
    ax.text(0, -0.18, "risk", ha="center", va="center",
            fontsize=10, color=MUTED)

    return _save_png(fig)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_chart(message: str) -> bytes:
    fig, ax = plt.subplots(figsize=(8, 2), dpi=130)
    ax.axis("off")
    ax.text(0.5, 0.5, message, ha="center", va="center",
            fontsize=12, color=MUTED, transform=ax.transAxes)
    return _save_png(fig)
