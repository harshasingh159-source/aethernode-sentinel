"""Draw the AetherNode radar icon (green dot + ring) as a multi-size .ico."""
from pathlib import Path

from PIL import Image, ImageDraw

GREEN = (52, 211, 153, 255)
BG = (11, 15, 20, 255)


def frame(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=size // 5, fill=BG)
    ring = max(2, size // 14)
    m = size * 0.16
    d.ellipse([m, m, size - m, size - m], outline=GREEN, width=ring)
    c = size * 0.36
    d.ellipse([c, c, size - c, size - c], fill=GREEN)
    return img


out = Path(__file__).with_name("aethernode.ico")
frame(256).save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", out)
