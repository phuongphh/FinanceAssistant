"""Shareable Twin image renderer (Phase 4.1, Story B.1).

Renders a privacy-conscious PNG of the user's Twin cone:

- NO absolute VND amounts anywhere (privacy contract)
- Shows growth % (P50 vs today) + horizon + watermark
- Gradient background + mascot bottom-right
- Optional "Founding Member" badge top-left

Performance target: < 1s/image. We use matplotlib (already a dep) to
draw the cone — y-axis tick labels are hidden so no money is leaked —
then composite the framing/branding via Pillow. Both libs are pure
Python + native and run in-process; no headless browser path.

This adapter intentionally exposes a single ``render_twin_share_image``
function returning PNG bytes. Services build the inputs; this module
owns only the pixels.
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

_ASSET_DIR = Path(__file__).resolve().parents[3] / "assets" / "mascot"
_MASCOT_DEFAULT = _ASSET_DIR / "happy.png"

# Final image dimensions tuned for Telegram preview (4:5 portrait reads
# well on phones without being clipped in chat).
WIDTH = 1080
HEIGHT = 1350

# Brand palette — kept inline so the renderer has no runtime config
# dependency. If we ever theme this, lift to content/twin_copy.yaml.
_BG_TOP = (255, 250, 242)        # warm cream
_BG_BOTTOM = (255, 224, 178)     # peach
_TEXT_DARK = (36, 59, 83)        # ink
_TEXT_MUTED = (98, 125, 152)     # slate
_ACCENT = (18, 103, 130)         # teal — matches cone P50
_BADGE_BG = (255, 243, 224)
_BADGE_BORDER = (255, 152, 0)


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    """Best-effort font loader. Falls back to PIL default so render
    never fails on a clean machine — the visual degrades, not the
    flow.
    """
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _gradient_background() -> Image.Image:
    """Vertical gradient from cream to peach. Cheap (one np-free
    Python loop over HEIGHT) but already <40ms at 1080x1350."""
    bg = Image.new("RGB", (WIDTH, HEIGHT), _BG_TOP)
    draw = ImageDraw.Draw(bg)
    for y in range(HEIGHT):
        t = y / max(HEIGHT - 1, 1)
        r = int(_BG_TOP[0] + (_BG_BOTTOM[0] - _BG_TOP[0]) * t)
        g = int(_BG_TOP[1] + (_BG_BOTTOM[1] - _BG_TOP[1]) * t)
        b = int(_BG_TOP[2] + (_BG_BOTTOM[2] - _BG_TOP[2]) * t)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))
    return bg


def _render_cone_png(cone: list[dict[str, Any]]) -> bytes:
    """Draw the cone with NO y-axis tick labels. This is the privacy
    guarantee at the rendering layer — even if a future caller forgets
    to strip amounts, the chart itself never paints them.
    """
    years = [int(p["year"]) for p in cone]
    p10 = [float(Decimal(str(p["p10"]))) for p in cone]
    p50 = [float(Decimal(str(p["p50"]))) for p in cone]
    p90 = [float(Decimal(str(p["p90"]))) for p in cone]

    fig, ax = plt.subplots(figsize=(9.0, 5.4), dpi=120)
    fig.patch.set_alpha(0.0)
    ax.set_facecolor((1, 1, 1, 0.0))

    ax.fill_between(years, p10, p90, color="#8ecae6", alpha=0.45)
    ax.plot(years, p50, color="#126782", linewidth=3.0)
    ax.scatter([years[0]], [p50[0]], color="#ffb703", s=70, zorder=5)

    ax.set_yticks([])
    ax.tick_params(axis="x", colors="#243b53", labelsize=12)
    ax.grid(True, axis="x", color="#d9e2ec", linewidth=0.8, alpha=0.6)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#bcccdc")

    buf = BytesIO()
    fig.tight_layout(pad=0.2)
    fig.savefig(buf, format="png", bbox_inches="tight", transparent=True)
    plt.close(fig)
    return buf.getvalue()


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    y: int,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text(((WIDTH - w) // 2, y), text, font=font, fill=fill)


def _draw_founding_badge(canvas: Image.Image, label: str) -> None:
    draw = ImageDraw.Draw(canvas)
    font = _font(28, bold=True)
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x, pad_y = 22, 12
    box = (40, 40, 40 + text_w + pad_x * 2, 40 + text_h + pad_y * 2)
    draw.rounded_rectangle(
        box, radius=18, fill=_BADGE_BG, outline=_BADGE_BORDER, width=3
    )
    draw.text((box[0] + pad_x, box[1] + pad_y - 2), label, font=font, fill=_TEXT_DARK)


def _paste_mascot(canvas: Image.Image, mascot_path: Path) -> None:
    """Place mascot bottom-right. Silently no-op if asset missing —
    branding is nice-to-have, the chart is the point.
    """
    if not mascot_path.exists():
        return
    try:
        mascot = Image.open(mascot_path).convert("RGBA")
    except OSError:
        return
    target_w = 200
    ratio = target_w / mascot.width
    target_h = int(mascot.height * ratio)
    mascot = mascot.resize((target_w, target_h), Image.LANCZOS)
    canvas.paste(mascot, (WIDTH - target_w - 50, HEIGHT - target_h - 50), mascot)


def render_twin_share_image(
    *,
    cone: list[dict[str, Any]],
    growth_pct_text: str,
    horizon_text: str,
    headline: str,
    subline: str,
    watermark: str,
    founding_badge_label: str | None = None,
    mascot_path: Path | None = None,
) -> bytes:
    """Render the shareable Twin image as PNG bytes.

    All copy is passed in by the caller (content/twin_copy.yaml) so
    this adapter stays localization-free.
    """
    if not cone:
        raise ValueError("cone must not be empty")

    canvas = _gradient_background()
    draw = ImageDraw.Draw(canvas)

    _draw_centered_text(draw, headline, y=140, font=_font(56, bold=True), fill=_TEXT_DARK)
    _draw_centered_text(draw, subline, y=220, font=_font(30), fill=_TEXT_MUTED)

    cone_png = Image.open(BytesIO(_render_cone_png(cone))).convert("RGBA")
    cone_w = WIDTH - 120
    ratio = cone_w / cone_png.width
    cone_h = int(cone_png.height * ratio)
    cone_png = cone_png.resize((cone_w, cone_h), Image.LANCZOS)
    canvas.paste(cone_png, (60, 290), cone_png)

    stats_y = 290 + cone_h + 30
    _draw_centered_text(
        draw, growth_pct_text, y=stats_y, font=_font(72, bold=True), fill=_ACCENT
    )
    _draw_centered_text(
        draw, horizon_text, y=stats_y + 100, font=_font(32), fill=_TEXT_MUTED
    )

    _draw_centered_text(
        draw, watermark, y=HEIGHT - 70, font=_font(24), fill=_TEXT_MUTED
    )

    if founding_badge_label:
        _draw_founding_badge(canvas, founding_badge_label)

    _paste_mascot(canvas, mascot_path or _MASCOT_DEFAULT)

    out = BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return out.getvalue()


__all__ = ["render_twin_share_image", "WIDTH", "HEIGHT"]
