"""كارت العضوية PDF (للطباعة). الأسماء العربي بتتكتب بخط DejaVu لو متسطّب (fonts-dejavu-core في packages.txt)."""
import io
import os
import re

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A6, landscape
from reportlab.pdfgen import canvas

import store as S

TEAL_DARK, TEAL, SAND = "#07363B", "#0B4F55", "#E8C9A0"
_FONTS = {"regular": ("MS-Regular", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
          "bold": ("MS-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")}
_ARABIC = re.compile(r"[\u0600-\u06FF]")
_registered = None


def _fonts():
    """يرجّع (regular, bold). لو DejaVu مش موجود يرجع لـ Helvetica (والعربي هيتبدّل بـ ?)."""
    global _registered
    if _registered is None:
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            for name, path in _FONTS.values():
                pdfmetrics.registerFont(TTFont(name, path))
            _registered = (_FONTS["regular"][0], _FONTS["bold"][0])
        except Exception:  # noqa: BLE001
            _registered = ("Helvetica", "Helvetica-Bold")
    return _registered


def _shape(text):
    """يوصّل الحروف العربي ويظبط الاتجاه (لو المكتبتين موجودتين)."""
    text = str(text or "")
    if not _ARABIC.search(text):
        return text
    if _fonts()[0] == "Helvetica":
        return _ARABIC.sub("?", text)
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:  # noqa: BLE001
        return text


def generate_card_pdf(member, company="", start=None, end=None):
    """member: dict/Series بحقول العضو. يرجّع bytes لملف PDF."""
    g = lambda k: S.nn(member.get(k)) or "—"  # noqa: E731
    reg, bold = _fonts()
    buf = io.BytesIO()
    w, h = landscape(A6)
    c = canvas.Canvas(buf, pagesize=(w, h))
    c.setTitle(f"Myshurance card - {g('name')}")
    c.setFillColor(HexColor(TEAL_DARK))
    c.rect(0, 0, w, h, fill=1, stroke=0)
    c.setFillColor(HexColor(TEAL))
    c.rect(0, h - 64, w, 64, fill=1, stroke=0)
    c.setFillColor(HexColor(SAND))
    c.rect(0, h - 68, w, 4, fill=1, stroke=0)
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont(bold, 18)
    c.drawString(22, h - 34, "Myshurance")
    c.setFont(reg, 8.5)
    c.setFillColor(HexColor(SAND))
    c.drawString(22, h - 50, "It's all about you  |  Health insurance membership")
    # الاسم
    name = _shape(g("name"))
    size = 15 if c.stringWidth(name, bold, 15) < w - 44 else 11
    c.setFillColor(HexColor("#FFFFFF"))
    c.setFont(bold, size)
    c.drawString(22, h - 98, name)
    rows = [("Card No", g("card_no")), ("Staff No", g("staff_no")),
            ("Tier / Type", f"{g('category')}  /  {g('dependency')}"), ("Policy", g("policy_no"))]
    y = h - 122
    for label, val in rows:
        c.setFont(reg, 8)
        c.setFillColor(HexColor(SAND))
        c.drawString(22, y, label)
        c.setFont(bold, 10)
        c.setFillColor(HexColor("#FFFFFF"))
        c.drawString(92, y, str(val))
        y -= 16
    c.setFont(reg, 8)
    c.setFillColor(HexColor(SAND))
    c.drawString(22, y, "Company")
    c.setFont(reg, 9)
    c.setFillColor(HexColor("#FFFFFF"))
    c.drawString(92, y, _shape(company or "—"))
    c.setFont(reg, 8)
    c.setFillColor(HexColor(SAND))
    c.drawString(22, 22, f"Valid: {S.fmt_date(start)}  to  {S.fmt_date(end)}")
    c.drawString(22, 11, "Printout for reference. The insurer's issued card governs coverage.")
    c.save()
    return buf.getvalue()
