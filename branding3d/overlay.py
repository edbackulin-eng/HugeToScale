"""Add the channel name and the size line to the Blender renders, and make the check previews.

    python branding3d/overlay.py <render dir> <out dir>

For each banner_X.png (+ .json from scene.py): banner_X_final.png (2560x1440), the phone crop
(the 1546x423 safe area) and the desktop crop (2560x423). For each avatar_X.png: the final
800x800 file and a sheet with it as a circle at 800, 98 and 48 px.
Font: Anton (SIL OFL 1.1).
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = str(ROOT / "assets/fonts/Anton-Regular.ttf")
YELLOW, WHITE, INK = (255, 214, 10), (255, 255, 255), (14, 16, 32)
SAFE = (507, 508, 2053, 932)  # 1546 x 423 centred in 2560 x 1440

# where the name goes inside the safe area, and its colour
TEXT = {"banner_A": ("left", YELLOW), "banner_B": ("right", WHITE), "banner_C": ("left", YELLOW)}


def outlined(base, xy, s, size, fill, stroke, sw, anchor="la", shadow=True):
    f = ImageFont.truetype(FONT, size)
    if shadow:  # soft drop shadow for depth
        sh = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((xy[0] + sw * 0.6, xy[1] + sw * 0.9), s, font=f, fill=(0, 0, 0, 150),
                                stroke_width=sw, stroke_fill=(0, 0, 0, 150), anchor=anchor)
        base.alpha_composite(sh.filter(ImageFilter.GaussianBlur(sw * 0.8)))
    ImageDraw.Draw(base).text(xy, s, font=f, fill=fill, stroke_width=sw, stroke_fill=stroke, anchor=anchor)


def fit_block(lines, max_w, max_h):
    """Largest font size at which the stacked lines fit max_w x max_h."""
    size = 400
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    while size > 20:
        f = ImageFont.truetype(FONT, size)
        boxes = [d.textbbox((0, 0), ln, font=f, stroke_width=int(size * 0.07)) for ln in lines]
        w = max(b[2] - b[0] for b in boxes)
        h = sum(b[3] - b[1] for b in boxes) + int(size * 0.04) * (len(lines) - 1)
        if w <= max_w and h <= max_h:
            return size, boxes
        size -= 4
    return size, boxes


def banner(png, js, out):
    key = png.stem
    info = json.loads(js.read_text())
    img = Image.open(png).convert("RGBA")
    sx = img.width / 2560
    if sx != 1:
        img = img.resize((2560, 1440), Image.LANCZOS)
    side, colour = TEXT[key]
    top, base = info["giant_top"], info["giant_base"]
    # size line next to the giant
    if side == "left":
        lx = info["giant_left"][0] - 26
    else:
        lx = info["giant_right"][0] + 26
    d = ImageDraw.Draw(img)
    y0, y1 = top[1], base[1]
    for w, c in ((14, INK), (7, YELLOW)):
        d.line([lx, y0, lx, y1], fill=c, width=w)
        d.line([lx - 18, y0, lx + 18, y0], fill=c, width=w)
        d.line([lx - 18, y1, lx + 18, y1], fill=c, width=w)
    h = info["giant_height_m"]
    label = f"{round(h)} m" if h >= 200 else f"{h:g} m"
    lab_x = lx + 30 if side == "left" else lx + 30
    outlined(img, (lab_x, y0 + 4), label, 78, YELLOW, INK, 8, anchor="lt")
    # channel name, two lines, inside the safe area on the free side
    lines = ["HUGE", "TO SCALE"]
    if side == "left":
        area, ya, yb = (SAFE[0] + 20, info["giant_left"][0] - 70), SAFE[1] + 15, SAFE[3] - 15
    else:  # right of the size line, under its label
        area, ya, yb = (lx + 60, SAFE[2] - 20), y0 + 100, SAFE[3] - 10
    size, boxes = fit_block(lines, area[1] - area[0], yb - ya)
    sw = int(size * 0.07)
    total_h = sum(b[3] - b[1] for b in boxes) + int(size * 0.04)
    y = ya + (yb - ya - total_h) / 2
    for ln, b in zip(lines, boxes):
        cx = (area[0] + area[1]) / 2
        outlined(img, (cx, y - b[1]), ln, size, colour, INK, sw, anchor="ma")
        y += (b[3] - b[1]) + int(size * 0.04)
    final = img.convert("RGB")
    final.save(out / f"{key}_final.png", optimize=True)
    final.crop(SAFE).save(out / f"{key}_phone.png")
    final.crop((0, SAFE[1], 2560, SAFE[3])).save(out / f"{key}_desktop.png")
    return final


def avatar(png, out):
    key = png.stem
    img = Image.open(png).convert("RGB")
    if img.width != 800:
        img = img.resize((800, 800), Image.LANCZOS)
    img.save(out / f"{key}_final.png", optimize=True)
    sheet = Image.new("RGB", (800 + 98 + 48 + 80, 820), (245, 245, 245))
    x = 10
    for s in (800, 98, 48):
        a = img.resize((s, s), Image.LANCZOS)
        m = Image.new("L", (s * 4, s * 4), 0)
        ImageDraw.Draw(m).ellipse([0, 0, s * 4 - 1, s * 4 - 1], fill=255)
        sheet.paste(a, (x, 10), m.resize((s, s), Image.LANCZOS))
        x += s + 30
    sheet.save(out / f"{key}_circles.png")


if __name__ == "__main__":
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.glob("banner_?.png")):
        banner(p, p.with_suffix(".json"), out)
        print(out / f"{p.stem}_final.png")
    for p in sorted(src.glob("avatar_?.png")):
        avatar(p, out)
        print(out / f"{p.stem}_final.png")
