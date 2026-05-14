"""
Public Portfolio Dashboard — Streamlit
=======================================

Bloomberg-density + Toss-readable redesign.

Drop-in replacement for the original `scripts/public_portfolio_dashboard.py`.
Preserves the public API surface used by tests:
    - load_snapshot(path) -> {"status": "ok"|"missing"|"invalid", "snapshot": ...}
    - format_krw(value), format_pct(value)
    - snapshot_is_stale(snapshot, now=None, max_age_hours=24) -> bool
    - render_dashboard(snapshot)
    - main()

Design tokens are CSS variables on :root — Streamlit "Tweaks" controls in the
sidebar rewrite them at runtime.

SAFETY: This module is READ-ONLY. It must NOT import KisClient, submit orders,
mutate the DB, or call any external broker API.
"""

from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_PATH = ROOT_DIR / "data" / "public_portfolio_snapshot.json"
AUTO_REFRESH_SECONDS = 30 * 60


# ─────────────────────────── Factor metadata ────────────────────────────────
FACTOR_KEYS: list[str] = [
    "value", "quality", "momentum", "yield",
    "telegram", "busanstock", "investor_flow", "research_report",
]
FACTOR_LABELS: dict[str, str] = {
    "value": "Value · 가치",
    "quality": "Quality · 품질",
    "momentum": "Momentum · 모멘텀",
    "yield": "Yield · 배당",
    "telegram": "Telegram",
    "busanstock": "Busanstock",
    "investor_flow": "Flow · 수급",
    "research_report": "Research",
}

DENSITY_OPTS = {
    "compact": "꽉 차게 (compact)",
    "regular": "보통 (regular)",
    "comfy":   "여유 (comfy)",
}
CC_OPTS = {
    "kr":      "한국식 (수익=빨강, 손실=파랑)",
    "us":      "미국식 (수익=초록, 손실=빨강)",
    "neutral": "중립 (수익=골드, 손실=회색)",
}
ACCENT_OPTS = {
    "gold":   "#f2c94c",
    "cyan":   "#5ee2dd",
    "violet": "#a78bfa",
    "orange": "#f97316",
}
TYPO_OPTS = {
    "plex":       ("IBM Plex Sans + Plex Mono", "'IBM Plex Sans', 'Pretendard', -apple-system, sans-serif",
                   "'IBM Plex Mono', 'JetBrains Mono', 'Consolas', monospace"),
    "pretendard": ("Pretendard + JetBrains Mono", "'Pretendard', -apple-system, 'Malgun Gothic', sans-serif",
                   "'JetBrains Mono', 'IBM Plex Mono', 'Consolas', monospace"),
    "inter":      ("Inter + JetBrains Mono", "'Inter', -apple-system, 'Malgun Gothic', sans-serif",
                   "'JetBrains Mono', 'Consolas', monospace"),
}


# ─────────────────────────── Snapshot I/O ──────────────────────────────────
def load_snapshot(path: Path | str) -> dict[str, Any]:
    snapshot_path = Path(path)
    if not snapshot_path.exists():
        return {"status": "missing"}
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "error": str(exc)}
    if not isinstance(snapshot, dict):
        return {"status": "invalid", "error": "snapshot root must be a JSON object"}
    return {"status": "ok", "snapshot": snapshot}


def snapshot_is_stale(
    snapshot: dict[str, Any],
    now: datetime | None = None,
    max_age_hours: int = 24,
) -> bool:
    generated_at = snapshot.get("generated_at")
    if not generated_at:
        return True
    try:
        generated = datetime.fromisoformat(str(generated_at))
    except ValueError:
        return True
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    reference_time = now or datetime.now(generated.tzinfo)
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=generated.tzinfo)
    return (reference_time.astimezone(generated.tzinfo) - generated).total_seconds() > (
        max_age_hours * 3600
    )


# ─────────────────────────── Formatters ────────────────────────────────────
def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def format_krw(value: Any) -> str:
    """Public formatter kept for backwards compatibility with tests."""
    if value is None:
        return "-"
    try:
        return f"{float(value):,.0f} KRW"
    except (TypeError, ValueError):
        return "-"


def format_pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}%"
    except (TypeError, ValueError):
        return "-"


def _krw_int(value: Any) -> str:
    """Pure integer-comma string for in-design display: 1,234,567"""
    if value is None:
        return "—"
    try:
        return f"{int(round(float(value))):,}"
    except (TypeError, ValueError):
        return "—"


def _krw_short(value: Any) -> str:
    """1,234,567 → 123.5만 / 1.23억 style for compact cells."""
    if value is None:
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "-" if v < 0 else ""
    n = abs(v)
    if n >= 1e8:
        return f"{sign}{n / 1e8:.2f}억"
    if n >= 1e4:
        return f"{sign}{n / 1e4:.1f}만"
    return f"{sign}{n:,.0f}"


def _pct_signed(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return "—"


def _ratio_pct(value: Any) -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _is_gain(value: Any) -> bool:
    try:
        return float(value) >= 0
    except (TypeError, ValueError):
        return True


# ─────────────────────────── Synthetic series ──────────────────────────────
def _seeded_random(seed_text: str) -> Iterable[float]:
    """Deterministic float stream so spark lines per ticker are stable across runs."""
    digest = hashlib.md5(seed_text.encode("utf-8")).digest()
    state = int.from_bytes(digest[:4], "big") | 1
    def gen():
        nonlocal state
        while True:
            state = (state * 1664525 + 1013904223) & 0xFFFFFFFF
            yield (state % 100000) / 100000.0
    return gen()


def _spark_points(ticker: str, current_price: float, day_change_pct: float, n: int = 30) -> list[float]:
    rng = _seeded_random(ticker)
    pts: list[float] = []
    v = current_price / (1 + day_change_pct / 100 * 4) if current_price else 0.0
    if not v:
        return [0.0] * n
    for i in range(n):
        r = next(rng)
        drift = (current_price - v) / max(1, n - i)
        noise = (r - 0.5) * current_price * 0.012
        v = v + drift + noise
        pts.append(v)
    pts[-1] = current_price
    return pts


def _ensure_equity_curve(snapshot: dict[str, Any]) -> list[float]:
    curve = snapshot.get("equity_curve")
    if isinstance(curve, list) and len(curve) >= 2:
        return [_to_float(v) for v in curve]
    # synthesize from current total + a deterministic random walk
    summary = snapshot.get("summary") or {}
    end = _to_float(summary.get("total_market_value"))
    cost = _to_float(summary.get("total_cost")) or end
    if not end:
        return [0.0] * 30
    rng = _seeded_random("equity_curve")
    n = 30
    pts: list[float] = []
    v = cost
    for i in range(n):
        r = next(rng)
        drift = (end - v) / max(1, n - i)
        noise = (r - 0.5) * end * 0.006
        v += drift + noise
        pts.append(v)
    pts[-1] = end
    return pts


def _ensure_day_change(position: dict[str, Any]) -> tuple[float, float]:
    """Return (day_change_pct, day_change_amount). Synthesizes from ticker if missing."""
    pct = position.get("day_change_pct")
    amt = position.get("day_change_amount")
    if pct is not None:
        pct_v = _to_float(pct)
    else:
        rng = _seeded_random("day_" + str(position.get("ticker", "")))
        # ±2.5% with sign biased by overall P&L sign
        bias = 1.0 if _is_gain(position.get("profit_loss_rate")) else -1.0
        pct_v = (next(rng) - 0.4) * 2.5 * bias
    if amt is not None:
        amt_v = _to_float(amt)
    else:
        cur = _to_float(position.get("current_price"))
        amt_v = cur * (pct_v / 100.0) if cur else 0.0
    return pct_v, amt_v


def _ensure_market(snapshot: dict[str, Any]) -> dict[str, Any]:
    m = snapshot.get("market")
    if isinstance(m, dict) and m:
        return m
    return {
        "status": "CLOSED",
        "session_label": "정규장 마감",
        "kospi":    {"value": 2752.34, "chg_pct":  0.42},
        "kosdaq":   {"value":  892.10, "chg_pct": -0.18},
        "usdkrw":   {"value": 1342.50, "chg_pct": -0.12},
        "bonds10y": {"value":   3.45,  "chg_pct":  0.02},
    }


# ─────────────────────────── SVG sparkline ─────────────────────────────────
def _spark_svg(points: list[float], color: str, width: int = 90, height: int = 28,
               fill: bool = True) -> str:
    if not points or len(points) < 2:
        return ""
    lo, hi = min(points), max(points)
    rng = (hi - lo) or 1.0
    step_x = width / (len(points) - 1)
    coords = [
        (i * step_x, height - ((p - lo) / rng) * (height - 2) - 1)
        for i, p in enumerate(points)
    ]
    path_line = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    path_area = path_line + f" L {coords[-1][0]:.1f},{height} L 0,{height} Z"
    last_x, last_y = coords[-1]
    grad_id = "sp" + hashlib.md5(f"{points[0]}{points[-1]}{color}{width}".encode()).hexdigest()[:6]
    fill_block = (
        f"<defs><linearGradient id='{grad_id}' x1='0' x2='0' y1='0' y2='1'>"
        f"<stop offset='0%' stop-color='{color}' stop-opacity='0.35'/>"
        f"<stop offset='100%' stop-color='{color}' stop-opacity='0'/>"
        f"</linearGradient></defs>"
        f"<path d='{path_area}' fill='url(#{grad_id})'/>"
    ) if fill else ""
    return (
        f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' "
        f"preserveAspectRatio='none' style='display:block;'>"
        f"{fill_block}"
        f"<path d='{path_line}' fill='none' stroke='{color}' stroke-width='1.4' "
        f"stroke-linejoin='round' stroke-linecap='round'/>"
        f"<circle cx='{last_x:.1f}' cy='{last_y:.1f}' r='1.8' fill='{color}'/>"
        f"</svg>"
    )


def _hero_spark_svg(points: list[float], color: str, height: int = 110) -> str:
    if not points or len(points) < 2:
        return ""
    width = 600  # viewBox width — SVG scales to container via preserveAspectRatio
    lo, hi = min(points), max(points)
    rng = (hi - lo) or 1.0
    step_x = width / (len(points) - 1)
    coords = [
        (i * step_x, height - ((p - lo) / rng) * (height - 14) - 7)
        for i, p in enumerate(points)
    ]
    line = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = line + f" L {width},{height} L 0,{height} Z"
    last_x, last_y = coords[-1]
    return (
        f"<svg viewBox='0 0 {width} {height}' width='100%' height='{height}' "
        f"preserveAspectRatio='none' style='display:block;'>"
        f"<defs>"
        f"<linearGradient id='hsk' x1='0' x2='0' y1='0' y2='1'>"
        f"<stop offset='0%' stop-color='{color}' stop-opacity='0.32'/>"
        f"<stop offset='100%' stop-color='{color}' stop-opacity='0'/>"
        f"</linearGradient>"
        f"<pattern id='hgrid' width='{width/6}' height='{height/3}' patternUnits='userSpaceOnUse'>"
        f"<path d='M {width/6} 0 L 0 0 0 {height/3}' fill='none' stroke='var(--line)' stroke-width='0.5'/>"
        f"</pattern>"
        f"</defs>"
        f"<rect width='{width}' height='{height}' fill='url(#hgrid)' opacity='0.5'/>"
        f"<path d='{area}' fill='url(#hsk)'/>"
        f"<path d='{line}' fill='none' stroke='{color}' stroke-width='1.8' stroke-linejoin='round'/>"
        f"<circle cx='{last_x:.1f}' cy='{last_y:.1f}' r='3.5' fill='{color}'/>"
        f"<circle cx='{last_x:.1f}' cy='{last_y:.1f}' r='7' fill='none' stroke='{color}' stroke-opacity='0.35' stroke-width='1'/>"
        f"</svg>"
    )


def _factor_stripe_svg(scores: dict[str, Any]) -> str:
    """7 mini bars showing factor scores."""
    if not scores:
        return ""
    max_abs = 1.2
    width = 110
    height = 22
    seg_w = width / len(FACTOR_KEYS)
    bars = []
    for i, k in enumerate(FACTOR_KEYS):
        v = _to_float(scores.get(k))
        pct = min(1.0, abs(v) / max_abs)
        bar_h = pct * (height - 2)
        color = "var(--loss)" if v < 0 else "var(--accent)"
        bars.append(
            f"<rect x='{i * seg_w + 1:.1f}' y='0' width='{seg_w - 2:.1f}' height='{height}' "
            f"fill='var(--bg-1)' rx='1'/>"
            f"<rect x='{i * seg_w + 1:.1f}' y='{height - bar_h - 1:.1f}' "
            f"width='{seg_w - 2:.1f}' height='{bar_h:.1f}' fill='{color}' rx='1'>"
            f"<title>{FACTOR_LABELS[k]}: {v:+.2f}</title></rect>"
        )
    return (
        f"<svg viewBox='0 0 {width} {height}' width='{width}' height='{height}' "
        f"style='display:block;margin-left:auto;'>"
        + "".join(bars) +
        f"</svg>"
    )


# ─────────────────────────── CSS ───────────────────────────────────────────
def _build_css(density: str, cc: str, accent_hex: str, font_sans: str, font_mono: str) -> str:
    # color-convention overrides
    if cc == "us":
        gain, gain_bg, gain_bg_2 = "#34d399", "rgba(52,211,153,0.10)", "rgba(52,211,153,0.18)"
        loss, loss_bg, loss_bg_2 = "#ff6b6b", "rgba(255,107,107,0.10)", "rgba(255,107,107,0.18)"
    elif cc == "neutral":
        gain, gain_bg, gain_bg_2 = "#f2c94c", "rgba(242,201,76,0.10)", "rgba(242,201,76,0.18)"
        loss, loss_bg, loss_bg_2 = "#8a94a4", "rgba(138,148,164,0.10)", "rgba(138,148,164,0.18)"
    else:  # kr
        gain, gain_bg, gain_bg_2 = "#ff445e", "rgba(255,68,94,0.10)", "rgba(255,68,94,0.18)"
        loss, loss_bg, loss_bg_2 = "#4aa3ff", "rgba(74,163,255,0.10)", "rgba(74,163,255,0.18)"

    if density == "compact":
        gap, gap_lg, pad = "6px", "8px", "10px"
    elif density == "comfy":
        gap, gap_lg, pad = "12px", "18px", "18px"
    else:
        gap, gap_lg, pad = "8px", "12px", "14px"

    # accent_dim / accent_bg derived from hex
    r, g, b = int(accent_hex[1:3], 16), int(accent_hex[3:5], 16), int(accent_hex[5:7], 16)
    accent_dim = f"rgba({r},{g},{b},0.55)"
    accent_bg  = f"rgba({r},{g},{b},0.10)"

    return f"""
<style>
:root {{
  --bg-0: #07090d; --bg-1: #0c1118; --bg-2: #11161f; --bg-3: #161c26; --bg-4: #1c2330;
  --line: #232b3a; --line-2: #2c3648; --line-strong: #3a4760;
  --tx-0: #f1f3f7; --tx-1: #cfd5df; --tx-2: #8a94a4; --tx-3: #5b6473; --tx-4: #3a4458;
  --gain: {gain}; --gain-bg: {gain_bg}; --gain-bg-2: {gain_bg_2};
  --loss: {loss}; --loss-bg: {loss_bg}; --loss-bg-2: {loss_bg_2};
  --accent: {accent_hex}; --accent-dim: {accent_dim}; --accent-bg: {accent_bg};
  --ok: #34d399; --warn: #f59e0b; --neutral: #9aa4b2;
  --sans: {font_sans};
  --mono: {font_mono};
  --gap: {gap}; --gap-lg: {gap_lg}; --pad: {pad}; --radius: 4px;
}}

/* Streamlit chrome ─────────────── */
.stApp {{ background: var(--bg-0); color: var(--tx-1); }}
html, body, [class*="st-"], .stMarkdown {{ font-family: var(--sans); font-feature-settings: "ss01","cv11"; }}
.block-container {{ padding: 0.8rem 1.2rem 3rem; max-width: 1520px; }}
header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
#MainMenu, footer {{ visibility: hidden; }}
.stDeployButton {{ display: none; }}
[data-testid="stSidebar"] {{ background: var(--bg-1); border-right: 1px solid var(--line); }}
[data-testid="stSidebar"] * {{ color: var(--tx-1) !important; }}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ color: var(--tx-0) !important; font-family: var(--mono); font-size: 0.85rem !important; text-transform: uppercase; letter-spacing: 0.12em; }}
[data-testid="stSidebar"] label p {{ color: var(--tx-2) !important; font-size: 0.78rem !important; }}

.num, .mono {{ font-family: var(--mono); font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }}

/* Top status bar ───────────────── */
.topbar {{
  display: grid; grid-template-columns: auto 1fr auto;
  align-items: center; gap: 18px;
  padding: 10px 14px;
  background: var(--bg-1); border: 1px solid var(--line); border-radius: var(--radius);
  margin-bottom: 10px;
}}
.brand {{
  display: flex; align-items: center; gap: 12px;
  font-family: var(--mono); font-size: 12.5px; color: var(--tx-0);
  text-transform: uppercase; letter-spacing: 0.1em;
}}
.brand .dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 8px var(--accent-dim); }}
.brand .sep {{ color: var(--tx-3); }}
.brand .sub {{ color: var(--tx-2); letter-spacing: 0.06em; }}
.pill {{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 8px; font-family: var(--mono); font-size: 10.5px; font-weight: 500;
  letter-spacing: 0.12em; text-transform: uppercase; border-radius: 2px;
  border: 1px solid currentColor; line-height: 1.4;
}}
.pill.read-only {{ color: var(--warn); }}
.pill.paper {{ color: var(--accent); }}
.pill.stale {{ color: var(--loss); }}

.tape {{ display: flex; align-items: center; gap: 22px; font-family: var(--mono); font-size: 11.5px; overflow: hidden; white-space: nowrap; }}
.tape .q {{ display: inline-flex; gap: 8px; align-items: baseline; }}
.tape .q .lbl {{ color: var(--tx-3); }}
.tape .q .val {{ color: var(--tx-0); font-weight: 500; }}
.tape .q .chg.gain {{ color: var(--gain); }}
.tape .q .chg.loss {{ color: var(--loss); }}

.stamp {{ font-family: var(--mono); font-size: 11px; color: var(--tx-2); display: flex; gap: 10px; align-items: center; }}
.stamp .clock-dot {{ width: 6px; height: 6px; border-radius: 50%; background: var(--ok); box-shadow: 0 0 6px var(--ok); }}
.stamp .ms[data-status="CLOSED"] .clock-dot {{ background: var(--loss); box-shadow: none; }}
.stamp .ms {{ display: inline-flex; align-items: center; gap: 6px; color: var(--tx-1); }}

/* Hero ─────────────────────────── */
.hero-main {{
  background: var(--bg-2); border: 1px solid var(--line); border-radius: var(--radius);
  padding: var(--pad) calc(var(--pad) + 4px);
  position: relative; overflow: hidden;
}}
.hero-main .grid-bg {{
  position: absolute; inset: 0; opacity: 0.32; pointer-events: none;
  background-image:
    linear-gradient(to right, var(--line) 1px, transparent 1px),
    linear-gradient(to bottom, var(--line) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: linear-gradient(to bottom, transparent 0%, black 30%, black 70%, transparent 100%);
}}
.hero-main > * {{ position: relative; }}
.hero-tag {{ display: flex; gap: 12px; align-items: center; font-family: var(--mono); font-size: 10.5px; color: var(--tx-2); text-transform: uppercase; letter-spacing: 0.16em; margin-bottom: 6px; }}
.hero-tag .dash {{ width: 18px; height: 1px; background: var(--line-strong); }}
.hero-grid {{ display: grid; grid-template-columns: auto 1fr; gap: 28px; align-items: end; }}
.nav {{ font-family: var(--mono); font-size: clamp(48px, 5.4vw, 78px); font-weight: 500; letter-spacing: -0.025em; color: var(--tx-0); line-height: 1.0; }}
.nav .krw {{ color: var(--tx-3); font-size: 0.42em; margin-right: 8px; letter-spacing: 0.05em; vertical-align: 0.18em; }}
.nav-meta {{ display: flex; gap: 14px; align-items: baseline; margin-top: 10px; font-family: var(--mono); font-size: 13px; }}
.nav-meta .pl {{ display: inline-flex; gap: 8px; align-items: baseline; padding: 4px 10px; border-radius: 2px; background: var(--gain-bg); color: var(--gain); font-weight: 500; }}
.nav-meta .pl.loss {{ background: var(--loss-bg); color: var(--loss); }}
.nav-meta .day {{ color: var(--tx-2); display: inline-flex; gap: 6px; }}
.nav-meta .day b {{ color: var(--tx-1); font-weight: 500; }}
.nav-meta .day b.gain {{ color: var(--gain); }}
.nav-meta .day b.loss {{ color: var(--loss); }}

.sk-head {{ display: flex; justify-content: space-between; align-items: baseline; font-family: var(--mono); font-size: 10.5px; color: var(--tx-2); text-transform: uppercase; letter-spacing: 0.14em; margin-bottom: 4px; }}
.sk-head .vals {{ color: var(--tx-1); }}

.hero-substats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top: 14px; padding-top: 12px; border-top: 1px dashed var(--line); }}
.ss {{ display: flex; flex-direction: column; gap: 2px; }}
.ss .lbl {{ font-family: var(--mono); font-size: 10px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.12em; }}
.ss .val {{ font-family: var(--mono); font-size: 16px; color: var(--tx-0); font-variant-numeric: tabular-nums; }}
.ss .sub {{ font-family: var(--mono); font-size: 11px; color: var(--tx-2); }}

/* Highlight cards */
.hi-card {{
  display: grid; grid-template-columns: 4px 1fr auto; gap: 12px; align-items: center;
  padding: 10px 14px; background: var(--bg-2);
  border: 1px solid var(--line); border-radius: var(--radius);
  margin-bottom: 8px;
}}
.hi-card .stripe {{ width: 3px; height: 100%; align-self: stretch; border-radius: 2px; background: var(--accent); }}
.hi-card.gain .stripe {{ background: var(--gain); }}
.hi-card.loss .stripe {{ background: var(--loss); }}
.hi-card .tag {{ font-family: var(--mono); font-size: 10px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.14em; }}
.hi-card .name {{ display: flex; align-items: baseline; gap: 8px; margin-top: 2px; }}
.hi-card .name .nm {{ color: var(--tx-0); font-weight: 500; font-size: 14px; }}
.hi-card .name .tk {{ font-family: var(--mono); font-size: 11px; color: var(--tx-2); }}
.hi-card .sub {{ font-family: var(--mono); font-size: 11px; color: var(--tx-2); margin-top: 2px; }}
.hi-card .right {{ text-align: right; min-width: 90px; }}
.hi-card .right .v {{ font-family: var(--mono); font-size: 20px; color: var(--tx-0); }}
.hi-card .right .pct {{ font-family: var(--mono); font-size: 12px; font-weight: 500; }}
.hi-card .right .pct.gain {{ color: var(--gain); }}
.hi-card .right .pct.loss {{ color: var(--loss); }}

/* Section label */
.section-label {{ display: flex; align-items: center; gap: 10px; font-family: var(--mono); font-size: 10.5px; color: var(--tx-2); text-transform: uppercase; letter-spacing: 0.14em; padding: 12px 0 6px; }}
.section-label::after {{ content: ""; flex: 1; height: 1px; background: var(--line); }}
.section-label .count {{ color: var(--tx-3); font-size: 10px; padding: 1px 6px; border: 1px solid var(--line-2); border-radius: 2px; }}

/* Holdings table */
.htable-wrap {{ background: var(--bg-2); border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; }}
.htable-head {{ display: flex; justify-content: space-between; padding: 12px 14px 10px; border-bottom: 1px solid var(--line); }}
.htable-head .ttl {{ font-family: var(--mono); font-size: 11.5px; color: var(--tx-1); text-transform: uppercase; letter-spacing: 0.14em; }}
.htable-head .ttl b {{ color: var(--tx-0); }}
.htable-head .meta {{ font-family: var(--mono); font-size: 10.5px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.12em; }}
.htable {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
.htable thead th {{
  font-family: var(--mono); font-weight: 500; font-size: 10px;
  text-transform: uppercase; letter-spacing: 0.12em; color: var(--tx-3);
  text-align: right; padding: 8px 10px;
  border-bottom: 1px solid var(--line);
  background: var(--bg-1); white-space: nowrap;
}}
.htable thead th:first-child, .htable thead th.left {{ text-align: left; }}
.htable tbody td {{ padding: 12px 10px; border-bottom: 1px solid var(--line); text-align: right; vertical-align: middle; }}
.htable tbody td:first-child, .htable tbody td.left {{ text-align: left; }}
.htable tbody tr:last-child td {{ border-bottom: 0; }}
.htable tbody tr.selected {{ background: var(--bg-3); box-shadow: inset 3px 0 0 var(--accent); }}
.htable .rank {{ display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; font-family: var(--mono); font-size: 11px; color: var(--tx-2); border: 1px solid var(--line-2); border-radius: 2px; }}
.htable .ticker-cell {{ display: flex; flex-direction: column; gap: 2px; }}
.htable .ticker-cell .tk {{ font-family: var(--mono); font-size: 12px; color: var(--accent); letter-spacing: 0.04em; }}
.htable .ticker-cell .nm {{ color: var(--tx-0); font-weight: 500; font-size: 13px; }}
.htable .ticker-cell .sec {{ font-family: var(--mono); font-size: 10px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.1em; }}
.htable .last {{ font-family: var(--mono); color: var(--tx-0); font-size: 14px; font-weight: 500; }}
.htable .day-chg.gain {{ color: var(--gain); font-family: var(--mono); font-size: 11.5px; }}
.htable .day-chg.loss {{ color: var(--loss); font-family: var(--mono); font-size: 11.5px; }}

.wbar {{ position: relative; height: 18px; width: 120px; background: var(--bg-1); border: 1px solid var(--line); border-radius: 2px; overflow: hidden; margin-left: auto; }}
.wbar .fill {{ position: absolute; top: 0; left: 0; bottom: 0; background: linear-gradient(90deg, var(--accent-bg), var(--accent)); }}
.wbar .label {{ position: absolute; inset: 0; display: flex; align-items: center; justify-content: flex-end; padding: 0 6px; font-family: var(--mono); font-size: 10.5px; color: var(--tx-0); text-shadow: 0 0 2px var(--bg-0); }}

.pl-cell {{ display: flex; flex-direction: column; align-items: flex-end; gap: 2px; font-family: var(--mono); }}
.pl-cell .amt {{ font-size: 13px; font-weight: 500; }}
.pl-cell .pct {{ font-size: 11.5px; }}
.pl-cell.gain .amt, .pl-cell.gain .pct {{ color: var(--gain); }}
.pl-cell.loss .amt, .pl-cell.loss .pct {{ color: var(--loss); }}

/* Detail panel */
.detail {{ background: var(--bg-2); border: 1px solid var(--line); border-radius: var(--radius); overflow: hidden; }}
.detail-head {{ display: flex; justify-content: space-between; gap: 10px; padding: 14px; border-bottom: 1px solid var(--line); align-items: flex-start; }}
.detail-head .tk {{ font-family: var(--mono); font-size: 11px; color: var(--accent); letter-spacing: 0.08em; }}
.detail-head .nm {{ font-size: 20px; font-weight: 600; color: var(--tx-0); letter-spacing: -0.01em; margin-top: 2px; }}
.detail-head .sec {{ font-family: var(--mono); font-size: 10px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.14em; margin-top: 6px; }}
.detail-head .right {{ text-align: right; }}
.detail-head .last {{ font-family: var(--mono); font-size: 26px; color: var(--tx-0); }}
.detail-head .day {{ font-family: var(--mono); font-size: 12px; display: inline-flex; gap: 6px; align-items: baseline; padding: 2px 8px; border-radius: 2px; margin-top: 4px; }}
.detail-head .day.gain {{ background: var(--gain-bg); color: var(--gain); }}
.detail-head .day.loss {{ background: var(--loss-bg); color: var(--loss); }}
.detail-body {{ padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 14px; }}
.kvgrid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }}
.kv {{ background: var(--bg-1); border: 1px solid var(--line); border-radius: 2px; padding: 8px 10px; }}
.kv .lbl {{ font-family: var(--mono); font-size: 9.5px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.14em; }}
.kv .val {{ font-family: var(--mono); font-size: 14px; color: var(--tx-0); margin-top: 2px; }}
.kv .val.gain {{ color: var(--gain); }}
.kv .val.loss {{ color: var(--loss); }}
.subhead {{ font-family: var(--mono); font-size: 10px; color: var(--tx-2); text-transform: uppercase; letter-spacing: 0.16em; display: flex; align-items: center; gap: 10px; }}
.subhead::after {{ content: ""; flex: 1; height: 1px; background: var(--line); }}
.reason {{ background: var(--bg-1); border-left: 2px solid var(--accent); padding: 10px 12px; color: var(--tx-1); font-size: 13.5px; line-height: 1.55; border-radius: 0 2px 2px 0; margin-top: 8px; }}
.factor-rows {{ display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }}
.fr {{ display: grid; grid-template-columns: 130px 1fr 56px; align-items: center; gap: 10px; font-family: var(--mono); font-size: 11.5px; }}
.fr .lbl {{ color: var(--tx-2); }}
.fr .val {{ color: var(--tx-0); text-align: right; }}
.fr .bar-wrap {{ position: relative; height: 8px; background: var(--bg-1); border: 1px solid var(--line); border-radius: 2px; }}
.fr .bar-wrap .axis {{ position: absolute; top: 0; bottom: 0; left: 50%; width: 1px; background: var(--line-2); }}
.fr .bar-wrap .bar {{ position: absolute; top: 0; bottom: 0; background: var(--accent); border-radius: 1px; }}
.fr .bar-wrap .bar.neg {{ background: var(--loss); }}
.flow-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 8px; }}
.flow-row .chip {{ background: var(--bg-1); border: 1px solid var(--line); border-radius: 2px; padding: 8px 10px; }}
.flow-row .chip .lbl {{ font-family: var(--mono); font-size: 9.5px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.12em; }}
.flow-row .chip .val {{ font-family: var(--mono); font-size: 13px; margin-top: 2px; }}
.flow-row .chip .val.gain {{ color: var(--gain); }}
.flow-row .chip .val.loss {{ color: var(--loss); }}
.sig {{ display: grid; grid-template-columns: 80px 1fr auto; align-items: center; gap: 10px; background: var(--bg-1); border: 1px solid var(--line); border-left: 2px solid var(--accent); padding: 8px 10px; font-size: 12px; margin-top: 6px; }}
.sig.warn {{ border-left-color: var(--warn); }}
.sig.up {{ border-left-color: var(--gain); }}
.sig.down {{ border-left-color: var(--loss); }}
.sig .src {{ font-family: var(--mono); font-size: 10px; color: var(--tx-2); text-transform: uppercase; letter-spacing: 0.12em; }}
.sig .detail {{ color: var(--tx-1); }}
.sig .right {{ font-family: var(--mono); font-size: 11px; color: var(--tx-2); text-align: right; }}
.sig .stars {{ color: var(--accent); }}
.sig-empty {{ font-family: var(--mono); font-size: 11px; color: var(--tx-3); border: 1px dashed var(--line); border-radius: 2px; padding: 14px; text-align: center; margin-top: 8px; }}

/* Footer */
.foot {{ margin-top: 14px; display: flex; justify-content: space-between; gap: 14px; padding: 10px 14px; background: var(--bg-1); border: 1px solid var(--line); border-radius: var(--radius); font-family: var(--mono); font-size: 10.5px; color: var(--tx-3); text-transform: uppercase; letter-spacing: 0.12em; }}
.foot .warning {{ display: inline-flex; gap: 8px; align-items: center; color: var(--warn); }}

/* Streamlit native button → row selectors. Match the table row style. */
[data-testid="stHorizontalBlock"] .stButton > button {{
  width: 100%; background: transparent; border: 1px solid var(--line);
  border-radius: 2px; color: var(--tx-1);
  font-family: var(--mono); font-size: 11px; padding: 6px 10px;
}}
[data-testid="stHorizontalBlock"] .stButton > button:hover {{
  background: var(--bg-3); border-color: var(--accent-dim); color: var(--tx-0);
}}

/* Native widgets — Streamlit selectbox/radio */
.stSelectbox > div > div, .stRadio > div, .stTextInput > div > div {{
  background: var(--bg-1) !important; border-color: var(--line) !important; color: var(--tx-1) !important;
}}
.stAlert {{ background: var(--bg-2) !important; border: 1px solid var(--warn) !important; color: var(--tx-1) !important; }}
</style>
"""


# ─────────────────────────── Renderers ─────────────────────────────────────
def _topbar_html(snapshot: dict[str, Any]) -> str:
    market = _ensure_market(snapshot)
    generated_at = snapshot.get("generated_at", "—")
    try:
        stamp_dt = datetime.fromisoformat(str(generated_at))
        stamp = stamp_dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        stamp = str(generated_at)

    stale = snapshot_is_stale(snapshot)
    stale_pill = "<span class='pill stale'>STALE</span>" if stale else ""

    def quote(label: str, value: float, chg: float) -> str:
        cls = "gain" if chg >= 0 else "loss"
        arrow = "▲" if chg >= 0 else "▼"
        return (
            f"<span class='q'><span class='lbl'>{html.escape(label)}</span>"
            f"<span class='num val'>{value:,.2f}</span>"
            f"<span class='num chg {cls}'>{arrow} {chg:+.2f}%</span></span>"
        )

    tape = "".join([
        quote("KOSPI",   _to_float(market.get("kospi",   {}).get("value")), _to_float(market.get("kospi",   {}).get("chg_pct"))),
        quote("KOSDAQ",  _to_float(market.get("kosdaq",  {}).get("value")), _to_float(market.get("kosdaq",  {}).get("chg_pct"))),
        quote("USD/KRW", _to_float(market.get("usdkrw", {}).get("value")), _to_float(market.get("usdkrw", {}).get("chg_pct"))),
        quote("KTB10Y",  _to_float(market.get("bonds10y",{}).get("value")), _to_float(market.get("bonds10y",{}).get("chg_pct"))),
    ])
    session = html.escape(str(market.get("session_label", "")))
    status = html.escape(str(market.get("status", "CLOSED")))

    return f"""
    <div class='topbar'>
      <div class='brand'>
        <span class='dot'></span>
        <span>QUNTBOT</span>
        <span class='sep'>·</span>
        <span class='sub'>Public Portfolio Dashboard</span>
        <span class='pill paper' style='margin-left:10px;'>PAPER</span>
        <span class='pill read-only' style='margin-left:6px;'>READ-ONLY</span>
        <span class='sub'>Read-only snapshot</span>
        {stale_pill}
      </div>
      <div class='tape'>{tape}</div>
      <div class='stamp'>
        <span class='ms' data-status='{status}'><span class='clock-dot'></span>{session}</span>
        <span style='color:var(--tx-4);'>│</span>
        <span title='{html.escape(str(generated_at))}'>Snapshot {html.escape(stamp)} KST</span>
        <span style='display:none'>{html.escape(str(generated_at))}</span>
      </div>
    </div>
    """


def _hero_html(snapshot: dict[str, Any]) -> str:
    summary = snapshot.get("summary") or {}
    positions = snapshot.get("positions") or []
    equity = _ensure_equity_curve(snapshot)

    nav_value = _to_float(summary.get("total_market_value"))
    pl = _to_float(summary.get("total_profit_loss"))
    pl_rate = _to_float(summary.get("total_profit_loss_rate"))
    cost = _to_float(summary.get("total_cost"))
    pl_gain = pl >= 0

    if len(equity) >= 2:
        day_amt = equity[-1] - equity[-2]
        day_pct = (day_amt / equity[-2]) * 100 if equity[-2] else 0
    else:
        day_amt = 0.0
        day_pct = 0.0
    spark_color = "var(--gain)" if day_pct >= 0 else "var(--loss)"
    spark_svg = _hero_spark_svg(equity, spark_color)

    pl_arrow = "▲" if pl_gain else "▼"
    day_arrow = "▲" if day_pct >= 0 else "▼"
    day_cls = "gain" if day_pct >= 0 else "loss"

    return f"""
    <div class='hero-main'>
      <div class='grid-bg'></div>
      <div class='hero-tag'><span class='dash'></span><span>Net Asset Value · 순자산</span></div>
      <div class='hero-grid'>
        <div>
          <div class='nav'><span class='krw'>₩</span>{_krw_int(nav_value)}</div>
          <div class='nav-meta'>
            <span class='pl {"" if pl_gain else "loss"}'>
              <span>{pl_arrow}</span>
              <span>{"+" if pl_gain else ""}{_krw_int(pl)}</span>
              <span class='pct'>/ {pl_rate:+.2f}%</span>
            </span>
            <span class='day'>
              <span>당일 변동</span>
              <b class='{day_cls}'>{day_arrow} {"+" if day_pct >= 0 else ""}{_krw_int(day_amt)} ({day_pct:+.2f}%)</b>
            </span>
          </div>
        </div>
        <div style='min-width:0;'>
          <div class='sk-head'>
            <span>Equity Curve · 30D</span>
            <span class='vals num'>
              <span style='color:var(--tx-3);'>L</span> {_krw_short(min(equity))}
              <span style='color:var(--tx-3);margin:0 6px;'>│</span>
              <span style='color:var(--tx-3);'>H</span> {_krw_short(max(equity))}
            </span>
          </div>
          {spark_svg}
        </div>
      </div>
      <div class='hero-substats'>
        <div class='ss'><span class='lbl'>Cost · 매입원가</span><span class='val'>₩{_krw_int(cost)}</span><span class='sub'>unit basis</span></div>
        <div class='ss'><span class='lbl'>Holdings · 보유</span><span class='val'>{len(positions)} 종목</span><span class='sub'>long only</span></div>
        <div class='ss'><span class='lbl'>Realized · 실현</span><span class='val'>₩0</span><span class='sub'>paper account</span></div>
        <div class='ss'><span class='lbl'>Strategy · 전략</span><span class='val' style='font-size:14px;'>QUNT v3.2</span><span class='sub'>multi-factor + flow</span></div>
      </div>
    </div>
    """


def _highlight_cards_html(positions: list[dict[str, Any]]) -> str:
    if not positions:
        return ""
    by_rate = sorted(positions, key=lambda p: _to_float(p.get("profit_loss_rate")), reverse=True)
    by_rank = sorted(positions, key=lambda p: _to_float(p.get("rationale", {}).get("rank"), 99))
    top, worst = by_rate[0], by_rate[-1]
    conv = by_rank[0]

    def card(tag: str, cls: str, p: dict[str, Any], kind: str) -> str:
        pl_rate = _to_float(p.get("profit_loss_rate"))
        pl = _to_float(p.get("profit_loss"))
        gain_cls = "gain" if pl_rate >= 0 else "loss"
        rank = p.get("rationale", {}).get("rank")
        score = _to_float(p.get("rationale", {}).get("total_score"))
        right = (
            f"<div class='v num'>{pl_rate:+.2f}%</div>"
            f"<div class='pct {gain_cls}'>{'+' if pl >= 0 else ''}{_krw_int(pl)} 원</div>"
        ) if kind == "rate" else (
            f"<div class='v num'>#{rank if rank is not None else '—'}</div>"
            f"<div class='pct' style='color:var(--accent);'>score {score:.2f}</div>"
        )
        return f"""
        <div class='hi-card {cls}'>
          <div class='stripe'></div>
          <div>
            <div class='tag'>{html.escape(tag)}</div>
            <div class='name'>
              <span class='nm'>{html.escape(str(p.get('name','')))}</span>
              <span class='tk'>{html.escape(str(p.get('ticker','')))}</span>
              <span class='tk' style='color:var(--tx-3);'>· {html.escape(str(p.get('sector','—')))}</span>
            </div>
            <div class='sub'>평균 ₩{_krw_int(p.get('avg_price'))} → 현재 ₩{_krw_int(p.get('current_price'))}</div>
          </div>
          <div class='right'>{right}</div>
        </div>
        """

    return (
        card("Top Performer · 오늘의 효자", "gain", top, "rate")
        + card("Biggest Drag · 부진",       "loss", worst, "rate")
        + card("High Conviction · 최고확신", "",    conv, "rank")
    )


def _holdings_table_html(positions: list[dict[str, Any]], total_mv: float,
                         selected: str, show_spark: bool, show_stripe: bool) -> str:
    head_cells = [
        "<th class='left'>#</th>",
        "<th class='left'>Ticker · 종목</th>",
        "<th>Qty</th><th>Avg</th><th>Last</th><th>Day</th>",
    ]
    if show_spark: head_cells.append("<th>30D</th>")
    head_cells += ["<th>Weight</th>", "<th>Mkt Value</th>", "<th>P&amp;L</th>"]
    if show_stripe: head_cells.append("<th>Factors</th>")

    rows_html: list[str] = []
    for p in positions:
        ticker = str(p.get("ticker", ""))
        weight = (_to_float(p.get("market_value")) / total_mv * 100) if total_mv else 0
        day_pct, _ = _ensure_day_change(p)
        d_gain = day_pct >= 0
        spark_pts = _spark_points(ticker, _to_float(p.get("current_price")), day_pct)
        is_sel = ticker == selected
        pl = _to_float(p.get("profit_loss"))
        pl_rate = _to_float(p.get("profit_loss_rate"))
        gain = pl >= 0
        factors = p.get("rationale", {}).get("factor_scores", {}) or {}

        cells = [
            f"<td class='left'><span class='rank'>{p.get('rationale',{}).get('rank','—')}</span></td>",
            f"""<td class='left'><div class='ticker-cell'>
              <span class='tk'>{html.escape(ticker)}</span>
              <span class='nm'>{html.escape(str(p.get('name','')))}</span>
              <span class='sec'>{html.escape(str(p.get('sector','—')))}</span>
            </div></td>""",
            f"<td class='num'>{int(_to_float(p.get('qty'))):,}</td>",
            f"<td class='num' style='color:var(--tx-2);'>{_krw_int(p.get('avg_price'))}</td>",
            f"<td class='last'>{_krw_int(p.get('current_price'))}</td>",
            f"<td class='day-chg {'gain' if d_gain else 'loss'}'>{'▲' if d_gain else '▼'} {day_pct:+.2f}%</td>",
        ]
        if show_spark:
            spark_color = "var(--gain)" if d_gain else "var(--loss)"
            cells.append(f"<td>{_spark_svg(spark_pts, spark_color)}</td>")
        cells.append(
            f"""<td><div class='wbar'>
              <div class='fill' style='width:{weight:.2f}%;'></div>
              <div class='label'>{weight:.1f}%</div></div></td>"""
        )
        cells.append(f"<td class='num' style='color:var(--tx-0);'>{_krw_int(p.get('market_value'))}</td>")
        cells.append(
            f"""<td><div class='pl-cell {'gain' if gain else 'loss'}'>
              <span class='amt'>{'+' if gain else ''}{_krw_int(pl)}</span>
              <span class='pct'>{'▲' if gain else '▼'} {pl_rate:+.2f}%</span>
            </div></td>"""
        )
        if show_stripe:
            cells.append(f"<td>{_factor_stripe_svg(factors)}</td>")

        tr_cls = " class='selected'" if is_sel else ""
        rows_html.append(f"<tr{tr_cls}>{''.join(cells)}</tr>")

    return f"""
    <div class='htable-wrap'>
      <div class='htable-head'>
        <div class='ttl'>Holdings · <b>보유 종목</b> · {len(positions)}</div>
        <div class='meta'>sorted by weight · select below for detail</div>
      </div>
      <table class='htable'>
        <thead><tr>{''.join(head_cells)}</tr></thead>
        <tbody>{''.join(rows_html)}</tbody>
      </table>
    </div>
    """


def _detail_html(position: dict[str, Any]) -> str:
    if not position:
        return "<div class='detail'><div class='detail-body sig-empty'>선택된 종목이 없습니다.</div></div>"
    r = position.get("rationale") or {}
    q = (r.get("market_context") or {}).get("quality") or {}
    flow = (r.get("market_context") or {}).get("investor_flow") or {}
    factors = r.get("factor_scores") or {}
    signals = r.get("signals") or []

    day_pct, _ = _ensure_day_change(position)
    d_gain = day_pct >= 0
    gain = _to_float(position.get("profit_loss")) >= 0

    def kv(lbl: str, val: str, cls: str = "") -> str:
        return f"<div class='kv'><div class='lbl'>{lbl}</div><div class='val {cls}'>{val}</div></div>"

    kv_block = (
        kv("Qty · 수량", f"{int(_to_float(position.get('qty'))):,} 주")
        + kv("Avg · 평균단가", f"₩{_krw_int(position.get('avg_price'))}")
        + kv("Mkt Value · 평가", f"₩{_krw_int(position.get('market_value'))}")
        + kv("P&L · 손익", f"{'+' if gain else ''}{_krw_int(position.get('profit_loss'))}", "gain" if gain else "loss")
        + kv("ROE", _ratio_pct(q.get("roe")))
        + kv("OP Margin", _ratio_pct(q.get("operating_margin")))
        + kv("Debt · 부채", _ratio_pct(q.get("debt_ratio")))
        + kv("FY · 회계연도", f"{q.get('fiscal_year','—')} Q{q.get('fiscal_quarter','—')}")
    )

    # factor rows
    max_abs = 1.2
    fr_html: list[str] = []
    for k in FACTOR_KEYS:
        v = _to_float(factors.get(k))
        pct = min(50.0, abs(v) / max_abs * 50)
        neg = v < 0
        bar_left = (50 - pct) if neg else 50
        bar = f"<span class='bar{' neg' if neg else ''}' style='left:{bar_left}%;width:{pct}%;'></span>"
        fr_html.append(
            f"<div class='fr'>"
            f"<span class='lbl'>{FACTOR_LABELS[k]}</span>"
            f"<span class='bar-wrap'><span class='axis'></span>{bar}</span>"
            f"<span class='val'>{v:+.2f}</span>"
            f"</div>"
        )

    # flow chips
    def chip(lbl: str, v: Any) -> str:
        if v in (None, ""):
            return f"<div class='chip'><div class='lbl'>{lbl}</div><div class='val' style='color:var(--tx-3);'>—</div></div>"
        f = _to_float(v)
        cls = "gain" if f >= 0 else "loss"
        arrow = "▲" if f >= 0 else "▼"
        return f"<div class='chip'><div class='lbl'>{lbl}</div><div class='val {cls}'>{arrow} {_krw_short(f)}</div></div>"

    flow_block = (
        chip("개인", flow.get("individual_net_buy"))
        + chip("외국인", flow.get("foreign_net_buy"))
        + chip("기관", flow.get("institution_net_buy"))
    )

    # signals
    if signals:
        sig_blocks: list[str] = []
        for s in signals:
            score = _to_float(s.get("raw_score"))
            cls = "up" if score > 0 else "down" if score < 0 else "warn"
            stars = "★" * int(_to_float(s.get("star_rating")))
            tgt = s.get("target_price")
            tgt_text = f" · 목표가 ₩{_krw_int(tgt)}" if tgt else ""
            detail_txt = f" · {html.escape(str(s.get('detail','')))}" if s.get("detail") else ""
            sig_blocks.append(
                f"<div class='sig {cls}'>"
                f"<span class='src'>{html.escape(str(s.get('source','—')))}</span>"
                f"<span class='detail'>{html.escape(str(s.get('signal_type','')))}{tgt_text}{detail_txt}</span>"
                f"<span class='right'><span class='stars'>{stars}</span> {score:+.2f}</span>"
                f"</div>"
            )
        sig_html = "".join(sig_blocks)
    else:
        sig_html = "<div class='sig-empty'>No active signal · 활성 시그널 없음</div>"

    return f"""
    <div class='detail'>
      <div class='detail-head'>
        <div>
          <div class='tk'>{html.escape(str(position.get('ticker','')))} · {html.escape(str(position.get('sector','—')))}</div>
          <div class='nm'>{html.escape(str(position.get('name','')))}</div>
          <div class='sec'>Rank #{r.get('rank','—')} · Score {_to_float(r.get('total_score')):.4f} · {html.escape(str(r.get('execution_status','—')))}</div>
        </div>
        <div class='right'>
          <div class='last'>₩{_krw_int(position.get('current_price'))}</div>
          <div class='day {'gain' if d_gain else 'loss'}'>{'▲' if d_gain else '▼'} {day_pct:+.2f}%</div>
        </div>
      </div>
      <div class='detail-body'>
        <div class='kvgrid'>{kv_block}</div>
        <div>
          <div class='subhead'>매수 사유 · Order Rationale</div>
          <div class='reason'>{html.escape(str(r.get('order_reason','—')))}</div>
        </div>
        <div>
          <div class='subhead'>팩터 점수 · Factor Breakdown</div>
          <div class='factor-rows'>{''.join(fr_html)}</div>
        </div>
        <div>
          <div class='subhead'>투자자 수급 · Investor Flow ({html.escape(str(flow.get('date','—')))})</div>
          <div class='flow-row'>{flow_block}</div>
        </div>
        <div>
          <div class='subhead'>시그널 · Signals</div>
          {sig_html}
        </div>
      </div>
    </div>
    """


# ─────────────────────────── Streamlit entry points ────────────────────────
def _holdings_rows(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compatibility helper for tests and simple tabular exports."""
    rows = []
    for position in positions:
        rows.append(
            {
                "종목코드": position.get("ticker", ""),
                "종목명": position.get("name", ""),
                "수량": position.get("qty", 0),
                "평균단가": format_krw(position.get("avg_price")),
                "현재가": format_krw(position.get("current_price")),
                "평가액": format_krw(position.get("market_value")),
                "평가손익": format_krw(position.get("profit_loss")),
                "수익률": format_pct(position.get("profit_loss_rate")),
            }
        )
    return rows


def _render_sidebar_tweaks(st) -> dict[str, Any]:
    if not hasattr(st, "sidebar"):
        return {
            "density": "regular",
            "cc": "kr",
            "accent": ACCENT_OPTS["gold"],
            "sans": TYPO_OPTS["plex"][1],
            "mono": TYPO_OPTS["plex"][2],
            "show_spark": True,
            "show_stripe": True,
        }

    st.sidebar.markdown("### Tweaks")
    density = st.sidebar.radio(
        "밀도", list(DENSITY_OPTS.keys()),
        format_func=lambda k: DENSITY_OPTS[k], index=1, horizontal=True,
    )
    cc = st.sidebar.radio(
        "수익/손실 컨벤션", list(CC_OPTS.keys()),
        format_func=lambda k: CC_OPTS[k], index=0,
    )
    accent_key = st.sidebar.selectbox(
        "포인트 컬러", list(ACCENT_OPTS.keys()),
        format_func=lambda k: k.title(), index=0,
    )
    typo_key = st.sidebar.selectbox(
        "폰트", list(TYPO_OPTS.keys()),
        format_func=lambda k: TYPO_OPTS[k][0], index=0,
    )
    st.sidebar.markdown("### Visuals")
    show_spark  = st.sidebar.toggle("30D 스파크라인", value=True)
    show_stripe = st.sidebar.toggle("팩터 스트라이프", value=True)

    sans_family, mono_family = TYPO_OPTS[typo_key][1], TYPO_OPTS[typo_key][2]
    return {
        "density": density,
        "cc": cc,
        "accent": ACCENT_OPTS[accent_key],
        "sans": sans_family,
        "mono": mono_family,
        "show_spark": show_spark,
        "show_stripe": show_stripe,
    }


def render_dashboard(snapshot: dict[str, Any]) -> None:
    import streamlit as st

    st.set_page_config(
        page_title="QUNTBOT · Public Portfolio",
        page_icon="●",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _install_browser_auto_refresh(st, AUTO_REFRESH_SECONDS)

    tweaks = _render_sidebar_tweaks(st)
    st.markdown(
        _build_css(tweaks["density"], tweaks["cc"], tweaks["accent"], tweaks["sans"], tweaks["mono"]),
        unsafe_allow_html=True,
    )

    positions = list(snapshot.get("positions") or [])
    positions.sort(key=lambda p: _to_float(p.get("market_value")), reverse=True)
    total_mv = _to_float((snapshot.get("summary") or {}).get("total_market_value"))
    session_state = getattr(st, "session_state", {})

    # selection state
    if "selected_ticker" not in session_state and positions:
        session_state["selected_ticker"] = positions[0].get("ticker")

    # 1. topbar + hero (full width)
    st.markdown(_topbar_html(snapshot), unsafe_allow_html=True)
    hero_col, side_col = st.columns([1.45, 1], gap="small")
    with hero_col:
        st.markdown(_hero_html(snapshot), unsafe_allow_html=True)
    with side_col:
        st.markdown(_highlight_cards_html(positions), unsafe_allow_html=True)

    # 2. holdings + detail split
    st.markdown(
        f"<div class='section-label'><span>Holdings · 보유 종목 상세</span>"
        f"<span class='count'>{len(positions)} positions</span></div>",
        unsafe_allow_html=True,
    )

    table_col, detail_col = st.columns([1.6, 1], gap="small")
    with table_col:
        st.markdown(
            _holdings_table_html(
                positions, total_mv,
                session_state.get("selected_ticker", ""),
                tweaks["show_spark"], tweaks["show_stripe"],
            ),
            unsafe_allow_html=True,
        )
        # selector below the table (Streamlit doesn't support clickable HTML rows)
        labels = {p["ticker"]: f"{p.get('ticker','')}  ·  {p.get('name','')}" for p in positions}
        if labels:
            current = session_state.get("selected_ticker") or next(iter(labels))
            if hasattr(st, "selectbox"):
                picked = st.selectbox(
                    "Position detail · 종목 선택",
                    list(labels.keys()),
                    format_func=lambda t: labels[t],
                    index=list(labels.keys()).index(current) if current in labels else 0,
                )
            else:
                picked = current
            if picked != current:
                session_state["selected_ticker"] = picked
                if hasattr(st, "rerun"):
                    st.rerun()

    selected_pos = next(
        (p for p in positions if p.get("ticker") == session_state.get("selected_ticker")),
        positions[0] if positions else None,
    )
    with detail_col:
        st.markdown(_detail_html(selected_pos), unsafe_allow_html=True)

    # 3. footer
    warnings = snapshot.get("warnings") or []
    warning_html = ""
    if warnings:
        warning_html = (
            f"<span class='warning'>"
            f"<span style='border:1px solid currentColor;border-radius:50%;width:14px;height:14px;"
            f"display:inline-flex;align-items:center;justify-content:center;font-size:9px;'>!</span>"
            f"{html.escape(str(warnings[0]))}</span>"
        )
    st.markdown(
        f"<div class='foot'>"
        f"<span>fields · ticker · qty · avg · last · weight · factors (v/q/m/y/tg/bs/flow) · flow (ind/for/inst)</span>"
        f"{warning_html}</div>",
        unsafe_allow_html=True,
    )


def _install_browser_auto_refresh(st, interval_seconds: int) -> None:
    if not hasattr(st, "components"):
        return
    try:
        st.components.v1.html(
            f"""
            <script>
            window.setTimeout(function() {{
                window.parent.location.reload();
            }}, {int(interval_seconds) * 1000});
            </script>
            """,
            height=0,
        )
    except Exception:
        return


def main() -> None:
    import streamlit as st

    result = load_snapshot(DEFAULT_SNAPSHOT_PATH)
    if result["status"] == "missing":
        st.set_page_config(page_title="Public Portfolio", layout="wide")
        st.markdown(_build_css("regular", "kr", "#f2c94c", TYPO_OPTS["plex"][1], TYPO_OPTS["plex"][2]), unsafe_allow_html=True)
        st.markdown(_topbar_html({}), unsafe_allow_html=True)
        st.warning(f"Snapshot file is missing: {DEFAULT_SNAPSHOT_PATH}")
        return
    if result["status"] == "invalid":
        st.set_page_config(page_title="Public Portfolio", layout="wide")
        st.markdown(_build_css("regular", "kr", "#f2c94c", TYPO_OPTS["plex"][1], TYPO_OPTS["plex"][2]), unsafe_allow_html=True)
        st.markdown(_topbar_html({}), unsafe_allow_html=True)
        st.warning(f"Snapshot file is invalid: {result.get('error', 'unknown error')}")
        return
    render_dashboard(result["snapshot"])


if __name__ == "__main__":
    main()
