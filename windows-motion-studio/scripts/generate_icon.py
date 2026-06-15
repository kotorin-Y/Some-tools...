from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Please install Pillow before generating icons: python -m pip install pillow") from exc


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def rounded_rectangle(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def create_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    scale = size / 256

    def s(value: int) -> int:
        return int(round(value * scale))

    rounded_rectangle(draw, (s(20), s(20), s(236), s(236)), s(52), "#0A66D8")
    rounded_rectangle(draw, (s(36), s(36), s(220), s(220)), s(40), "#1288FF")
    rounded_rectangle(draw, (s(58), s(66), s(198), s(102)), s(18), "#D9ECFF")
    rounded_rectangle(draw, (s(58), s(112), s(156), s(148)), s(18), "#FFFFFF")
    rounded_rectangle(draw, (s(58), s(158), s(198), s(194)), s(18), "#A8D5FF")

    knob_radius = s(18)
    draw.ellipse((s(154), s(64), s(154) + knob_radius * 2, s(64) + knob_radius * 2), fill="#003C8F")
    draw.ellipse((s(108), s(110), s(108) + knob_radius * 2, s(110) + knob_radius * 2), fill="#0066CC")
    draw.ellipse((s(132), s(156), s(132) + knob_radius * 2, s(156) + knob_radius * 2), fill="#004FB3")

    draw.arc((s(74), s(52), s(202), s(204)), start=300, end=44, fill="#EAF6FF", width=s(9))
    draw.polygon([(s(202), s(82)), (s(226), s(78)), (s(213), s(100))], fill="#EAF6FF")
    return img


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    base = create_icon(1024)
    png_path = ASSETS / "windows_motion_studio_icon.png"
    ico_path = ASSETS / "windows_motion_studio_icon.ico"
    base.save(png_path)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base.save(ico_path, format="ICO", sizes=sizes)
    print(png_path)
    print(ico_path)


if __name__ == "__main__":
    main()
