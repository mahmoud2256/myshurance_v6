"""طبقة البيانات + منطق العمل لبرنامج Myshurance."""
import hashlib
import hmac
import io
import re
import secrets
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

CAIRO = ZoneInfo("Africa/Cairo")

PROVIDERS = ["Sarwa Life", "Sarwa", "Orient", "AXA", "GIG Life", "Allianz"]
CLIENTS_MAP = {
    "90502239912": "مدرسه نيو سكول",
    "90502239913": "بوب ليدرز",
    "90502239934": "مدرسه ليدرز انترناشونال",
    "90502239932": "ليدرز كوليدج للخدمات التعليميه",
}
DEFAULT_START, DEFAULT_END = "2026-09-29", "2027-09-28"

REQ_TYPES = ["add", "delete", "replace", "upgrade"]
REQ_STATUSES = ["draft", "sent", "review", "done", "rejected", "cancelled"]
OPEN_STATUSES = ["draft", "sent", "review"]
TRANSITIONS = {
    "draft": ["sent", "cancelled"],
    "sent": ["review", "rejected", "cancelled"],
    "review": ["done", "rejected", "cancelled"],
    "rejected": ["draft"],
    "done": [],
    "cancelled": [],
}
REF_PREFIX = {"add": "ADD", "delete": "DEL", "replace": "REP", "upgrade": "UPG"}
DEPENDENCIES = ["PRINCIPAL", "SPOUSE", "CHILD", "OTHER"]

# حقول العضو اللي بتتنقل في طلب الإضافة
MEMBER_FIELDS = ["name", "staff_no", "card_no", "national_id", "phone", "dependency", "dob",
                 "gender", "category", "source_start", "source_end"]

COLS = {
    "members": ["name", "staff_no", "card_no", "national_id", "phone", "policy_no", "dependency", "dob",
                "gender", "category", "source_start", "source_end", "status", "termination_date", "portal_pw"],
    "requests": ["ref_no", "type", "member_id", "member_name", "staff_no", "policy_no", "effective_date",
                 "details", "payload", "status", "created_by", "updated_at"],
    "policies": ["policy_no", "type", "start_date", "end_date", "premium", "status"],
    "notifications": ["event", "message", "status", "attempts", "sent_at", "error"],
    "approvals": ["ref_no", "member_id", "member_name", "staff_no", "policy_no", "approval_type", "provider",
                  "hospital", "amount", "details", "status", "created_by", "decided_by", "updated_at"],
    "audit_log": ["actor", "role", "action", "entity", "ref", "details"],
}

TYPE_AR = {"add": "إضافة", "delete": "حذف", "replace": "بدل فاقد", "upgrade": "ترقية فئة"}
STATUS_AR = {"draft": "مسودة", "sent": "مُرسل", "review": "قيد المراجعة", "done": "تم التنفيذ",
             "rejected": "مرفوض", "cancelled": "ملغي"}
ICON = {"add": "🟢", "delete": "🔴", "replace": "🟡", "upgrade": "🔵"}


# ───────────────────────── أدوات عامة ─────────────────────────
def now_iso():
    return datetime.now(CAIRO).isoformat(timespec="seconds")


def nn(v):
    """يرجّع None للفاضي / NaN، وإلا القيمة (نصوص بتتقص)."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v


def str_id(v):
    """أرقام وظيفية/كروت: يمنع 104.0 ويحافظ على الأصفار لو جاية نص."""
    v = nn(v)
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def to_iso(v):
    v = nn(v)
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", s):
        d = pd.to_datetime(s, errors="coerce")
    else:
        d = pd.to_datetime(s, dayfirst=True, errors="coerce")
    return None if pd.isna(d) else d.date().isoformat()


def fmt_date(v):
    iso = to_iso(v)
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else "—"


def fmt_ts(v):
    v = nn(v)
    return str(v)[:16].replace("T", " ") if v else "—"


def norm_name(s):
    return re.sub(r"\s+", " ", str(nn(s) or "")).casefold()


def norm_gender(v):
    v = str(nn(v) or "").strip().lower()
    if v in ("m", "male", "ذكر", "1"):
        return "M"
    if v in ("f", "female", "أنثى", "انثى", "2"):
        return "F"
    return None


def norm_category(v):
    m = re.match(r"([A-D])(?:$|[\s\-_/])", str(nn(v) or "").strip().upper())
    return m.group(1) if m else None


def parse_nid(nid):
    """يستخرج تاريخ الميلاد والنوع من الرقم القومي المصري (14 رقم)."""
    nid = str(nn(nid) or "")
    if len(nid) != 14 or not nid.isdigit():
        return {}
    try:
        century, yy, mm, dd = int(nid[0]), int(nid[1:3]), int(nid[3:5]), int(nid[5:7])
        if century not in (2, 3):
            return {}
        year = (1900 if century == 2 else 2000) + yy
        return {"dob": date(year, mm, dd).isoformat(), "gender": "M" if int(nid[12]) % 2 == 1 else "F"}
    except ValueError:
        return {}


def secret(name):
    try:
        v = st.secrets.get(name)
    except Exception:
        return None
    return str(v) if v not in (None, "") else None


# ───────────────────────── الاتصال بـ Supabase ─────────────────────────
@st.cache_resource
def _connect():
    url, key = secret("SUPABASE_URL"), secret("SUPABASE_KEY")
    if not url or not key:
        return None, None
    try:
        from supabase import create_client
        return create_client(url, key), None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


SB, SB_ERR = _connect()


def _mem():
    if "db" not in st.session_state:
        st.session_state.db = {k: [] for k in COLS}
        for no in CLIENTS_MAP:
            st.session_state.db["policies"].append({
                "id": str(uuid.uuid4()), "policy_no": no, "type": "p_health", "start_date": DEFAULT_START,
                "end_date": DEFAULT_END, "premium": 0, "status": "active", "created_at": now_iso()})
    return st.session_state.db


# ───────────────────────── CRUD ─────────────────────────
def _clean(table, row, drop_none):
    out = {}
    for k, v in row.items():
        if k not in COLS[table]:
            continue
        v = nn(v) if not isinstance(v, (dict, list)) else v
        if isinstance(v, (date, datetime)):
            v = v.isoformat()
        if v is None and drop_none:
            continue
        out[k] = v
    return out


def load(table):
    cols = ["id"] + COLS[table] + ["created_at"]
    rows = []
    try:
        if SB:
            start = 0
            while True:
                chunk = (SB.table(table).select("*").order("created_at", desc=True).order("id")
                         .range(start, start + 999).execute().data)
                rows += chunk
                if len(chunk) < 1000:
                    break
                start += 1000
        else:
            rows = list(reversed(_mem()[table]))
    except Exception as e:  # noqa: BLE001
        st.error(f"{table}: {e}")
        rows = []
    return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame(columns=cols)


def insert(table, row):
    row = _clean(table, row, drop_none=True)
    if SB:
        res = SB.table(table).insert(row).execute()
        return res.data[0] if res.data else row
    rec = {**row, "id": str(uuid.uuid4()), "created_at": now_iso()}
    _mem()[table].append(rec)
    return rec


def insert_many(table, rows):
    rows = [_clean(table, r, drop_none=True) for r in rows]
    if not rows:
        return
    if SB:
        for i in range(0, len(rows), 200):
            SB.table(table).insert(rows[i:i + 200]).execute()
    else:
        for r in rows:
            _mem()[table].append({**r, "id": str(uuid.uuid4()), "created_at": now_iso()})


def update(table, rid, row):
    row = _clean(table, row, drop_none=False)
    if SB:
        SB.table(table).update(row).eq("id", rid).execute()
    else:
        for r in _mem()[table]:
            if r["id"] == rid:
                r.update(row)


# ───────────────────────── الأعضاء ─────────────────────────
def find_member(policy_no, staff_no=None, name=None, members=None):
    """يرجّع Series للعضو أو None. الأولوية للرقم الوظيفي ثم الاسم."""
    df = load("members") if members is None else members
    if df.empty:
        return None
    df = df[df["policy_no"].astype(str) == str(policy_no)]
    staff = str_id(staff_no)
    if staff:
        hit = df[df["staff_no"].map(str_id) == staff]
        if not hit.empty:
            return hit.iloc[0]
    if name:
        hit = df[df["name"].map(norm_name) == norm_name(name)]
        if not hit.empty:
            return hit.iloc[0]
    return None


ALIASES = {
    "staff_no": ["employee no", "employee number", "emp no", "staff no", "staff number", "staff id",
                 "الرقم الوظيفي", "الرقم الوظيفي staff number"],
    "name": ["employee name", "insured name", "member name", "full name", "name", "الاسم", "الاسم الكامل"],
    "card_no": ["card number", "card no", "card", "رقم كارت التأمين", "رقم الكارت"],
    "national_id": ["national id", "nid", "الرقم القومي"],
    "dob": ["date of birth", "dob", "birth date", "birthdate", "تاريخ الميلاد"],
    "gender": ["gender", "sex", "النوع"],
    "category": ["category", "class", "tier", "الفئة"],
    "dependency": ["dependency", "relation", "relationship", "member type", "نوع العضو",
                   "نوع العضو dependency"],
    "source_start": ["start date", "effective date", "inception date", "تاريخ السريان بالمصدر"],
    "source_end": ["end date", "expiry date", "expiry", "expiry date ", "تاريخ الانتهاء بالمصدر"],
}


def _hn(s):
    return re.sub(r"\s+", " ", re.sub(r"[\.:_#]+", " ", str(s))).strip().lower()


def detect_columns(df):
    cols = {_hn(c): c for c in df.columns}
    return {f: cols[_hn(n)] for f, names in ALIASES.items() for n in names[::-1] if _hn(n) in cols}


def rows_from_df(df, mapping):
    """mapping: field -> اسم عمود في الملف."""
    out = []
    for _, r in df.iterrows():
        g = lambda f: r.get(mapping[f]) if mapping.get(f) is not None else None  # noqa: E731
        name = nn(g("name"))
        if not name:
            continue
        nid = str_id(g("national_id"))
        row = {
            "name": str(name), "staff_no": str_id(g("staff_no")), "card_no": str_id(g("card_no")),
            "national_id": nid if nid and nid.isdigit() and len(nid) == 14 else None,
            "dob": to_iso(g("dob")), "gender": norm_gender(g("gender")), "category": norm_category(g("category")),
            "dependency": (str(nn(g("dependency"))).upper() if nn(g("dependency")) else None),
            "source_start": to_iso(g("source_start")), "source_end": to_iso(g("source_end")),
        }
        out.append(row)
    return out


def upsert_members(policy_no, rows):
    """يستورد صفوف الماستر: العضو (بالرقم الوظيفي أو الاسم) يتحدّث، والجديد يتضاف.
    مبيمسحش حد، ومبيغيّرش حالة العضوية. يرجّع (جديد، متحدّث، من غير تغيير)."""
    existing = load("members")
    existing = existing[existing["policy_no"].astype(str) == str(policy_no)]
    by_staff, by_name, rec = {}, {}, {}
    for r in existing.to_dict("records"):
        rec[r["id"]] = r
        if str_id(r["staff_no"]):
            by_staff[str_id(r["staff_no"])] = r["id"]
        by_name[norm_name(r["name"])] = r["id"]
    new_rows, updated, same = [], 0, 0
    for row in rows:
        key = row.get("staff_no")
        rid = by_staff.get(key) if key else by_name.get(norm_name(row["name"]))
        if rid is None:
            new_rows.append({**row, "policy_no": policy_no, "status": "active"})
            tag = f"new{len(new_rows)}"
            if key:
                by_staff[key] = tag
            by_name[norm_name(row["name"])] = tag
            continue
        if rid.startswith("new"):  # مكرر جوه نفس الشيت
            same += 1
            continue
        old = rec[rid]
        changes = {k: v for k, v in row.items() if v is not None and nn(old.get(k)) != v}
        if changes:
            update("members", rid, changes)
            updated += 1
        else:
            same += 1
    insert_many("members", new_rows)
    return len(new_rows), updated, same


# ───────────────────────── الوثائق ─────────────────────────
def policies_df():
    df = load("policies")
    rows = {str(r["policy_no"]): r for r in df.to_dict("records")}
    out = []
    for no, school in CLIENTS_MAP.items():
        r = rows.pop(no, {})
        out.append({"policy_no": no, "school": school, "start_date": to_iso(r.get("start_date")),
                    "end_date": to_iso(r.get("end_date"))})
    for no, r in rows.items():
        out.append({"policy_no": no, "school": "", "start_date": to_iso(r.get("start_date")),
                    "end_date": to_iso(r.get("end_date"))})
    df = pd.DataFrame(out, columns=["policy_no", "school", "start_date", "end_date"]).astype(object)
    return df.where(df.notna(), None)  # الفاضي يفضل None مش NaN


def save_policy_dates(policy_no, start, end):
    row = {"policy_no": policy_no, "type": "p_health", "start_date": to_iso(start), "end_date": to_iso(end),
           "status": "active"}
    if SB:
        SB.table("policies").upsert(_clean("policies", row, False), on_conflict="policy_no").execute()
        return
    for r in _mem()["policies"]:
        if r["policy_no"] == policy_no:
            r.update(row)
            return
    insert("policies", row)


# ───────────────────────── الإشعارات (واتساب عبر جدول notifications) ─────────────────────────
def _t():
    return datetime.now(CAIRO).strftime("%Y-%m-%d %H:%M")


def _ctx(req):
    pol = nn(req.get("policy_no")) or "—"
    school = CLIENTS_MAP.get(pol, "")
    return pol, f" ({school})" if school else ""


def msg_created(req, user):
    typ, (pol, school) = req["type"], _ctx(req)
    lines = [f"{ICON[typ]} طلب {TYPE_AR[typ]} جديد", f"المرجع: {req['ref_no']}",
             f"العضو: {req.get('member_name') or '—'}"]
    if nn(req.get("staff_no")):
        lines.append(f"الرقم الوظيفي: {req['staff_no']}")
    lines.append(f"الوثيقة: {pol}{school}")
    if typ == "delete" and nn(req.get("effective_date")):
        lines.append(f"تاريخ الحذف: {fmt_date(req['effective_date'])}")
    if typ == "upgrade":
        p = _payload(req)
        lines.append(f"الفئة: {p.get('old_category') or '—'} ← {p.get('new_category') or '—'}")
    return "\n".join(lines + [f"بواسطة: {user or '—'}", f"الوقت: {_t()}"])


def msg_status(req, old, new, user):
    typ, (pol, school) = req["type"], _ctx(req)
    lines = [f"🔄 الطلب {req['ref_no']} ({TYPE_AR[typ]}) اتغيرت حالته",
             f"من: {STATUS_AR[old]} ← إلى: {STATUS_AR[new]}",
             f"العضو: {req.get('member_name') or '—'}", f"الوثيقة: {pol}{school}"]
    if new == "done" and typ == "add":
        lines.append("✅ تم تفعيل العضو في الوثيقة")
    elif new == "done" and typ == "delete":
        lines.append("⛔ تم إنهاء عضوية العضو (السجل محفوظ)")
    elif new == "done" and typ == "upgrade":
        lines.append(f"⬆ تم تغيير الفئة إلى {_payload(req).get('new_category') or '—'}")
    return "\n".join(lines + [f"بواسطة: {user or '—'}", f"الوقت: {_t()}"])


def notify_import(policy_no, new, upd, same, user):
    pol, school = _ctx({"policy_no": policy_no})
    notify("master_import", "\n".join([
        "📥 استيراد ماستر Allianz", f"الوثيقة: {pol}{school}",
        f"جديد: {new} | اتحدّث: {upd} | بدون تغيير: {same}", f"بواسطة: {user or '—'}", f"الوقت: {_t()}"]))
    audit("member_import", "policy", policy_no, f"new {new} | updated {upd} | same {same}")


def notify_policy(policy_no, start, end, user):
    pol, school = _ctx({"policy_no": policy_no})
    notify("policy_dates", "\n".join([
        "📅 تعديل تواريخ وثيقة", f"الوثيقة: {pol}{school}",
        f"من {fmt_date(start)} إلى {fmt_date(end)}", f"بواسطة: {user or '—'}", f"الوقت: {_t()}"]))
    audit("policy_dates", "policy", policy_no, f"{to_iso(start)} -> {to_iso(end)}")


def notify(event, message):
    try:
        insert("notifications", {"event": event, "message": message, "status": "pending", "attempts": 0})
    except Exception as e:  # noqa: BLE001 - الإشعار ميوقفش الشغل
        st.warning(f"notifications: {e}")


def audit(action, entity, ref=None, details=None, actor=None, role=None):
    """سجل تدقيق: مين عمل إيه ومتى. بيتسجل تلقائياً ومفيش في البرنامج أي تعديل أو مسح فيه.
    لو الجدول مش موجود بيظهر تحذير مرة واحدة في الجلسة ومبيوقفش الشغل."""
    ss = st.session_state
    try:
        insert("audit_log", {"actor": actor or ss.get("user_name") or "—", "role": role or ss.get("role"),
                             "action": action, "entity": entity, "ref": ref, "details": details})
    except Exception as e:  # noqa: BLE001
        if not ss.get("_audit_warned"):
            ss["_audit_warned"] = True
            st.warning(f"audit_log: {e}")


# ───────────────────────── الطلبات ─────────────────────────
def next_ref(rtype):
    prefix = f"REQ-{REF_PREFIX[rtype]}-{datetime.now(CAIRO).year}-"
    nums = [int(x[len(prefix):]) for x in load("requests")["ref_no"].dropna().astype(str)
            if x.startswith(prefix) and x[len(prefix):].isdigit()]
    return f"{prefix}{(max(nums) if nums else 0) + 1:04d}"


def _json_safe(d):
    return {k: (v.isoformat() if isinstance(v, (date, datetime)) else nn(v)) for k, v in d.items()}


def create_request(rtype, policy_no, member_name, payload, user, member_id=None, staff_no=None,
                   effective_date=None, details=None):
    rec = insert("requests", {
        "ref_no": next_ref(rtype), "type": rtype, "member_id": member_id, "member_name": member_name,
        "staff_no": staff_no, "policy_no": policy_no, "effective_date": to_iso(effective_date),
        "details": details, "payload": _json_safe(payload), "status": "draft", "created_by": user or None})
    rec = {**rec, "type": rtype, "member_name": member_name, "staff_no": staff_no, "policy_no": policy_no,
           "effective_date": to_iso(effective_date)}
    notify("request_created", msg_created(rec, user))
    audit("request_created", "request", rec.get("ref_no"), f"{rtype} | {member_name} | {policy_no}")
    return rec


def _open_requests(reqs, rtype, policy_no, member_id=None, staff_no=None, name=None):
    df = reqs[(reqs["type"] == rtype) & (reqs["status"].isin(OPEN_STATUSES))
              & (reqs["policy_no"].astype(str) == str(policy_no))]
    if member_id:
        return df[df["member_id"] == member_id]
    if staff_no:
        return df[df["staff_no"].map(str_id) == str_id(staff_no)]
    return df[df["member_name"].map(norm_name) == norm_name(name)]


def create_add_request(policy_no, data, effective_date, user):
    """يرجّع (الطلب، None) أو (None، مفتاح رسالة الخطأ)."""
    name = nn(data.get("name"))
    if not name:
        return None, "err_name"
    if not policy_no:
        return None, "err_policy"
    d = {k: nn(data.get(k)) for k in MEMBER_FIELDS}
    d["name"], d["staff_no"], d["card_no"] = str(name), str_id(d["staff_no"]), str_id(d["card_no"])
    if d["national_id"]:
        d["national_id"] = str_id(d["national_id"])
        info = parse_nid(d["national_id"])
        if not info:
            return None, "err_nid"
        d["dob"], d["gender"] = to_iso(d["dob"]) or info["dob"], norm_gender(d["gender"]) or info["gender"]
    d.update(dob=to_iso(d["dob"]), gender=norm_gender(d["gender"]), category=norm_category(d["category"]),
             source_start=to_iso(d["source_start"]), source_end=to_iso(d["source_end"]),
             dependency=(str(d["dependency"]).upper() if d["dependency"] else None))
    ex = find_member(policy_no, d["staff_no"], d["name"])
    if ex is not None and (nn(ex["status"]) or "active") == "active":
        return None, "err_exists"
    if not _open_requests(load("requests"), "add", policy_no, staff_no=d["staff_no"], name=d["name"]).empty:
        return None, "err_dup_req"
    rec = create_request("add", policy_no, d["name"], d, user, staff_no=d["staff_no"],
                         effective_date=effective_date,
                         member_id=(ex["id"] if ex is not None else None))
    return rec, None


def _snapshot(m):
    return {k: nn(m.get(k)) for k in ("name", "staff_no", "card_no", "national_id", "dob", "gender",
                                      "category", "dependency")}


def create_delete_request(member, effective_date, user, details=None):
    if (nn(member["status"]) or "active") != "active":
        return None, "err_not_active"
    if not _open_requests(load("requests"), "delete", member["policy_no"], member_id=member["id"]).empty:
        return None, "err_open_exists"
    rec = create_request("delete", member["policy_no"], member["name"], _snapshot(member), user,
                         member_id=member["id"], staff_no=str_id(member["staff_no"]),
                         effective_date=effective_date, details=details)
    return rec, None


def create_replace_request(member, reason, user, details=None):
    if (nn(member["status"]) or "active") != "active":
        return None, "err_not_active"
    if not _open_requests(load("requests"), "replace", member["policy_no"], member_id=member["id"]).empty:
        return None, "err_open_exists"
    snap = {**_snapshot(member), "reason": reason}
    rec = create_request("replace", member["policy_no"], member["name"], snap, user, member_id=member["id"],
                         staff_no=str_id(member["staff_no"]), effective_date=date.today(),
                         details=details or reason)
    return rec, None


def create_upgrade_request(member, new_category, user, details=None):
    if (nn(member["status"]) or "active") != "active":
        return None, "err_not_active"
    new_category = norm_category(new_category)
    if not new_category or new_category == norm_category(member.get("category")):
        return None, "err_same_cat"
    if not _open_requests(load("requests"), "upgrade", member["policy_no"], member_id=member["id"]).empty:
        return None, "err_open_exists"
    snap = {**_snapshot(member), "old_category": norm_category(member.get("category")), "new_category": new_category}
    rec = create_request("upgrade", member["policy_no"], member["name"], snap, user, member_id=member["id"],
                         staff_no=str_id(member["staff_no"]), effective_date=date.today(), details=details)
    return rec, None


def _payload(req):
    p = req.get("payload")
    return p if isinstance(p, dict) else {}


def _apply_done(req):
    """الأثر على الأعضاء لما الطلب يوصل 'تم التنفيذ' (آمن لو اتنفذ أكتر من مرة)."""
    p, pol = _payload(req), req["policy_no"]
    if req["type"] == "add":
        fields = {k: p.get(k) for k in MEMBER_FIELDS if nn(p.get(k)) is not None}
        fields["name"] = nn(p.get("name")) or req["member_name"]
        ex = find_member(pol, fields.get("staff_no"), fields["name"])
        if ex is not None:
            update("members", ex["id"], {**fields, "status": "active", "termination_date": None})
        else:
            insert("members", {**fields, "policy_no": pol, "status": "active"})
    elif req["type"] == "delete":
        ex = None
        if nn(req.get("member_id")):
            m = load("members")
            hit = m[m["id"] == req["member_id"]]
            ex = hit.iloc[0] if not hit.empty else None
        if ex is None:
            ex = find_member(pol, req.get("staff_no"), req["member_name"])
        if ex is not None:
            update("members", ex["id"], {"status": "terminated",
                                         "termination_date": to_iso(req.get("effective_date")) or date.today().isoformat()})
    elif req["type"] == "upgrade":
        ex = None
        if nn(req.get("member_id")):
            m = load("members")
            hit = m[m["id"] == req["member_id"]]
            ex = hit.iloc[0] if not hit.empty else None
        if ex is None:
            ex = find_member(pol, req.get("staff_no"), req["member_name"])
        if ex is not None and norm_category(p.get("new_category")):
            update("members", ex["id"], {"category": norm_category(p.get("new_category"))})


def change_status(rid, new, user):
    df = load("requests")
    hit = df[df["id"] == rid]
    if hit.empty:
        raise ValueError("request not found")
    req = hit.iloc[0].to_dict()
    old = req["status"]
    if new not in TRANSITIONS.get(old, []):
        raise ValueError("transition")
    if new == "done":
        _apply_done(req)
    update("requests", rid, {"status": new, "updated_at": now_iso()})
    notify("status_changed", msg_status(req, old, new, user))
    audit("status_changed", "request", req.get("ref_no"), f"{old} -> {new} | {req.get('member_name')}")


# ───────────────────────── ملفات الإضافة/الحذف ─────────────────────────
def export_df(rtype, reqs):
    rows = []
    for r in reqs.to_dict("records"):
        p = _payload(r)
        if rtype == "add":
            rows.append({"Name": r["member_name"], "National ID": p.get("national_id"), "DOB": fmt_date(p.get("dob")),
                         "Phone": p.get("phone"), "Staff ID": p.get("staff_no"), "Date": fmt_date(r["effective_date"]),
                         "Policy": r["policy_no"]})
        elif rtype == "delete":
            rows.append({"Name": r["member_name"], "Staff ID": p.get("staff_no"), "Card No": p.get("card_no"),
                         "National ID": p.get("national_id"), "DOB": fmt_date(p.get("dob")), "Policy": r["policy_no"],
                         "Deletion Date": fmt_date(r["effective_date"])})
        elif rtype == "upgrade":
            rows.append({"Name": r["member_name"], "Staff ID": p.get("staff_no"), "Card No": p.get("card_no"),
                         "National ID": p.get("national_id"), "Policy": r["policy_no"],
                         "Old Tier": p.get("old_category"), "New Tier": p.get("new_category"),
                         "Date": fmt_date(r["effective_date"])})
        else:
            rows.append({"Name": r["member_name"], "Staff ID": p.get("staff_no"), "Card No": p.get("card_no"),
                         "Policy": r["policy_no"], "Reason": p.get("reason"), "Date": fmt_date(r["effective_date"])})
    return pd.DataFrame(rows)


def to_excel_bytes(df):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        df.to_excel(w, index=False)
    return out.getvalue()


def export_all_requests(reqs):
    return pd.DataFrame({"Ref": reqs["ref_no"], "Type": reqs["type"], "Member": reqs["member_name"],
                         "Staff ID": reqs["staff_no"], "Policy": reqs["policy_no"],
                         "Effective": reqs["effective_date"].map(fmt_date), "Status": reqs["status"],
                         "Created": reqs["created_at"].map(fmt_ts), "By": reqs["created_by"]})


def to_excel_sheets(sheets):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for name, df in sheets.items():
            (df if len(df.columns) else pd.DataFrame({"": []})).to_excel(w, sheet_name=name[:31], index=False)
    return out.getvalue()


def parse_allianz_file(file):
    """يقرا شيت Allianz سواء HTML بامتداد xls أو XLSX أو CSV. يرجّع (DataFrame، رسالة خطأ)."""
    content = file.getvalue() if hasattr(file, "getvalue") else file.read()
    name = (getattr(file, "name", "") or "").lower()
    if name.endswith(".csv"):
        try:
            return pd.read_csv(io.BytesIO(content), dtype=str), None
        except Exception:  # noqa: BLE001
            pass
    try:
        text = content.decode("utf-8", errors="ignore")
        if "<table" in text.lower():
            dfs = pd.read_html(io.StringIO(text), converters=defaultdict(lambda: str))
            if dfs:
                df = dfs[0]
                if len(df) and df.iloc[0].astype(str).str.contains("Employee", case=False, na=False).any():
                    df.columns = df.iloc[0]
                    df = df[1:]
                return df.reset_index(drop=True).dropna(how="all"), None
    except Exception:  # noqa: BLE001
        pass
    last = None
    for engine in ("xlrd", "openpyxl", None):
        try:
            kw = {"engine": engine} if engine else {}
            return pd.read_excel(io.BytesIO(content), dtype=str, **kw).dropna(how="all"), None
        except Exception as e:  # noqa: BLE001
            last = e
    return pd.DataFrame(), str(last)



# ───────────────────────── الموافقات الطبية ─────────────────────────
APPROVAL_TYPES = ["hospital", "lab", "pharmacy", "surgery", "checkup"]
APPROVAL_STATUSES = ["pending", "approved", "rejected"]
AP_TYPE_AR = {"hospital": "دخول مستشفى", "lab": "تحاليل / أشعة", "pharmacy": "صيدلية", "surgery": "عملية جراحية",
              "checkup": "كشف"}
AP_STATUS_AR = {"pending": "معلّقة", "approved": "موافق عليها", "rejected": "مرفوضة"}


def next_approval_ref():
    prefix = f"AP-{datetime.now(CAIRO).year}-"
    nums = [int(x[len(prefix):]) for x in load("approvals")["ref_no"].dropna().astype(str)
            if x.startswith(prefix) and x[len(prefix):].isdigit()]
    return f"{prefix}{(max(nums) if nums else 0) + 1:04d}"


def create_approval(member, ap_type, provider, hospital, amount, details, user):
    if (nn(member["status"]) or "active") != "active":
        return None, "err_not_active"
    rec = insert("approvals", {
        "ref_no": next_approval_ref(), "member_id": member["id"], "member_name": member["name"],
        "staff_no": str_id(member["staff_no"]), "policy_no": member["policy_no"], "approval_type": ap_type,
        "provider": provider, "hospital": nn(hospital), "amount": float(amount or 0), "details": nn(details),
        "status": "pending", "created_by": user or None})
    pol, school = _ctx({"policy_no": member["policy_no"]})
    notify("approval_created", "\n".join([
        f"🏥 طلب موافقة جديد ({AP_TYPE_AR[ap_type]})", f"المرجع: {rec['ref_no']}", f"العضو: {member['name']}",
        f"الجهة: {nn(hospital) or '—'} | شركة التأمين: {provider}", f"المبلغ التقديري: {float(amount or 0):,.0f}",
        f"الوثيقة: {pol}{school}", f"بواسطة: {user or '—'}", f"الوقت: {_t()}"]))
    audit("approval_created", "approval", rec["ref_no"],
          f"{ap_type} | {member['name']} | {float(amount or 0):,.0f}", actor=user or None)
    return rec, None


def decide_approval(aid, new, user):
    df = load("approvals")
    hit = df[df["id"] == aid]
    if hit.empty:
        raise ValueError("approval not found")
    ap = hit.iloc[0].to_dict()
    if ap["status"] != "pending" or new not in ("approved", "rejected"):
        raise ValueError("transition")
    update("approvals", aid, {"status": new, "decided_by": user or None, "updated_at": now_iso()})
    pol, school = _ctx(ap)
    icon = "✅" if new == "approved" else "❌"
    notify("approval_decided", "\n".join([
        f"{icon} الموافقة {ap['ref_no']} اتغيرت حالتها", f"الحالة: {AP_STATUS_AR[new]}", f"العضو: {ap['member_name']}",
        f"المبلغ التقديري: {float(nn(ap.get('amount')) or 0):,.0f}", f"الوثيقة: {pol}{school}",
        f"بواسطة: {user or '—'}", f"الوقت: {_t()}"]))
    audit("approval_decided", "approval", ap["ref_no"], f"{ap['status']} -> {new} | {ap['member_name']}")


MAX_EMP_PENDING = 5


def employee_submit_approval(member, ap_type, hospital, amount, details):
    """طلب موافقة بيقدّمه الموظف نفسه. يرجّع (الطلب، None) أو (None، مفتاح الخطأ)."""
    if ap_type not in APPROVAL_TYPES:
        return None, "err_transition"
    a = pd.DataFrame(load("approvals"))
    pend = a[(a["member_id"] == member["id"]) & (a["status"] == "pending")]
    if len(pend) >= MAX_EMP_PENDING:
        return None, "err_too_many"
    amount = min(max(float(amount or 0), 0.0), 10_000_000.0)
    return create_approval(member, ap_type, "Allianz", (nn(hospital) or "")[:120] or None, amount,
                           (nn(details) or "")[:300] or None, f"{member['name']} · employee")


# ───────────────────────── دخول الموظف (رقم قومي + كود من الـ HR) ─────────────────────────
_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # من غير O/0/I/1 عشان ما يتلخبطوش


def _hash_code(code, salt):
    return hashlib.pbkdf2_hmac("sha256", str(code).strip().upper().encode(), salt, 120_000).hex()


def set_portal_code(member_id, label=None):
    """يولّد كود جديد للعضو ويخزّن الهاش بس. الكود الأصلي بيتعرض مرة واحدة ومش بيتخزن."""
    code = "".join(secrets.choice(_CODE_CHARS) for _ in range(8))
    salt = secrets.token_bytes(16)
    update("members", member_id, {"portal_pw": f"{salt.hex()}${_hash_code(code, salt)}"})
    audit("portal_code", "member", str(member_id)[:8], label)
    return code


def verify_portal(national_id, code):
    """يرجّع سجل العضو (dict) لو الرقم القومي والكود صح والعضو نشط، وإلا None."""
    nid, code = str_id(national_id), str(code or "").strip()
    if not nid or not code:
        return None
    m = load("members")
    m = m[(m["national_id"].map(str_id) == nid) & (m["status"].fillna("active") == "active") & m["portal_pw"].notna()]
    found = None
    for r in m.to_dict("records"):
        salt_hex, _, h = str(r["portal_pw"]).partition("$")
        try:
            ok = hmac.compare_digest(_hash_code(code, bytes.fromhex(salt_hex)), h)
        except ValueError:
            ok = False
        if ok:
            found = r
    if m.empty:  # نفس زمن الرد سواء الرقم موجود أو لأ
        _hash_code(code, b"0" * 16)
    return found


# ───────────────────────── التنبيهات ─────────────────────────
def _age_days(series):
    ts = pd.to_datetime(series, utc=True, errors="coerce")
    return (pd.Timestamp.now(tz="UTC") - ts).dt.days


def alerts(members, reqs, appr, pols, stale_days=2, soon_days=30):
    out = {}
    o = reqs[reqs["status"].isin(OPEN_STATUSES)].copy()
    o["age"] = _age_days(o["updated_at"].where(o["updated_at"].notna(), o["created_at"]))
    out["stale_requests"] = o[o["age"] >= stale_days]
    a = appr[appr["status"] == "pending"].copy()
    a["age"] = _age_days(a["created_at"])
    out["stale_approvals"] = a[a["age"] >= stale_days]
    today, limit = date.today().isoformat(), (date.today() + timedelta(days=soon_days)).isoformat()
    ends = pols["end_date"].fillna("")
    out["policies_soon"] = pols[(ends >= today) & (ends <= limit) & (ends != "")]
    out["policies_expired"] = pols[(ends < today) & (ends != "")]
    act = members[members["status"].fillna("active") == "active"].copy()
    act["_end"] = act["source_end"].map(to_iso).fillna("")
    out["members_soon"] = act[(act["_end"] >= today) & (act["_end"] <= limit) & (act["_end"] != "")]
    return out
