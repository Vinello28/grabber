"""
Generates high-resolution application icons for Grabber (.png, .ico, .icns).
"""

import os
from pathlib import Path
from PIL import Image, ImageDraw


def generate_icons():
    assets_dir = Path(__file__).resolve().parent.parent / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    size = (512, 512)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Background rounded circle / badge with vibrant gradient fill
    # Modern dark tech theme: Indigo / Deep Blue with Cyan & Gold accents
    margin = 20
    bbox = [margin, margin, size[0] - margin, size[1] - margin]
    draw.rounded_rectangle(bbox, radius=110, fill=(26, 32, 44, 255), outline=(99, 102, 241, 255), width=12)

    # Inner decorative glow
    inner_bbox = [margin + 16, margin + 16, size[0] - margin - 16, size[1] - margin - 16]
    draw.rounded_rectangle(inner_bbox, radius=94, fill=(15, 23, 42, 255), outline=(56, 189, 248, 120), width=4)

    # 2. Draw Lightning Bolt / Energy Grabber symbol
    # Coordinates centered
    points = [
        (280, 80),   # top peak
        (170, 260),  # left middle inset
        (250, 260),  # middle right notch
        (220, 430),  # bottom sharp point
        (350, 230),  # right middle out
        (270, 230),  # right middle in
    ]
    draw.polygon(points, fill=(245, 158, 11, 255))  # Amber/Gold

    # Lightning highlight
    sub_points = [
        (280, 80),
        (220, 260),
        (280, 260),
        (230, 410),
        (330, 240),
        (270, 240),
    ]
    draw.polygon(sub_points, fill=(251, 191, 36, 255))

    # Save PNG
    png_path = assets_dir / "icon.png"
    img.save(png_path, format="PNG")
    print(f"Generated {png_path}")

    # Save Windows ICO (16, 32, 48, 64, 128, 256)
    ico_path = assets_dir / "icon.ico"
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=ico_sizes)
    print(f"Generated {ico_path}")

    # Save macOS ICNS (or fallback png)
    icns_path = assets_dir / "icon.icns"
    try:
        img.save(icns_path, format="ICNS")
        print(f"Generated {icns_path}")
    except Exception:
        # Pillow might not support direct ICNS on all platforms without sips
        # On macOS, sips or iconutil can convert png to icns
        print("Creating ICNS via macOS sips/iconutil if available...")
        _generate_mac_icns(png_path, icns_path)


def _generate_mac_icns(png_path: Path, icns_path: Path):
    import subprocess
    iconset_dir = png_path.parent / "icon.iconset"
    iconset_dir.mkdir(exist_ok=True)
    try:
        sizes = [16, 32, 64, 128, 256, 512]
        for s in sizes:
            subprocess.run(["sips", "-z", str(s), str(s), str(png_path), "--out", str(iconset_dir / f"icon_{s}x{s}.png")], check=True, capture_output=True)
            if s <= 256:
                subprocess.run(["sips", "-z", str(s*2), str(s*2), str(png_path), "--out", str(iconset_dir / f"icon_{s}x{s}@2x.png")], check=True, capture_output=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)], check=True, capture_output=True)
        print(f"Generated {icns_path} via iconutil")
    except Exception as e:
        print(f"ICNS creation note: {e}")
    finally:
        # cleanup temp iconset
        import shutil
        if iconset_dir.exists():
            shutil.rmtree(iconset_dir, ignore_errors=True)


if __name__ == "__main__":
    generate_icons()
