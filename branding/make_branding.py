"""Channel art drawn as vector shapes with Pillow (no AI imagery, no third-party logos).

    python branding/make_branding.py            # all variants into branding/out/
    python branding/make_branding.py "Name"     # banners with another channel name

Avatar 800x800 (YouTube shows it as a circle), banner 2560x1440 with the text kept inside
the 1546x423 area that is visible on every device. Font: Anton (SIL OFL 1.1, assets/fonts).
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = str(ROOT / "assets/fonts/Anton-Regular.ttf")
OUT = ROOT / "branding/out"
SS = 3  # supersampling for smooth edges

YELLOW, ORANGE, CYAN, MAGENTA = (255, 214, 10), (255, 122, 0), (0, 209, 255), (255, 46, 136)
WHITE, INK = (255, 255, 255), (12, 14, 28)


def gradient(w, h, top, bottom, radial=False):
    img = Image.new("RGB", (w, h))
    px = img.load()
    cx, cy, rmax = w / 2, h / 2, math.hypot(w / 2, h / 2)
    for y in range(h):
        for x in range(0, w):
            t = math.hypot(x - cx, y - cy) / rmax if radial else y / (h - 1)
            px[x, y] = tuple(int(a + (b - a) * t) for a, b in zip(top, bottom))
    return img


def fast_gradient(w, h, top, bottom, radial=False):
    small = gradient(max(w // 16, 2), max(h // 16, 2), top, bottom, radial)
    return small.resize((w, h), Image.BICUBIC)


def person(d, x, base, height, fill, outline=None, ow=0):
    """Generic standing human silhouette, feet at (x, base)."""
    u = height / 10
    ow = int(min(ow, max(2, 0.18 * u)))
    head = 1.35 * u
    d.ellipse([x - head / 2, base - height, x + head / 2, base - height + head], fill=fill,
              outline=outline, width=ow)
    d.rounded_rectangle([x - 1.25 * u, base - height + 1.6 * u, x + 1.25 * u, base - 4.2 * u],
                        radius=0.9 * u, fill=fill, outline=outline, width=ow)
    for s in (-1, 1):
        d.rounded_rectangle([x + s * 0.15 * u - (0.95 * u if s < 0 else 0), base - 4.6 * u,
                             x + s * 0.15 * u + (0 if s < 0 else 0.95 * u), base],
                            radius=0.45 * u, fill=fill, outline=outline, width=ow)


def ruler(d, x0, y0, x1, y1, n, color, w, major=5):
    d.line([x0, y0, x0, y1], fill=color, width=w)
    for i in range(n + 1):
        y = y1 - (y1 - y0) * i / n
        L = (x1 - x0) * (1 if i % major == 0 else 0.55)
        d.line([x0, y, x0 + L, y], fill=color, width=w)


def text_c(d, xy, s, size, fill, stroke, sw, anchor="mm"):
    f = ImageFont.truetype(FONT, size)
    d.text(xy, s, font=f, fill=fill, stroke_width=sw, stroke_fill=stroke, anchor=anchor)


def finish(img, size, path):
    img = img.resize(size, Image.LANCZOS)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)
    return path


# ---------- avatars (no channel name on them, so any avatar fits any name) ----------

def avatar_a():
    """Huge yellow bar with ruler ticks towering over a tiny person — the scale idea in one shape."""
    W = 800 * SS
    img = fast_gradient(W, W, (40, 20, 120), (8, 10, 40), radial=True)
    d = ImageDraw.Draw(img)
    base = 0.80 * W
    d.rectangle([0, base, W, W], fill=(20, 22, 60))
    bx0, bx1 = 0.40 * W, 0.66 * W
    d.rectangle([bx0, 0.14 * W, bx1, base], fill=YELLOW, outline=INK, width=14 * SS)
    for i in range(1, 12):
        y = base - (base - 0.14 * W) * i / 12
        L = (0.09 if i % 3 == 0 else 0.05) * W
        d.line([bx0 + 8 * SS, y, bx0 + L, y], fill=INK, width=9 * SS)
    person(d, 0.27 * W, base, 0.17 * W, WHITE, INK, 5 * SS)
    d.line([0.16 * W, base, 0.84 * W, base], fill=CYAN, width=10 * SS)
    return finish(img, (800, 800), OUT / "avatar_A_bar.png")


def avatar_b():
    """A giant down-arrow landing next to a tiny person: 'dropped in'."""
    W = 800 * SS
    img = fast_gradient(W, W, (0, 150, 255), (90, 0, 160))
    d = ImageDraw.Draw(img)
    base = 0.78 * W
    d.rectangle([0, base, W, W], fill=INK)
    cx = 0.56 * W
    arrow = [(cx - 0.13 * W, 0.12 * W), (cx + 0.13 * W, 0.12 * W), (cx + 0.13 * W, 0.46 * W),
             (cx + 0.25 * W, 0.46 * W), (cx, base - 0.02 * W), (cx - 0.25 * W, 0.46 * W),
             (cx - 0.13 * W, 0.46 * W)]
    d.polygon(arrow, fill=YELLOW, outline=INK, width=16 * SS)
    person(d, 0.17 * W, base, 0.16 * W, WHITE, INK, 5 * SS)
    for k in range(3):  # impact lines
        y = base - 0.03 * W - k * 0.035 * W
        d.line([cx + 0.27 * W, y, cx + 0.33 * W, y - 0.02 * W], fill=WHITE, width=9 * SS)
        d.line([cx - 0.27 * W, y, cx - 0.31 * W, y - 0.02 * W], fill=WHITE, width=9 * SS)
    return finish(img, (800, 800), OUT / "avatar_B_arrow.png")


def avatar_c():
    """'1:1' in huge yellow over a magenta-orange burst with a ruler edge."""
    W = 800 * SS
    img = fast_gradient(W, W, (255, 46, 136), (255, 122, 0))
    d = ImageDraw.Draw(img)
    for i in range(24):  # sun-burst rays
        a0, a1 = i * 2 * math.pi / 24, (i + 0.5) * 2 * math.pi / 24
        c = W / 2
        d.polygon([(c, c), (c + W * math.cos(a0), c + W * math.sin(a0)),
                   (c + W * math.cos(a1), c + W * math.sin(a1))], fill=(255, 90, 100))
    ruler(d, 0.15 * W, 0.30 * W, 0.22 * W, 0.70 * W, 16, INK, 7 * SS)
    text_c(d, (0.53 * W, 0.50 * W), "1:1", int(0.46 * W), YELLOW, INK, 14 * SS)
    person(d, 0.83 * W, 0.76 * W, 0.14 * W, WHITE, INK, 5 * SS)
    return finish(img, (800, 800), OUT / "avatar_C_one_to_one.png")


# ---------- banners ----------

def skyline(d, W, base, color, seed=7, maxh=0.16):
    import random
    r = random.Random(seed)
    x = 0
    while x < W:
        w = r.uniform(0.012, 0.03) * W
        h = r.uniform(0.03, maxh) * W * 0.5625
        d.rectangle([x, base - h, x + w, base], fill=color)
        x += w + r.uniform(0, 0.004) * W


def banner(style, name, tagline):
    W, H = 2560 * SS, 1440 * SS
    cx, cy = W / 2, H / 2
    if style == "A":
        img = fast_gradient(W, H, (40, 20, 120), (8, 10, 40))
    elif style == "B":
        img = fast_gradient(W, H, (0, 150, 255), (90, 0, 160))
    else:
        img = fast_gradient(W, H, (255, 46, 136), (255, 122, 0))
    d = ImageDraw.Draw(img)
    base = cy + 0.16 * H
    sky = (20, 22, 60) if style != "C" else (120, 20, 60)
    skyline(d, W, base, sky, seed={"A": 3, "B": 5, "C": 9}[style])
    d.rectangle([0, base, W, H], fill=sky)
    # a giant scale object outside the text: a tall bar (A), arrow (B), ruler (C)
    if style == "A":
        d.rectangle([0.78 * W, cy - 0.30 * H, 0.84 * W, base], fill=YELLOW, outline=INK, width=10 * SS)
        for i in range(1, 10):
            y = base - (base - (cy - 0.30 * H)) * i / 10
            d.line([0.78 * W + 6 * SS, y, 0.795 * W + (0.01 * W if i % 2 == 0 else 0), y], fill=INK, width=6 * SS)
        person(d, 0.755 * W, base, 0.05 * H, WHITE, INK, 3 * SS)
    elif style == "B":
        ax = 0.80 * W
        d.polygon([(ax - 0.03 * W, cy - 0.30 * H), (ax + 0.03 * W, cy - 0.30 * H), (ax + 0.03 * W, cy),
                   (ax + 0.06 * W, cy), (ax, base), (ax - 0.06 * W, cy), (ax - 0.03 * W, cy)],
                  fill=YELLOW, outline=INK, width=10 * SS)
        person(d, 0.72 * W, base, 0.05 * H, WHITE, INK, 3 * SS)
    else:
        ruler(d, 0.20 * W, cy - 0.28 * H, 0.235 * W, base, 30, INK, 5 * SS)
        person(d, 0.80 * W, base, 0.05 * H, WHITE, INK, 3 * SS)
    # text in the safe area (1546 x 423 around the centre)
    title_size = int(0.13 * H)
    f = ImageFont.truetype(FONT, title_size)
    while d.textlength(name.upper(), font=f) > 1460 * SS:
        title_size -= 4 * SS
        f = ImageFont.truetype(FONT, title_size)
    text_c(d, (cx, cy - 0.035 * H), name.upper(), title_size, YELLOW if style != "C" else WHITE, INK, 14 * SS)
    text_c(d, (cx, cy + 0.085 * H), tagline.upper(), int(0.042 * H), WHITE, INK, 7 * SS)
    slug = name.lower().replace(" ", "_")
    return finish(img, (2560, 1440), OUT / f"banner_{style}_{slug}.png")


def safe_area_preview(path):
    """Copy of a banner with the visible-on-all-devices area outlined, for checking only."""
    img = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(img)
    W, H = img.size
    d.rectangle([(W - 1546) / 2, (H - 423) / 2, (W + 1546) / 2, (H + 423) / 2], outline=(0, 255, 0), width=4)
    p = path.with_name(path.stem + "_safearea.png")
    img.save(p)
    return p


if __name__ == "__main__":
    tag = "Real things. Real size. Real places."
    made = [avatar_a(), avatar_b(), avatar_c()]
    names = sys.argv[1:] or ["Dropped To Scale", "Huge To Scale", "Placed For Scale"]
    for style, name in zip("ABC", names * 3):
        p = banner(style, name, tag)
        made += [p, safe_area_preview(p)]
    for p in made:
        print(p.relative_to(ROOT))
