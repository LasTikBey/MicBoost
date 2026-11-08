"""packaging/micboost.ico üretir (geliştirici aracı, Pillow gerektirir: pip install pillow)."""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024


def build() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # Mavi çapraz gradyan; görev çubuğundaki simgeyle aynı palet.
    grad = Image.new("RGBA", (S, S))
    px = grad.load()
    c0, c1 = (37, 99, 235), (59, 130, 246)
    for y in range(S):
        for x in range(S):
            t = (x + y) / (2 * S)
            px[x, y] = (int(c0[0] + (c1[0] - c0[0]) * t), int(c0[1] + (c1[1] - c0[1]) * t),
                        int(c0[2] + (c1[2] - c0[2]) * t), 255)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((32, 32, S - 32, S - 32), radius=210, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    w = (255, 255, 255, 255)
    d.rounded_rectangle((392, 200, 632, 600), radius=120, fill=w)          # mikrofon kapsülü
    d.arc((280, 320, 744, 720), 180, 360, fill=w, width=56)                 # tutucu yay
    d.line((512, 720, 512, 830), fill=w, width=56)
    d.line((400, 830, 624, 830), fill=w, width=56)
    return img


if __name__ == "__main__":
    out = Path(__file__).with_name("micboost.ico")
    build().save(out, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("yazıldı:", out)
