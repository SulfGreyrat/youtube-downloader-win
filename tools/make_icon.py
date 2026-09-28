"""Render assets/icon.ico (+ icon.png) with Pillow.

Red rounded square, white down-arrow landing on a tray line — "download".
Drawn at 1024px and downsampled per size for clean anti-aliasing.
Run: .buildenv/Scripts/python.exe tools/make_icon.py
"""

import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

RED_TOP = (255, 92, 92)
RED_BOTTOM = (214, 40, 48)
INK = (255, 255, 255)
S = 1024


def master() -> Image.Image:
    # vertical gradient clipped to a rounded square
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        c = tuple(int(RED_TOP[i] + (RED_BOTTOM[i] - RED_TOP[i]) * t) for i in range(3))
        gd.line([(0, y), (S, y)], fill=c + (255,))
    mask = Image.new("L", (S, S), 0)
    inset = int(S * 0.04)
    ImageDraw.Draw(mask).rounded_rectangle(
        [inset, inset, S - inset, S - inset], radius=int(S * 0.22), fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    cx = S / 2
    shaft_w, head_w = S * 0.15, S * 0.46
    top, head_y, tip = S * 0.20, S * 0.46, S * 0.68
    d.rounded_rectangle([cx - shaft_w / 2, top, cx + shaft_w / 2, head_y + S * 0.04],
                        radius=int(S * 0.035), fill=INK)
    d.polygon([(cx - head_w / 2, head_y), (cx + head_w / 2, head_y), (cx, tip)], fill=INK)
    # tray
    d.rounded_rectangle([S * 0.24, S * 0.74, S * 0.76, S * 0.74 + S * 0.075],
                        radius=int(S * 0.0375), fill=INK)
    return img


def main() -> None:
    os.makedirs(ASSETS, exist_ok=True)
    big = master()
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = [big.resize((s, s), Image.LANCZOS) for s in sizes]
    frames[-1].save(os.path.join(ASSETS, "icon.ico"), format="ICO",
                    sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    big.resize((512, 512), Image.LANCZOS).save(os.path.join(ASSETS, "icon.png"))
    print("written", os.path.join(ASSETS, "icon.ico"))


if __name__ == "__main__":
    main()
