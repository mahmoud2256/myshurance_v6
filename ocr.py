"""قراءة البطاقة الشخصية وكارنيه التأمين.
- لو ANTHROPIC_API_KEY موجود: قراءة بالذكاء الاصطناعي (دقة أعلى بكتير).
- غير كده: OCR عادي (tesseract) كاحتياطي، ودقته أقل.
مفيش أي بيانات افتراضية: اللي مش مقروء بيفضل فاضي، واللي مش متأكدين منه بيتعلّم "راجع"."""
import base64
import io
import re
from datetime import date

from PIL import Image, ImageEnhance, ImageOps

import store as S

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
# أسماء الحقول عند النموذج -> مفتاح الترجمة في الواجهة
UI_KEY = {"name": "c_name", "national_id": "f_nid", "card_no": "c_card", "category": "c_cat",
          "dob": "c_dob", "expiry_date": "c_end"}

TOOLS = {
    "nid": {
        "name": "record_national_id",
        "description": "سجّل البيانات المقروءة من صورة بطاقة الرقم القومي المصرية.",
        "input_schema": {"type": "object", "properties": {
            "is_national_id": {"type": "boolean", "description": "هل الصورة بطاقة رقم قومي مصرية؟"},
            "name": {"type": ["string", "null"], "description": "الاسم الكامل بالعربي زي ما هو مطبوع (الاسم الأول + اسم الأب + الجد + العائلة). من غير سطور العنوان."},
            "national_id": {"type": ["string", "null"], "description": "الرقم القومي 14 رقم، بأرقام إنجليزية 0-9."},
            "uncertain_fields": {"type": "array", "items": {"type": "string", "enum": ["name", "national_id"]},
                                 "description": "الحقول اللي مش متأكد منها 100% (صورة مش واضحة أو حرف/رقم مشكوك فيه)."},
        }, "required": ["is_national_id", "name", "national_id", "uncertain_fields"]},
    },
    "card": {
        "name": "record_insurance_card",
        "description": "سجّل البيانات المقروءة من صورة كارنيه تأمين صحي.",
        "input_schema": {"type": "object", "properties": {
            "name": {"type": ["string", "null"], "description": "اسم المؤمن عليه زي ما هو مطبوع."},
            "card_no": {"type": ["string", "null"], "description": "رقم الكارت بالظبط زي ما هو مطبوع (حروف وأرقام)."},
            "category": {"type": ["string", "null"], "description": "الفئة (A أو B أو C أو D) لو مكتوبة."},
            "dob": {"type": ["string", "null"], "description": "تاريخ الميلاد لو مكتوب."},
            "expiry_date": {"type": ["string", "null"], "description": "تاريخ انتهاء الكارت لو مكتوب."},
            "uncertain_fields": {"type": "array", "items": {"type": "string",
                                 "enum": ["name", "card_no", "category", "dob", "expiry_date"]},
                                 "description": "الحقول اللي مش متأكد منها 100%."},
        }, "required": ["name", "card_no", "uncertain_fields"]},
    },
}
PROMPTS = {
    "nid": "ده تصوير لبطاقة رقم قومي مصرية. استخرج الاسم الكامل بالعربي والرقم القومي (14 رقم). "
           "حوّل الأرقام الهندية (٠-٩) لأرقام إنجليزية. متخمّنش: لو حاجة مش واضحة سيبها null وحطها في uncertain_fields.",
    "card": "ده تصوير لكارنيه تأمين صحي. استخرج اسم المؤمن عليه ورقم الكارت والفئة وتاريخ الميلاد وتاريخ الانتهاء لو موجودين. "
            "انسخ رقم الكارت حرف بحرف زي المطبوع، ومتخمّنش: لو حاجة مش واضحة سيبها null وحطها في uncertain_fields.",
}


def to_western(v):
    return v.translate(AR_DIGITS) if isinstance(v, str) else v


def claude_available():
    return bool(S.secret("ANTHROPIC_API_KEY"))


def tesseract_available():
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001
        return False


def prepare_image(file, max_side=1600):
    """يعدّل اتجاه الصورة ويصغّرها (صور الموبايل كبيرة) ويرجّع (JPEG bytes، PIL image)."""
    raw = file.getvalue() if hasattr(file, "getvalue") else file.read()
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    scale = max_side / max(img.size)
    if scale < 1:
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue(), img


# ───────────────────────── المحركات ─────────────────────────
def _call_claude(jpeg_bytes, kind):
    import anthropic
    client = anthropic.Anthropic(api_key=S.secret("ANTHROPIC_API_KEY"))
    tool = TOOLS[kind]
    resp = client.messages.create(
        model=S.secret("ANTHROPIC_MODEL") or "claude-sonnet-5-5", max_tokens=800,
        tools=[tool], tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.b64encode(jpeg_bytes).decode()}},
            {"type": "text", "text": PROMPTS[kind]}]}])
    for block in resp.content:
        if block.type == "tool_use":
            return dict(block.input)
    raise ValueError("no tool output")


def _tesseract_text(img, lang):
    try:
        import pytesseract
        proc = ImageEnhance.Contrast(ImageOps.grayscale(img.resize((img.width * 2, img.height * 2)))).enhance(2.0)
        return pytesseract.image_to_string(proc, lang=lang)
    except Exception:  # noqa: BLE001
        return ""


_SKIP = re.compile(r"جمهورية|مصر|العربية|بطاقة|تحقيق|الشخصية|الرقم|القومي|الاسم|يسري|حتى")
_KEYWORDS = ("card", "insured", "category", "expiry", "holder", "national")
_BAD_NAME = re.compile(r"(?i)college|school|international|company|group|academy|universit|institute|hospital|"
                       r"ltd|limited|holder|insured|national|category|co-?pay|dental|optical|maternity|expiry|"
                       r"drugs|nextcare|allianz|single|family|card")
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _gray(img, scale):
    g = ImageOps.grayscale(img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS))
    return ImageEnhance.Contrast(g).enhance(1.8)


def _ocr(img, scale, psm, lang="eng"):
    try:
        import pytesseract
        return pytesseract.image_to_string(_gray(img, scale), lang=lang, config=f"--psm {psm}")
    except Exception:  # noqa: BLE001
        return ""


def _hits(text):
    t = text.lower()
    return sum(k in t for k in _KEYWORDS)


def _order_pts(pts):
    import numpy as np
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype="float32")


def _crop_card(img):
    """يلاقي الكارت في الصورة (أزرق/رمادي فاتح على خلفية تانية) ويعدّله مستقيم. لو فشل يرجّع None."""
    try:
        import cv2
        import numpy as np
        bgr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        h, w = bgr.shape[:2]
        b = cv2.cvtColor(cv2.GaussianBlur(bgr, (9, 9), 0), cv2.COLOR_BGR2LAB)[:, :, 2]
        _, th = cv2.threshold(b, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((31, 31), np.uint8))
        th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
        cs, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cs:
            return None
        c = max(cs, key=cv2.contourArea)
        rect = cv2.minAreaRect(c)
        cw, ch = rect[1]
        if cv2.contourArea(c) < 0.15 * h * w or not (1.3 < max(cw, ch) / max(1, min(cw, ch)) < 2.0):
            return None
        box = _order_pts(cv2.boxPoints(rect))
        wd = int(max(np.linalg.norm(box[0] - box[1]), np.linalg.norm(box[3] - box[2])))
        ht = int(max(np.linalg.norm(box[0] - box[3]), np.linalg.norm(box[1] - box[2])))
        m = cv2.getPerspectiveTransform(box, np.array([[0, 0], [wd, 0], [wd, ht], [0, ht]], dtype="float32"))
        warp = cv2.warpPerspective(bgr, m, (wd, ht))
        if warp.shape[0] > warp.shape[1]:
            warp = cv2.rotate(warp, cv2.ROTATE_90_COUNTERCLOCKWISE)
        return Image.fromarray(cv2.cvtColor(warp, cv2.COLOR_BGR2RGB))
    except Exception:  # noqa: BLE001
        return None


def _upright(img):
    """يجرّب الاتجاهات ويختار اللي فيه أكتر كلمات الكارنيه."""
    base = _crop_card(img)
    angles = (0, 180) if base is not None else (0, 90, 180, 270)
    base = base if base is not None else img
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as ex:
        scores = list(ex.map(lambda a: _hits(_ocr(base.rotate(a, expand=True), 1.2, 6)), angles))
    best = max(zip(scores, [-a for a in angles], angles))
    return base.rotate(best[2], expand=True)


def _norm_hex(tok):
    t = tok.upper().replace("O", "0").replace("Q", "0").replace("I", "1").replace("L", "1")
    return t if re.fullmatch(r"[0-9A-F]{12,20}", t) else None


def _clean_words(s):
    s = re.sub(r"[^A-Za-z' \-]", " ", s or "")
    words = [w for w in s.split() if len(w) >= 2]
    return " ".join(words) if 2 <= len(words) <= 5 and not _BAD_NAME.search(s) else None


def _name_cands(text):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out = []
    for i, ln in enumerate(lines):
        if not re.search(r"(?i)insured|name\s*:", ln):
            continue
        tail = _clean_words(ln.split(":")[-1]) if ":" in ln else None
        if tail:
            out.append(tail)
            continue
        for j in (i - 1, i + 1):  # القيمة أحياناً بتتقرا في السطر اللي قبل أو بعد اللابل
            if 0 <= j < len(lines):
                c = _clean_words(lines[j].split(":")[-1])
                if c:
                    out.append(c)
    return out


def _date_cands(text):
    out = []
    for d, mon, y in re.findall(r"(\d{1,2})\s?[-–]?\s?([A-Za-z]{3})\s?[-–]?\s?(\d{4}|\d{2})(?!\d)", text):
        mo = _MONTHS.get(mon.lower())
        if not mo:
            continue
        y = int(y)
        y = y if y > 99 else (1900 + y if y > 30 else 2000 + y)
        iso = S.to_iso(f"{int(d):02d}-{mo:02d}-{y}")
        if iso:
            out.append(iso)
    return out


def _top(cands, min_votes=1):
    from collections import Counter
    if not cands:
        return None, 0
    val, n = Counter(cands).most_common(1)[0]
    return (val, n) if n >= min_votes else (None, n)


def _read_card_tesseract(img):
    from concurrent.futures import ThreadPoolExecutor
    card = _upright(img)
    with ThreadPoolExecutor(max_workers=4) as ex:  # محاولات OCR بالتوازي (tesseract بيشتغل كعملية منفصلة)
        texts = list(ex.map(lambda p: _ocr(card, p[0], p[1]), ((1, 4), (1, 11), (1.5, 11), (2, 11), (1, 6), (2, 4))))
    def _votes(txts):
        return ([h for t in txts for tok in re.findall(r"[0-9A-Za-z]{12,20}", t) if (h := _norm_hex(tok))],
                [c for t in txts for c in _name_cands(t)])
    hexes, names = _votes(texts)
    if len({h for h in hexes if hexes.count(h) >= 2}) == 0 or not _top(names, 2)[0]:
        # القراءة ناقصة: محاولات زيادة بدرجات تكبير مختلفة قبل ما نسيبه فاضي
        with ThreadPoolExecutor(max_workers=4) as ex:
            more = list(ex.map(lambda p: _ocr(card, p[0], p[1]), ((3, 11), (0.8, 11), (1.2, 4), (2.5, 6), (1.5, 4), (3, 4))))
        texts += more
    raw, unsure = {}, []
    hexes = [h for t in texts for tok in re.findall(r"[0-9A-Za-z]{12,20}", t) if (h := _norm_hex(tok))]
    val, n = _top(hexes, 2)
    if val:
        raw["card_no"] = val
        if n < 3:
            unsure.append("card_no")
    val, n = _top([c for t in texts for c in _name_cands(t)], 2)
    if val:
        raw["name"] = val
        if n < 3:
            unsure.append("name")
    cat = [m.upper() for t in texts for m in re.findall(r"(?<![A-Za-z])([A-Da-d])\s?-\s?[A-Za-z]{3,}", t)]
    val, n = _top(cat, 2)
    if val:
        raw["category"] = val
    dates = [d for t in texts for d in _date_cands(t)]
    yr = date.today().year
    for key, pick in (("dob", [d for d in dates if int(d[:4]) <= yr - 16]),
                      ("expiry_date", [d for d in dates if int(d[:4]) >= yr - 1])):
        val, n = _top(pick, 2)
        if val:
            raw[key] = val
            if n < 3:
                unsure.append(key)
    raw["uncertain_fields"] = unsure
    return raw


def _tesseract_read(img, kind):
    if kind == "card":
        return _read_card_tesseract(img)
    best = {}
    for ang in (0, 90, 180, 270):
        text = to_western(_ocr(img.rotate(ang, expand=True), 1.5, 6, "ara+eng")
                          + "\n" + _ocr(img.rotate(ang, expand=True), 1.5, 11, "ara+eng"))
        for m in re.findall(r"(?<!\d)\d{14}(?!\d)", text.replace(" ", "")):
            if S.parse_nid(m):
                best[m] = best.get(m, 0) + 1
    raw = {"uncertain_fields": ["national_id"]}
    if best:
        raw["national_id"] = max(best, key=best.get)
    return raw


# ───────────────────────── التنظيف والتحقق ─────────────────────────
def _clean_name(v):
    v = to_western(v) if isinstance(v, str) else None
    if not v:
        return None
    v = re.sub(r"[\d\|_:;,.\-]+", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    return v if len(v) >= 3 else None


def postprocess(raw, kind):
    """يرجّع (data، uncertain، warnings). مفيش تخمين: أي قيمة مش سليمة بتتشال."""
    data, warnings = {}, []
    uncertain = {UI_KEY[f] for f in (raw.get("uncertain_fields") or []) if f in UI_KEY}
    name = _clean_name(raw.get("name"))
    if name:
        data["name"] = name
    if kind == "nid":
        nid = re.sub(r"\D", "", to_western(S.nn(raw.get("national_id")) or ""))
        if nid:
            info = S.parse_nid(nid)
            if info:  # الميلاد والنوع بيتحسبوا من الرقم نفسه
                data["national_id"] = nid
                data.update(info)
            else:
                warnings.append("scan_nid_bad")
        if raw.get("is_national_id") is False:
            warnings.append("scan_not_nid")
    else:
        card = re.sub(r"[\s\-]", "", to_western(S.nn(raw.get("card_no")) or ""))
        if card:
            data["card_no"] = card
            if len(card) < 8:
                uncertain.add("c_card")
        cat = S.norm_category(raw.get("category"))
        if cat:
            data["category"] = cat
        for src, dst in (("dob", "dob"), ("expiry_date", "source_end")):
            iso = S.to_iso(to_western(S.nn(raw.get(src))))
            if iso:
                data[dst] = iso
    return data, sorted(uncertain), warnings


def read_document(file, kind):
    """kind = 'nid' | 'card'. يرجّع dict فيه data / uncertain / warnings / engine / errors."""
    out = {"data": {}, "uncertain": [], "warnings": [], "engine": None, "errors": []}
    try:
        jpeg, img = prepare_image(file)
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"image: {e}")
        return out
    raw = None
    if claude_available():
        try:
            raw, out["engine"] = _call_claude(jpeg, kind), "claude"
        except Exception as e:  # noqa: BLE001
            out["errors"].append(str(e)[:200])
    if raw is None and tesseract_available():
        raw, out["engine"] = _tesseract_read(img, kind), "tesseract"
    if raw is None:
        return out
    out["data"], out["uncertain"], out["warnings"] = postprocess(raw, kind)
    if out["engine"] == "tesseract" and kind == "nid":
        out["warnings"].append("scan_ocr_limited")  # الاسم العربي بالـ OCR العادي غير موثوق: بيتكتب يدوي
    return out


def read_all(nid_file, card_file):
    """يقرا الصورتين ويدمجهم: الاسم/الرقم القومي/الميلاد/النوع من البطاقة، والكارت/الفئة/الانتهاء من الكارنيه."""
    nid = read_document(nid_file, "nid") if nid_file else None
    card = read_document(card_file, "card") if card_file else None
    res = {"data": {}, "uncertain": set(), "warnings": [], "engine": None, "errors": []}
    for part in (card, nid):  # البطاقة تكسب في الاسم والميلاد
        if not part:
            continue
        res["data"].update({k: v for k, v in part["data"].items()
                            if not (res["data"].get(k) and k == "dob" and part is card)})
        res["uncertain"] |= set(part["uncertain"])
        res["warnings"] += part["warnings"]
        res["errors"] += part["errors"]
        res["engine"] = "claude" if "claude" in (res["engine"], part["engine"]) else (res["engine"] or part["engine"])
    if nid and card:
        n, c = nid["data"], card["data"]
        # تاريخ الميلاد على الكارنيه لو مختلف عن اللي في الرقم القومي: نحذّر ونعتمد الرقم القومي
        if n.get("dob") and c.get("dob") and n["dob"] != c["dob"]:
            res["warnings"].append("scan_dob_mismatch")
            res["data"]["dob"] = n["dob"]
    res["uncertain"] = sorted(res["uncertain"])
    res["warnings"] = list(dict.fromkeys(res["warnings"]))
    return res
