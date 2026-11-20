from colorsys import rgb_to_hsv
from io import BytesIO
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

src = Path("Soutenance_INSEA_ERP_v2.pptx")
dst = Path("dist/Soutenance_INSEA_ERP_v3.pptx")
p = Presentation(src)
W, H = p.slide_width / Inches(1), p.slide_height / Inches(1)
INK, PURPLE, PALE = "30204D", "7141BD", "F2EAFF"
ORANGE, PEACH, BG = "EF825D", "FFE1D4", "FCF9FF"
WHITE, MUTED = "FFFFFF", "665778"

def rgb(v):
    return RGBColor.from_string(v)

def palette(val):
    if len(val) != 6:
        return val
    try:
        r, g, b = (int(val[i:i+2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return val
    hue, sat, brightness = rgb_to_hsv(r, g, b)
    if not (54 <= hue * 360 <= 192 and sat > .04):
        return val
    if hue * 360 < 95 and brightness > .74:
        return "FFD0A9"
    if brightness > .95:
        return "FBF8FF"
    if brightness > .87:
        return "F0E7FC"
    if brightness > .72 and sat < .45:
        return "DBC6F8"
    if brightness > .62 and sat < .42:
        return "A889CB"
    if brightness > .47:
        return "8352C3"
    if brightness > .26:
        return "7042AD"
    return "4E2F76"

for slide in p.slides:
    for e in slide._element.iter(qn("a:srgbClr")):
        value = e.get("val")
        if value:
            e.set("val", palette(value))

def block(s, x, y, w, h, fill, kind=MSO_SHAPE.RECTANGLE, border=None):
    shape = s.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = rgb(fill)
    if border:
        shape.line.color.rgb = rgb(border)
        shape.line.width = Pt(1)
    else:
        shape.line.fill.background()
    if kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        shape.adjustments[0] = .18
    return shape

def roundbox(s, x, y, w, h, fill, border=None):
    return block(s, x, y, w, h, fill, MSO_SHAPE.ROUNDED_RECTANGLE, border)

def dot(s, x, y, d, fill):
    return block(s, x, y, d, d, fill, MSO_SHAPE.OVAL)

def text(s, value, x, y, w, h, size, fill=INK, bold=False, align=None):
    shape = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = False
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, line in enumerate(value.split("\n")):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.space_before = para.space_after = Pt(0)
        if align:
            para.alignment = align
        run = para.add_run()
        run.text = line
        run.font.name = "Aptos Display" if bold else "Aptos"
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = rgb(fill)

s = p.slides[0]
for sh in list(s.shapes):
    el = sh._element
    el.getparent().remove(el)
s.background.fill.solid()
s.background.fill.fore_color.rgb = rgb(BG)

# Editable title and illustration.
roundbox(s, .78, 1.14, .65, .075, ORANGE)
text(s, "Gestion des autorisations", .77, 1.74, 7.86, .78, 39, INK, True)
text(s, "d’absence et des congés", .77, 2.58, 7.86, .82, 39, PURPLE, True)

# Calendar and approval mark, drawn with native PowerPoint shapes.
dot(s, 8.56, 1.52, 4.02, PALE)
dot(s, 11.90, 1.45, .34, PEACH)
dot(s, 8.45, 5.15, .22, PEACH)
roundbox(s, 9.08, 2.30, 2.92, 2.60, "DCCAF8")
roundbox(s, 9.00, 2.14, 2.92, 2.60, WHITE, "DACAF3")
roundbox(s, 9.00, 2.14, 2.92, .64, PURPLE)
block(s, 9.00, 2.53, 2.92, .25, PURPLE)
for x in (9.58, 11.02):
    roundbox(s, x, 1.93, .13, .42, INK)
for row in range(3):
    for column in range(4):
        if (row, column) != (1, 2):
            roundbox(s, 9.30 + column * .56, 3.02 + row * .48, .30, .29, PALE)
roundbox(s, 10.42, 3.50, .30, .29, ORANGE)
dot(s, 11.15, 3.83, 1.04, "FFB693")
text(s, "✓", 11.15, 3.97, 1.04, .75, 32, INK, True, PP_ALIGN.CENTER)
text(s, "Odoo", 9.15, 5.83, 2.89, .52, 24, PURPLE, True, PP_ALIGN.CENTER)

# Preserve the authors in file properties, with a title-only cover.
p.core_properties.author = "Amina Bajdouri et Alaa Belga"
p.core_properties.title = "Gestion des autorisations d’absence et des congés"

def replace_text(shape, value):
    para = shape.text_frame.paragraphs[0]
    first = para.runs[0]
    first.text = value
    for run in list(para.runs)[1:]:
        run._r.getparent().remove(run._r)
    for other in list(shape.text_frame.paragraphs)[1:]:
        other._p.getparent().remove(other._p)

for sh in p.slides[3].shapes:
    if not sh.has_text_frame or not sh.text:
        continue
    v = sh.text.strip()
    new = None
    if v.startswith("Motif obligatoire. Maximum"):
        new = "Motif obligatoire. Le solde annuel reste disponible."
    elif v.startswith("Solde suffisant. Cumul"):
        new = "Contrôle du solde avant approbation. Le seuil s’exprime en jours travaillés."
    elif v.startswith("Préavis 7"):
        new = "Préavis : 7 jours calendaires"
    elif v.startswith("Pièce requise pour"):
        new = "Maladie, événement familial et sortie médicale. PDF ou image pour une sortie médicale."
    elif v.startswith("Chevauchements bloqués."):
        new = "Les durées s’expriment en jours travaillés. Les chevauchements sont bloqués."
    if new:
        replace_text(sh, new)

# Crop the source screenshot, then fit the crop in the existing picture area.
def crop_picture(slide, shape, fraction):
    original = Image.open(BytesIO(shape.image.blob)).convert("RGB")
    x0, y0, x1, y1 = fraction
    cropped = original.crop(tuple(round(n) for n in (
        x0 * original.width, y0 * original.height, x1 * original.width, y1 * original.height,
    )))
    data = BytesIO()
    cropped.save(data, "PNG")
    ratio = min(shape.width / cropped.width, shape.height / cropped.height)
    w = round(cropped.width * ratio)
    h = round(cropped.height * ratio)
    new = slide.shapes.add_picture(data, shape.left + (shape.width-w)//2,
                                   shape.top + (shape.height-h)//2, w, h)
    shape._element.addprevious(new._element)
    shape._element.getparent().remove(shape._element)

plans = {
    8: [(.015, .005, 1, .99), (0, .06, .79, .98), (.018, .03, .93, .98)],
    9: [(0, 0, 1, .53), (0, .12, .87, .94)],
    10: [(0, 0, .80, .48)],
}
for number, regions in plans.items():
    slide = p.slides[number - 1]
    pictures = sorted(
        (shape for shape in slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE),
        key=lambda shape: (round(shape.left / Inches(.1)), shape.top),
    )
    print(f"Slide {number}: {len(pictures)} captures")
    assert len(pictures) == len(regions)
    for shape, region in zip(pictures, regions):
        crop_picture(slide, shape, region)

dst.parent.mkdir(exist_ok=True)
p.save(dst)
assert len(Presentation(dst).slides) == 12
print(f"PowerPoint V3 : {dst.stat().st_size} octets")
