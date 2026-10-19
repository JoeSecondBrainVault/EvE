"""Generates high-resolution Windows App Icon (.ico) and PNG assets for E.V.E.

Produces:
- assets/eve.ico (multi-resolution mipmap: 256x256, 128x128, 64x64, 48x48, 32x32, 24x24, 16x16)
- assets/eve.png (512x512 master RGBA)
- dashboard/public/eve-icon.png (512x512 for web app icon / favicon)
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
DASH_PUBLIC_DIR = PROJECT_ROOT / "dashboard" / "public"


def render_master_icon(size: int = 1024) -> Image.Image:
    """Renders a high-resolution 1024x1024 master icon using supersampling."""
    # RGBA transparent canvas
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    center = size / 2.0
    radius = size * 0.45

    # 1. Outer ambient radial glow layer
    glow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    for r in range(int(radius * 1.08), int(radius * 0.70), -4):
        alpha = int(45 * (1.0 - (r - radius * 0.70) / (radius * 0.38)))
        if alpha > 0:
            glow_draw.ellipse(
                (center - r, center - r, center + r, center + r),
                fill=(16, 185, 129, alpha),  # Emerald glow
            )
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=18))
    img = Image.alpha_composite(img, glow_layer)
    draw = ImageDraw.Draw(img)

    # 2. Base Squircle / Rounded Dark Slate Chassis
    pad = size * 0.08
    corner = size * 0.22
    # Shadow underneath
    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow)
    s_draw.rounded_rectangle(
        (pad + 6, pad + 14, size - pad + 6, size - pad + 14),
        radius=int(corner),
        fill=(0, 0, 0, 160),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=16))
    img = Image.alpha_composite(img, shadow)
    draw = ImageDraw.Draw(img)

    # Dark Slate-950 Body
    draw.rounded_rectangle(
        (pad, pad, size - pad, size - pad),
        radius=int(corner),
        fill=(3, 7, 18, 250),           # Slate-950
        outline=(16, 185, 129, 220),     # Emerald-500 border
        width=int(size * 0.015),
    )

    # 3. Inner Sci-Fi Concentric Ring / Orbital Track
    orbit_r = radius * 0.72
    draw.ellipse(
        (center - orbit_r, center - orbit_r, center + orbit_r, center + orbit_r),
        outline=(6, 182, 212, 140),  # Cyan-500 track
        width=int(size * 0.012),
    )

    # Orbital gap arcs
    draw.arc(
        (center - orbit_r * 1.12, center - orbit_r * 1.12, center + orbit_r * 1.12, center + orbit_r * 1.12),
        start=30,
        end=150,
        fill=(52, 211, 153, 200),  # Emerald-400
        width=int(size * 0.018),
    )
    draw.arc(
        (center - orbit_r * 1.12, center - orbit_r * 1.12, center + orbit_r * 1.12, center + orbit_r * 1.12),
        start=210,
        end=330,
        fill=(56, 189, 248, 200),  # Sky-400
        width=int(size * 0.018),
    )

    # 4. Stylized Futuristic Geometric Monogram "E"
    # Modern horizontal energy bars with vertical cyber backbone
    bar_x0 = center - size * 0.18
    bar_x1 = center + size * 0.18
    bar_mid_x1 = center + size * 0.11
    bar_w = size * 0.065
    spine_x1 = bar_x0 + bar_w

    top_y = center - size * 0.20
    mid_y = center
    bot_y = center + size * 0.20

    # Vertical Spine
    draw.rounded_rectangle(
        (bar_x0, top_y, spine_x1, bot_y),
        radius=int(bar_w * 0.4),
        fill=(16, 185, 129, 255),  # Emerald
    )

    # Top horizontal bar
    draw.rounded_rectangle(
        (bar_x0, top_y - bar_w / 2, bar_x1, top_y + bar_w / 2),
        radius=int(bar_w * 0.4),
        fill=(52, 211, 153, 255),
    )

    # Center horizontal bar (slightly shorter, cyber style)
    draw.rounded_rectangle(
        (bar_x0, mid_y - bar_w / 2, bar_mid_x1, mid_y + bar_w / 2),
        radius=int(bar_w * 0.4),
        fill=(6, 182, 212, 255),  # Cyan
    )

    # Bottom horizontal bar
    draw.rounded_rectangle(
        (bar_x0, bot_y - bar_w / 2, bar_x1, bot_y + bar_w / 2),
        radius=int(bar_w * 0.4),
        fill=(52, 211, 153, 255),
    )

    # Central glowing pulse beacon
    beacon_r = size * 0.038
    beacon_cx = center + size * 0.17
    beacon_cy = center
    draw.ellipse(
        (beacon_cx - beacon_r, beacon_cy - beacon_r, beacon_cx + beacon_r, beacon_cy + beacon_r),
        fill=(255, 255, 255, 255),
        outline=(6, 182, 212, 255),
        width=int(size * 0.01),
    )

    return img


def generate_all_icons() -> None:
    print("[1/3] Rendering 1024x1024 master icon with anti-aliasing...")
    master = render_master_icon(1024)

    # 512x512 Master PNG
    master_512 = master.resize((512, 512), Image.Resampling.LANCZOS)
    png_path = ASSETS_DIR / "eve.png"
    master_512.save(png_path, "PNG")
    print(f"      Saved {png_path} (512x512)")

    if DASH_PUBLIC_DIR.exists():
        dash_icon_path = DASH_PUBLIC_DIR / "eve-icon.png"
        master_512.save(dash_icon_path, "PNG")
        print(f"      Saved {dash_icon_path}")

    # Multi-resolution Windows .ico
    print("[2/3] Generating Windows multi-resolution .ico (256, 128, 64, 48, 32, 24, 16)...")
    ico_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    ico_path = ASSETS_DIR / "eve.ico"

    # Pillow saves .ico with mipmap sizes
    master.save(
        ico_path,
        format="ICO",
        sizes=ico_sizes,
    )
    print(f"      Saved {ico_path}")
    print("[3/3] Icon generation complete!")


if __name__ == "__main__":
    generate_all_icons()
