"""Avatar artwork for Desktop Wellness Buddy.

The active app uses the local avatar helpers below. Personal photos and custom
avatar files are intentionally not included in the public repository.
"""
import os

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))


def _grad(size, top, bottom):
    w, h = size
    g = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(g)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return g


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


