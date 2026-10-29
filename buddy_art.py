"""Avatar artwork for Desktop Wellness Buddy.

The active app uses the local avatar helpers below. Personal photos and custom
avatar files are intentionally not included in the public repository.
"""
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = (254, 0, 254)  # see-through colour on Windows
S = 4  # supersampling
BW, BH = 210, 130  # bird picture size in pixels


def _grad(size, top, bottom):
    w, h = size
    g = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return g


def _fill_shape(img, mask, top, bottom):
    img.paste(_grad(img.size, top, bottom), (0, 0), mask)


def _wing(img, ang, front):
    """One wing, rotated about the shoulder. ang in degrees, 0 = flat back, 80 = up."""
    w, h = img.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    sx, sy = 92 * S, 62 * S  # shoulder
    length = (56 if front else 48) * S
    a = math.radians(ang)
    tipx = sx - math.cos(a) * length * 0.55
    tipy = sy - math.sin(a) * length
    # leaf shaped wing: shoulder -> leading edge -> tip -> trailing edge
    lead = (sx + 18 * S - math.sin(a) * 6 * S, sy - math.sin(a) * length * 0.55 - 8 * S)
    trail = (sx - 26 * S, sy - math.sin(a) * length * 0.45 + 12 * S)
    def curve(p0, c, p1, n=18):
        return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0],
                 (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1])
                for t in [i / n for i in range(n + 1)]]
    top_c = (lead[0] + (tipx - sx) * 0.15, lead[1] - 4 * S)
    bot_c = (trail[0] + (tipx - sx) * 0.1, trail[1] + 2 * S)
    pts = curve((sx, sy), top_c, (tipx, tipy)) + curve((tipx, tipy), bot_c, (sx, sy))
    d.polygon(pts, fill=255)
    m = m.filter(ImageFilter.GaussianBlur(S * 0.6))
    if front:
        top, bot = (120, 230, 205), (30, 140, 135)
    else:
        top, bot = (170, 240, 225), (80, 180, 175)
    layer.paste(_grad((w, h), top, bot), (0, 0), m)
    # feather lines
    ld = ImageDraw.Draw(layer)
    for k in (0.35, 0.55, 0.75):
        ex = sx + (tipx - sx) * k
        ey = sy + (tipy - sy) * k
        ld.line([(sx, sy), (ex, ey)], fill=(20, 95, 95, 140), width=S)
    img.alpha_composite(layer)


def _eye(d, style):
    """Eyes carry the mood. Box is roughly x 135..145, y 44..54 (before scaling)."""
    ink = (15, 15, 25, 255)
    x1, y1, x2, y2 = 134 * S, 43 * S, 146 * S, 55 * S
    if style == "blink":
        d.line([(x1, 49 * S), (x2, 49 * S)], fill=ink, width=2 * S)
    elif style == "happy":  # ^ ^
        d.arc([x1, 45 * S, x2, 57 * S], 200, 340, fill=ink, width=2 * S)
    elif style == "sleepy":  # half closed
        d.pieslice([x1, y1, x2, y2], 0, 180, fill=ink)
        d.line([(x1, 49 * S), (x2, 49 * S)], fill=ink, width=2 * S)
    elif style == "zen":  # peaceful curve
        d.arc([x1, 42 * S, x2, 54 * S], 20, 160, fill=ink, width=2 * S)
    elif style == "sparkle":  # star eyes
        cx, cy, r = 140 * S, 49 * S, 7 * S
        d.polygon([(cx, cy - r), (cx + r / 3, cy - r / 3), (cx + r, cy), (cx + r / 3, cy + r / 3),
                   (cx, cy + r), (cx - r / 3, cy + r / 3), (cx - r, cy), (cx - r / 3, cy - r / 3)],
                  fill=(255, 215, 40, 255), outline=ink)
    elif style == "sass":  # side glance and a raised brow
        d.ellipse([x1, y1 + S, x2, y2 - S], fill=(255, 255, 255, 255), outline=ink)
        d.ellipse([141 * S, 46 * S, 146 * S, 52 * S], fill=ink)
        d.line([(133 * S, 41 * S), (146 * S, 37 * S)], fill=ink, width=2 * S)
    else:  # open
        d.ellipse([135 * S, 44 * S, 145 * S, 54 * S], fill=ink)
        d.ellipse([138 * S, 45 * S, 142 * S, 49 * S], fill=(255, 255, 255, 255))


_CACHE = {}


def bird_rgba(angle=40, eye="open"):
    """Cached RGBA bird facing right, hard edged alpha, ready to resize or flip."""
    k = (angle, eye)
    if k not in _CACHE:
        _CACHE[k] = _draw_bird(angle, eye)
    return _CACHE[k]


def bird_frame(angle=40, facing=1, eye="open"):
    """RGB image of the bird on the see-through colour (used by the preview)."""
    im = bird_rgba(angle, eye)
    bg = Image.new("RGB", im.size, KEY)
    bg.paste(im.convert("RGB"), (0, 0), im.split()[3])
    return ImageOps.mirror(bg) if facing < 0 else bg


def _draw_bird(angle=40, eye="open"):
    w, h = BW * S, BH * S
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    # tail
    tm = Image.new("L", (w, h), 0)
    td = ImageDraw.Draw(tm)
    td.polygon([(70 * S, 66 * S), (14 * S, 100 * S), (10 * S, 112 * S), (30 * S, 108 * S),
                (22 * S, 120 * S), (48 * S, 104 * S), (84 * S, 82 * S)], fill=255)
    tl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    tl.paste(_grad((w, h), (22, 120, 95), (10, 60, 70)), (0, 0), tm)
    img.alpha_composite(tl)
    _wing(img, angle * 0.9, False)  # back wing
    # body
    bm = Image.new("L", (w, h), 0)
    bd = ImageDraw.Draw(bm)
    bd.ellipse([58 * S, 48 * S, 138 * S, 92 * S], fill=255)
    bl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bl.paste(_grad((w, h), (60, 210, 150), (15, 110, 100)), (0, 0), bm)
    # pale belly
    belly = Image.new("L", (w, h), 0)
    ImageDraw.Draw(belly).ellipse([72 * S, 70 * S, 132 * S, 96 * S], fill=255)
    belly = ImageChops.multiply(belly, bm).filter(ImageFilter.GaussianBlur(S * 3))
    bl.paste((250, 244, 225, 255), (0, 0), ImageChops.multiply(belly, bm))
    img.alpha_composite(bl)
    # head
    hm = Image.new("L", (w, h), 0)
    ImageDraw.Draw(hm).ellipse([116 * S, 34 * S, 154 * S, 72 * S], fill=255)
    hl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    hl.paste(_grad((w, h), (80, 225, 170), (20, 130, 110)), (0, 0), hm)
    img.alpha_composite(hl)
    # shimmering throat patch
    gm = Image.new("L", (w, h), 0)
    ImageDraw.Draw(gm).ellipse([128 * S, 56 * S, 152 * S, 76 * S], fill=255)
    gm = ImageChops.multiply(gm, hm)
    gl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gl.paste(_grad((w, h), (255, 70, 150), (190, 20, 110)), (0, 0), gm)
    img.alpha_composite(gl)
    d = ImageDraw.Draw(img)
    # beak, long and thin
    d.polygon([(152 * S, 50 * S), (206 * S, 44 * S), (152 * S, 56 * S)], fill=(40, 40, 45, 255))
    _eye(d, eye)
    # front wing on top
    _wing(img, angle, True)
    # outline pass for a clean cartoon edge
    a = img.split()[3]
    edge = ImageChops.subtract(a.filter(ImageFilter.MaxFilter(S * 2 + 1)), a)
    out = Image.new("RGBA", (w, h), (10, 55, 60, 255))
    out.putalpha(edge)
    base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    base.alpha_composite(out)
    base.alpha_composite(img)
    small = base.resize((BW, BH), Image.LANCZOS)
    alpha = small.split()[3].point(lambda v: 255 if v > 110 else 0)  # hard edge, no pink fringe
    small.putalpha(alpha)
    return small


def _font(size):
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _cartoon(photo_path, size=256):
    im = Image.open(photo_path)
    im = ImageOps.exif_transpose(im).convert("RGB")
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = max(0, int((h - side) * 0.25))  # faces sit in the upper part of most photos
    im = im.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    smooth = im
    for _ in range(3):
        smooth = smooth.filter(ImageFilter.MedianFilter(5))
    smooth = ImageEnhance.Color(smooth).enhance(1.45)
    smooth = ImageEnhance.Contrast(smooth).enhance(1.15)
    smooth = ImageOps.posterize(smooth, 4)
    gray = ImageOps.autocontrast(im.convert("L").filter(ImageFilter.GaussianBlur(1.2)))
    edges = gray.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 22 else 0)
    ink = ImageOps.invert(edges.filter(ImageFilter.MinFilter(3)))  # thin dark lines
    toon = ImageChops.multiply(smooth, Image.merge("RGB", (ink, ink, ink)))
    return toon


def _doodle(size=256):
    """Drawn cartoon portrait: shoulder length dark hair, warm skin, big eyes, pink top, grey jacket."""
    k = 3
    n = size * k
    img = _grad((n, n), (255, 226, 190), (255, 170, 205)).convert("RGBA")
    d = ImageDraw.Draw(img)

    def P(x, y):
        return (x * n / 256, y * n / 256)

    def box(x1, y1, x2, y2):
        return [P(x1, y1), P(x2, y2)]

    ink = (45, 25, 35, 255)
    skin, skin_sh = (176, 116, 84, 255), (150, 94, 68, 255)
    hair, hair_hi = (28, 22, 34, 255), (70, 55, 80, 255)
    # back hair
    d.rounded_rectangle(box(48, 40, 208, 236), radius=int(60 * k), fill=hair)
    # jacket shoulders, pink top, neck
    d.ellipse(box(-10, 196, 266, 330), fill=(150, 175, 185, 255), outline=ink, width=2 * k)
    d.polygon([P(98, 206), P(158, 206), P(128, 262)], fill=(255, 40, 135, 255), outline=ink)
    d.rounded_rectangle(box(108, 168, 148, 212), radius=int(10 * k), fill=skin_sh)
    # face
    d.ellipse(box(66, 62, 190, 196), fill=skin, outline=ink, width=2 * k)
    # hair top and side part
    d.pieslice(box(58, 36, 198, 150), 180, 360, fill=hair)
    d.polygon([P(66, 100), P(60, 150), P(84, 120), P(100, 78), P(128, 60)], fill=hair)
    d.polygon([P(190, 100), P(196, 150), P(172, 120), P(150, 74), P(128, 60)], fill=hair)
    d.arc(box(76, 44, 176, 110), 200, 280, fill=hair_hi, width=3 * k)
    # eyes: big, shiny
    for cx in (101, 155):
        d.ellipse(box(cx - 15, 112, cx + 15, 146), fill=(255, 255, 255, 255), outline=ink, width=2 * k)
        d.ellipse(box(cx - 10, 116, cx + 10, 144), fill=(70, 38, 28, 255))
        d.ellipse(box(cx - 5, 122, cx + 5, 138), fill=(15, 10, 14, 255))
        d.ellipse(box(cx - 8, 119, cx - 1, 127), fill=(255, 255, 255, 255))
        d.ellipse(box(cx + 3, 134, cx + 7, 139), fill=(255, 255, 255, 255))
        d.arc(box(cx - 17, 106, cx + 17, 140), 195, 345, fill=ink, width=3 * k)  # lash line
    d.arc(box(84, 96, 118, 112), 200, 340, fill=ink, width=3 * k)  # brows
    d.arc(box(138, 96, 172, 112), 200, 340, fill=ink, width=3 * k)
    # nose, blush, smile with teeth
    d.arc(box(120, 142, 136, 160), 20, 160, fill=skin_sh, width=2 * k)
    for cx in (88, 168):
        d.ellipse(box(cx - 12, 152, cx + 12, 166), fill=(240, 110, 120, 110))
    d.pieslice(box(100, 160, 156, 192), 0, 180, fill=(255, 255, 255, 255), outline=ink, width=2 * k)
    d.arc(box(100, 158, 156, 186), 15, 165, fill=(150, 40, 70, 255), width=2 * k)
    return img.resize((size, size), Image.LANCZOS).convert("RGB")


def make_avatar(size=256):
    """Load the clean full-body avatar. Returns transparent RGBA."""
    own = os.path.join(HERE, "avatar.png")
    photo = None
    for n in ("me.jpg", "me.jpeg", "me.png"):
        p = os.path.join(HERE, n)
        if os.path.exists(p):
            photo = p
            break
    if os.path.exists(own):
        face = Image.open(own).convert("RGBA")
        face.thumbnail((size, size), Image.LANCZOS)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.alpha_composite(face, ((size - face.width) // 2, (size - face.height) // 2))
        return out
    elif photo:
        face = _cartoon(photo, size)
    else:  # hand drawn doodle portrait until a photo is added
        face = _doodle(size)
    face.thumbnail((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.alpha_composite(face.convert("RGBA"), ((size - face.width) // 2, (size - face.height) // 2))
    return out


def save_icon():
    av = make_avatar(256)
    path = os.path.join(HERE, "desktop_wellness_buddy.ico")
    av.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return path


