from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import fitz
from PIL import Image, ImageChops
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "Rapport_INSEA_ERP_Conges_LaTeX.zip"
OUT = ROOT / "dist" / "Soutenance_INSEA_ERP.pptx"

PAPER = "F4F7F5"
WHITE = "FFFFFF"
INK = "143330"
TEAL = "006960"
MUTED = "4A635E"
MINT = "DDEEE8"
LIME = "D9EDAA"
LINE = "D6E2DD"
DARK = "092F2B"

prs = Presentation()
prs.slide_width = Inches(13.333333)
prs.slide_height = Inches(7.5)
prs.core_properties.title = "Gestion des autorisations d’absence et des congés"
prs.core_properties.subject = "Soutenance INSEA · Systèmes intégrés"
prs.core_properties.author = "Amina Bajdouri et Alaa Belga"


def color(hex_value):
    return RGBColor.from_string(hex_value)


def box(slide, x, y, w, h, fill, border=None, rounding=False):
    kind = MSO_SHAPE.ROUNDED_RECTANGLE if rounding else MSO_SHAPE.RECTANGLE
    shape = slide.shapes.add_shape(kind, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color(fill)
    if border:
        shape.line.color.rgb = color(border)
        shape.line.width = Pt(0.7)
    else:
        shape.line.fill.background()
    if rounding:
        shape.adjustments[0] = 0.12
    return shape


def txt(slide, value, x, y, w, h, size=19, fg=INK, bold=False, align=None):
    sh = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = sh.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.TOP
    for i, line in enumerate(value.split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_before = p.space_after = Pt(0)
        if align is not None:
            p.alignment = align
        run = p.add_run()
        run.text = line
        run.font.name = "Aptos"
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color(fg)
    return sh


def slide(title=None, subtitle=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = color(PAPER)
    if title:
        txt(s, title, 0.65, 0.43, 12.0, 0.55, 30, bold=True)
        if subtitle:
            txt(s, subtitle, 0.67, 1.10, 12.0, 0.40, 15, MUTED)
        box(s, 0.65, 7.03, 12.02, 0.014, LINE)
        txt(s, "INSEA  /  Systèmes intégrés  /  2026–2027", 0.66, 7.16, 9, 0.22, 10, MUTED)
        txt(s, f"{len(prs.slides):02}", 11.9, 7.13, 0.76, 0.25, 11, TEAL,
            bold=True, align=PP_ALIGN.RIGHT)
    return s


def card(slide, x, y, w, h, heading, body, bg=WHITE, size=18):
    box(slide, x, y, w, h, bg, LINE, rounding=True)
    txt(slide, heading, x + .24, y + .24, w - .48, .48, 19, TEAL, True)
    txt(slide, body, x + .24, y + .88, w - .48, h - 1.06, size)


def step(slide, number, heading, body, x, y, w):
    box(slide, x, y + .02, .48, .44, MINT, rounding=True)
    txt(slide, str(number), x, y + .07, .48, .32, 15, TEAL, True, PP_ALIGN.CENTER)
    txt(slide, heading, x + .66, y, w - .66, .37, 18, INK, True)
    txt(slide, body, x + .66, y + .39, w - .66, .60, 15, MUTED)


ASSETS = {}


def get_asset(name):
    if name not in ASSETS:
        with ZipFile(SOURCE) as archive:
            item = next(path for path in archive.namelist()
                        if path.rstrip("/").endswith("/" + name))
            raw = archive.read(item)
        if name.lower().endswith(".pdf"):
            with fitz.open(stream=raw, filetype="pdf") as doc:
                pix = doc[0].get_pixmap(matrix=fitz.Matrix(3.5, 3.5), alpha=False)
                im = Image.open(BytesIO(pix.tobytes("png"))).convert("RGB")
            bg = Image.new("RGB", im.size, "white")
            diff = ImageChops.difference(im, bg).convert("L").point(lambda v: 255 if v > 10 else 0)
            if bounds := diff.getbbox():
                l, t, r, b = bounds
                im = im.crop((max(0, l-9), max(0, t-9), min(im.width, r+9), min(im.height, b+9)))
            data = BytesIO()
            im.save(data, format="PNG", optimize=True)
            raw = data.getvalue()
        with Image.open(BytesIO(raw)) as img:
            ASSETS[name] = (raw, img.width, img.height)
    return ASSETS[name]


def figure(slide, name, x, y, w, h, caption=None):
    box(slide, x, y, w, h, WHITE, LINE, rounding=True)
    pad = .14
    inner_w, inner_h = w - 2 * pad, h - 2 * pad - (.40 if caption else 0)
    raw, px, py = get_asset(name)
    ratio = min(inner_w / px, inner_h / py)
    iw, ih = px * ratio, py * ratio
    slide.shapes.add_picture(BytesIO(raw), Inches(x + (w - iw) / 2),
                             Inches(y + pad + (inner_h - ih) / 2),
                             width=Inches(iw), height=Inches(ih))
    if caption:
        txt(slide, caption, x + .15, y + h - .42, w - .30, .29, 12, MUTED,
            align=PP_ALIGN.CENTER)


s = slide()
s.background.fill.fore_color.rgb = color(DARK)
box(s, .72, .70, .36, .045, LIME)
txt(s, "INSEA   /   3ᵉ année DSE   /   2026–2027", 1.19, .58, 7.15, .32, 13, LIME, True)

txt(s, "Gestion des\nautorisations d’absence\net des congés", .70, 1.57, 8.05, 2.44,
    39, WHITE, True)
txt(s, "Société Lambda", .76, 4.07, 7.88, .52, 24, WHITE, True)
txt(s, "Intégration dans Odoo Community 17", .76, 4.65, 7.88, .42, 19, "BEE0D5")

box(s, 9.05, 1.31, 3.56, 4.57, "123F39", "396159", rounding=True)
txt(s, "Circuit de validation", 9.32, 1.66, 3.02, .34, 15, WHITE, True)
box(s, 9.51, 2.52, .021, 2.18, "659286")
for y, role, action in [
    (2.31, "Employé", "Saisit et soumet"),
    (3.42, "Manager", "Examine et décide"),
    (4.53, "Responsable RH", "Valide si nécessaire"),
]:
    box(s, 9.38, y + .03, .27, .27, LIME, rounding=True)
    txt(s, role, 9.85, y, 2.49, .33, 16, WHITE, True)
    txt(s, action, 9.85, y + .39, 2.48, .34, 14, "BEE0D5")

box(s, .73, 6.35, 11.89, .014, "396159")
txt(s, "Amina Bajdouri  ·  Alaa Belga", .76, 6.64, 6.70, .42, 18, WHITE, True)
txt(s, "Mini-projet de systèmes intégrés", 7.43, 6.71, 5.17, .33,
    14, "BEE0D5", align=PP_ALIGN.RIGHT)

s = slide("Un circuit commun pour la société Lambda",
          "Centraliser la demande, les pièces, les décisions et l’historique dans Odoo.")
card(s, .65, 1.83, 5.85, 3.48, "Situation de départ",
     "Les demandes circulaient sur papier ou par échanges informels.\n\n"
     "Le suivi des absences de l’équipe et la vérification du solde annuel demandaient des relances.")
card(s, 6.74, 1.83, 5.94, 3.48, "Parcours proposé",
     "L’employé dépose une demande et suit sa décision.\n\n"
     "Le N+1 vérifie la disponibilité de son équipe. Les RH interviennent quand une seconde décision est requise.",
     MINT)
txt(s, "Périmètre  ·  Sorties courtes, congé payé, mariage, naissance, décès et maladie.",
    .70, 5.75, 11.9, .66, 17, TEAL, True)

s = slide("Quatre acteurs dans le circuit",
          "Diagramme de cas d’utilisation issu du rapport.")
figure(s, "cas_utilisation.pdf", .65, 1.62, 6.36, 5.08)
step(s, 1, "Employé", "Saisit, justifie et soumet sa demande. Consulte le statut et le solde.", 7.34, 1.77, 5.21)
step(s, 2, "Manager direct", "Consulte les demandes de son équipe et prend la première décision.", 7.34, 2.94, 5.21)
step(s, 3, "Responsable RH", "Vérifie les pièces et rend la décision finale quand elle est requise.", 7.34, 4.11, 5.21)
step(s, 4, "Administrateur", "Déploie le module et configure les comptes et habilitations.", 7.34, 5.28, 5.21)

s = slide("Les règles déclenchées par la demande",
          "Les contrôles sont appliqués côté serveur et s’appuient sur le calendrier de travail Odoo.")
card(s, .65, 1.64, 5.88, 2.20, "Autorisation de sortie",
     "Motif obligatoire. Maximum 4 h par sortie, 3 sorties et 8 h par mois. Le solde annuel est préservé.", size=17)
card(s, 6.74, 1.64, 5.94, 2.20, "Congé payé annuel",
     "Solde suffisant. Cumul de 1,5 jour par mois travaillé. Préavis de 7 jours calendaires au-delà de 3 jours.", size=17)
card(s, .65, 4.03, 5.88, 2.24, "Justificatifs",
     "Pièce requise pour maladie, événement familial ou sortie médicale. Pour une sortie médicale, PDF ou image.", size=17)
card(s, 6.74, 4.03, 5.94, 2.24, "Calendrier et intégrité",
     "Chevauchements bloqués. Congés familiaux en jours travaillés : mariage 4, naissance 3, décès 2 ou 3.", size=17)

s = slide("Un module intégré à Odoo Community 17",
          "Architecture de l’environnement de démonstration.")
figure(s, "architecture.pdf", .65, 1.65, 12.03, 2.20)
card(s, .65, 4.08, 3.87, 2.38, "GitHub Codespaces",
     "Le port privé 8069 relie le navigateur à l’environnement distant.", size=17)
card(s, 4.72, 4.08, 3.87, 2.38, "Odoo + hr_holidays",
     "Le module INSEA étend l’application Congés avec Python et XML.", MINT, 17)
card(s, 8.79, 4.08, 3.89, 2.38, "PostgreSQL 16",
     "Docker Compose initialise les services et conserve les données dans des volumes.", size=17)

s = slide("L’héritage garde les mécanismes d’Odoo",
          "Diagramme de classes issu du rapport.")
figure(s, "classes.pdf", .65, 1.57, 7.65, 5.2)
card(s, 8.55, 1.64, 4.13, 2.17, "Modèles étendus",
     "hr.leave, hr.leave.type et hr.employee portent les champs et contrôles INSEA.", size=17)
card(s, 8.55, 4.03, 4.13, 2.54, "Mécanismes réutilisés",
     "États, actions de validation, calendrier, allocations et pièces jointes restent dans le socle Odoo.", MINT, 17)

s = slide("Le type de demande détermine le circuit",
          "Diagramme d’états-transitions issu du rapport.")
figure(s, "etats.pdf", .65, 1.62, 7.46, 5.10)
card(s, 8.35, 1.65, 4.33, 1.76, "Sortie courte",
     "Le manager rend la décision finale.", size=16)
card(s, 8.35, 3.56, 4.33, 1.76, "Congé à deux niveaux",
     "L’accord du manager déclenche l’étape RH.", size=16)
txt(s, "Le refus exige un motif. La validation finale vérifie le justificatif lorsqu’il est requis.",
    8.53, 5.64, 3.97, .82, 15, MUTED)

s = slide("Recette observée  /  Saisie et soumission",
          "Sortie administrative de deux heures le 27 novembre 2026.")
figure(s, "01_saisie_sortie.jpg", .65, 1.67, 6.72, 3.86, "Formulaire employé au stade du brouillon")
figure(s, "02_soumission.jpg", 7.58, 1.67, 5.10, 2.54, "Historique du passage à To Approve")
figure(s, "03_activite_manager.jpg", 7.58, 4.41, 5.10, 2.30, "Activité d’approbation dans Discuss")
txt(s, "10 h → 12 h  ·  Démarche administrative", .81, 5.77, 6.38, .46, 18, TEAL, True)
txt(s, "L’employé soumet la demande et le manager reçoit l’activité à traiter.",
    .81, 6.28, 6.33, .55, 15, MUTED)

s = slide("Recette observée  /  Approbation et notification",
          "Le manager valide la sortie courte en une seule étape.")
figure(s, "04_approbation_manager.jpg", .65, 1.67, 12.03, 2.60, "Demande de sortie au statut Approved")
figure(s, "05_notification_employe.jpg", .65, 4.43, 12.03, 2.28, "Notification et trace du changement de statut")

s = slide("Solde de départ et résultats de test",
          "Résultats observés et résultat à montrer en démonstration.")
figure(s, "06_solde_initial.jpg", .65, 1.68, 7.68, 4.85, "Allocation initiale de cinq jours visible dans Odoo")
card(s, 8.57, 1.68, 4.11, 2.12, "19 tests réussis",
     "0 échec et 0 erreur selon le journal de mise à niveau transmis.", MINT, 17)
card(s, 8.57, 4.02, 4.11, 2.51, "5 jours → 4 jours",
     "Résultat attendu après validation RH d’un jour de congé payé sur une allocation initiale de cinq jours.", size=17)

s = slide("Démonstration en direct",
          "Trois comptes de test et une allocation annuelle initiale.")
card(s, .65, 1.78, 5.83, 4.16, "01  /  Sortie courte",
     "Employé · Saisir deux heures, sélectionner le motif et soumettre.\n\n"
     "Manager · Approuver la demande.\n\n"
     "Employé · Ouvrir la notification dans Discuss.", size=18)
card(s, 6.69, 1.78, 5.99, 4.16, "02  /  Congé payé",
     "Employé · Soumettre une journée de congé payé.\n\n"
     "Manager · Donner le premier accord.\n\n"
     "RH · Valider, puis vérifier le solde depuis la session employé.", MINT, 18)

s = slide("Bilan et questions",
          "Gestion des autorisations d’absence et des congés dans Odoo.")
card(s, .65, 1.72, 7.45, 3.44, "Ce que la solution apporte",
     "Les demandes, les décisions et leur historique sont réunis dans Congés.\n\n"
     "Les contrôles propres à Lambda s’ajoutent au socle Odoo par héritage.\n\n"
     "Le parcours de sortie courte est documenté de bout en bout.", MINT, 18)
card(s, 8.35, 1.72, 4.33, 3.44, "Choix de mise en œuvre",
     "Le binôme applique aussi la double approbation à la maladie d’un jour. L’énoncé mentionne le seuil de plus d’un jour pour le passage RH.", size=17)
txt(s, "Merci pour votre attention.", .71, 5.79, 11.85, .61, 27, TEAL, True)

assert len(ASSETS) == 10
assert len(prs.slides) == 12
for n, s in enumerate(prs.slides, 1):
    for shape in s.shapes:
        assert 0 <= shape.left <= shape.left + shape.width <= prs.slide_width + 5, (n, shape.name)
        assert 0 <= shape.top <= shape.top + shape.height <= prs.slide_height + 5, (n, shape.name)
OUT.parent.mkdir(exist_ok=True)
prs.save(OUT)
verified = Presentation(OUT)
assert len(verified.slides) == 12
with ZipFile(OUT) as archive:
    assert archive.testzip() is None
    print(f"PowerPoint vérifié : {len(verified.slides)} diapositives, {len(ASSETS)} visuels originaux, {OUT.stat().st_size} octets.")
