import hmac
import html
import time
import traceback
from urllib.parse import quote
from datetime import date, timedelta

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Myshurance", page_icon="🛡", layout="wide", initial_sidebar_state="expanded")

from PIL import Image  # noqa: E402

import cards  # noqa: E402
import ocr  # noqa: E402
import store as S  # noqa: E402
from i18n import lang, t  # noqa: E402

TEAL_DARK, TEAL, TEAL_ACTIVE = "#07363B", "#0B4F55", "#226068"
SAND, CREAM, BORDER = "#E8C9A0", "#F6F1E8", "#E8DCC8"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PAYLOAD_LABELS = {"name": "c_name", "staff_no": "c_staff", "card_no": "c_card", "national_id": "f_nid",
                  "phone": "f_phone", "dob": "c_dob", "gender": "c_gender", "category": "c_cat",
                  "dependency": "c_dep", "source_start": "c_start", "source_end": "c_end", "reason": "f_reason",
                  "old_category": "c_oldcat", "new_category": "c_newcat"}


# ───────────────────────── أدوات واجهة ─────────────────────────
def inject_css():
    css = """
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
html, body, [class*="css"], .stApp, button, input, textarea, select { font-family: 'Cairo', sans-serif !important; }
.stApp { background: %CREAM%; %DIR% }
header[data-testid="stHeader"] { background: transparent; }
.block-container { padding-top: 1.5rem; max-width: 1250px; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, %TEAL%, %DARK%); %DIR% }
[data-testid="stSidebar"] * { color: #EAF1F0; }
[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.12); }
.brand { display:flex; align-items:center; gap:12px; padding: 6px 4px 2px 4px; }
.brand .logo { width:46px; height:46px; border-radius:14px; border:1.5px solid rgba(232,201,160,.5);
  background: rgba(255,255,255,.06); display:flex; align-items:center; justify-content:center;
  color:%SAND%; font-weight:800; font-style:italic; font-size:20px; }
.brand .name { font-size:24px; font-weight:800; color:#fff; line-height:1.1; }
.tagline { color:%SAND%; font-style:italic; font-size:14px; padding: 0 4px 10px 4px; opacity:.9 }
[data-testid="stSidebar"] [role="radiogroup"] { gap: 6px; }
[data-testid="stSidebar"] [role="radiogroup"] label { padding: 12px 14px; border-radius: 14px; width:100%; cursor:pointer; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background: %ACTIVE%; box-shadow: inset -4px 0 0 %SAND%; }
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child { display:none; }
[data-testid="stSidebar"] [role="radiogroup"] label p { font-size: 17px; font-weight:600; }
.hero { background: linear-gradient(135deg, %TEAL% 0%, %ACTIVE% 100%); color:#fff; border-radius: 26px; padding: 26px 30px; margin-bottom: 18px; }
.hero h1 { color:#fff; font-size: 32px; font-weight:800; margin:0 0 8px 0; }
.hero .pill { display:inline-block; background: rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.35); border-radius: 999px; padding: 8px 16px; font-size: 14px; }
.stat { background:#fff; border:1px solid %BORDER%; border-radius:20px; padding:14px 16px; }
.stat .n { font-size: 30px; font-weight:800; color:%TEAL%; line-height:1.1 }
.stat .l { font-size: 13px; color:#5b6f70 }
.stat.gold { border-color:%SAND%; background: #FBF4E8 }
.pcard { background:#fff; border:1px solid %BORDER%; border-radius:22px; padding:18px; margin-bottom:10px; }
.pcard .top { display:flex; justify-content:space-between; align-items:center; }
.pcard .no { font-weight:800; color:%TEAL%; font-size:18px; }
.pcard .school { font-weight:700; margin:8px 0 2px 0; font-size:17px; }
.pcard .box { background:#FBF4E8; border:1px solid %BORDER%; border-radius:14px; padding:10px 12px; margin:10px 0; font-size:14px; }
.pcard .counts { display:flex; gap:8px; } .pcard .counts div { flex:1; background:%CREAM%; border-radius:12px; padding:8px; text-align:center; font-size:13px; }
.pcard .counts b { display:block; font-size:20px; color:%TEAL%; }
.badge { display:inline-block; padding:3px 12px; border-radius:999px; font-size:12px; font-weight:700; }
.badge.ok { background:#DDF3E6; color:#1B6B3A; } .badge.bad { background:#F8DADA; color:#9A2A2A; }
h2, h3 { color: %TEAL% !important; font-weight:800 !important; }
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button { background: %TEAL%; color:#fff; border:0; border-radius: 12px; padding: .5rem 1.1rem; font-weight:700; }
.stButton > button:hover, .stFormSubmitButton > button:hover, .stDownloadButton > button:hover { background: %ACTIVE%; color:#fff; }
.stButton > button:disabled { background:#b9c7c8; color:#fff; }
[data-testid="stSidebar"] .stButton > button { background: transparent; border:1px solid rgba(255,255,255,.22); width:100%; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { background-color: %SAND%; }
[data-testid="stForm"] { background:#fff; border:1px solid %BORDER%; border-radius:20px; }
"""
    for k, v in {"%CREAM%": CREAM, "%TEAL%": TEAL, "%DARK%": TEAL_DARK, "%ACTIVE%": TEAL_ACTIVE, "%SAND%": SAND,
                 "%BORDER%": BORDER,
                 "%DIR%": "direction: rtl; text-align: right;" if lang() == "ar" else ""}.items():
        css = css.replace(k, v)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def table(df):
    st.dataframe(df, hide_index=True, width="stretch")


def stat(col, n, label, gold=False):
    col.markdown(f'<div class="stat {"gold" if gold else ""}"><div class="n">{n}</div><div class="l">{label}</div></div>',
                 unsafe_allow_html=True)


def flash(kind, msg):
    st.session_state["_flash"] = (kind, msg)


def show_flash():
    f = st.session_state.pop("_flash", None)
    if f:
        getattr(st, f[0])(f[1])


def user():
    return st.session_state.get("user_name", "")


def can_edit():
    return st.session_state.get("role") == "admin"


def policy_label(no):
    return f"{no} - {S.school_name(no)}"


def all_or(label_fn):
    return lambda x: t("all") if x == "*" else label_fn(x)


def member_table(df, reqs):
    df = df.reset_index(drop=True)
    delmap = {}
    if not reqs.empty:
        o = reqs[(reqs["type"] == "delete") & reqs["status"].isin(S.OPEN_STATUSES) & reqs["member_id"].notna()]
        delmap = dict(zip(o["member_id"], o["status"]))
    dash = lambda s: s.fillna("—")  # noqa: E731
    return pd.DataFrame({
        t("c_idx"): range(1, len(df) + 1),
        t("c_name"): df["name"], t("c_staff"): dash(df["staff_no"]), t("c_card"): dash(df["card_no"]),
        t("c_policy"): df["policy_no"], t("c_company"): df["policy_no"].map(lambda p: S.school_name(p) or "—"),
        t("c_cat"): dash(df["category"]), t("c_dep"): dash(df["dependency"]),
        t("c_dob"): df["dob"].map(S.fmt_date),
        t("c_gender"): df["gender"].map(lambda g: t("g_" + g) if g in ("M", "F") else "—"),
        t("c_start"): df["source_start"].map(S.fmt_date), t("c_end"): df["source_end"].map(S.fmt_date),
        t("c_mstatus"): df["status"].fillna("active").map(lambda s: t("ms_" + s)),
        t("c_delreq"): df["id"].map(lambda i: t("st_" + delmap[i]) if i in delmap else t("no_req")),
    })


def date_or_none(iso):
    iso = S.to_iso(iso)
    return date.fromisoformat(iso) if iso else None


# ───────────────────────── الدخول ─────────────────────────
AUTH_COOKIE = "ms_auth"


def remember(token):
    """يجهّز كوكي "تذكّرني" (بيتكتب في المتصفح في الـ run الجاي). من غير COOKIE_SECRET مبيحصلش حاجة."""
    st.session_state.pop("_no_auto", None)
    if token:
        st.session_state["_cookie_out"] = ("set", token)


def emit_cookie():
    act = st.session_state.pop("_cookie_out", None)
    if not act:
        return
    kind, tok = act
    val, age = (tok, S.SESSION_TTL) if kind == "set" else ("", 0)  # التوكن حروف آمنة فقط (base64url + hex)
    js = (f'<script>(function(){{var s="{AUTH_COOKIE}={val}; path=/; max-age={age}; SameSite=Lax";'
          f'if(location.protocol==="https:")s+="; Secure";document.cookie=s;}})();</script>')
    try:
        st.html(js, unsafe_allow_javascript=True)
    except TypeError:  # نسخة Streamlit أقدم
        import streamlit.components.v1 as components
        components.html(js, height=0)


def request_cookies():
    try:
        return dict(st.context.cookies)
    except Exception:  # noqa: BLE001
        return {}


def try_auto_login():
    """لو فيه كوكي دخول سليم (توقيع + لسه ما انتهاش + الباسورد/الكود ما اتغيرش) ندخّله من غير باسورد."""
    ss = st.session_state
    if "role" in ss or ss.get("_no_auto") or not S.secret_cookie():
        return
    d = S.read_session_token(request_cookies().get(AUTH_COOKIE))
    if not d:
        return
    if d["r"] in ("admin", "viewer"):
        pw = S.secret("ADMIN_PASSWORD" if d["r"] == "admin" else "VIEWER_PASSWORD")
        if pw and S.token_fp(pw) == d.get("f"):
            ss.role, ss.user_name = d["r"], d.get("n") or ""
        return
    m = S.load("members")
    hit = m[m["id"] == d.get("m")]
    if hit.empty:
        return
    r = hit.iloc[0]
    if (S.nn(r["status"]) or "active") == "active" and S.nn(r.get("portal_pw")) and S.token_fp(r["portal_pw"]) == d.get("f"):
        ss.role, ss.user_name, ss.member_id = "employee", r["name"], r["id"]


def login_screen():
    c = st.columns([1, 1.2, 1])[1]
    with c:
        st.markdown(f'<div class="hero" style="text-align:center"><h1>Myshurance</h1>'
                    f'<div class="pill">{t("tagline")}</div></div>', unsafe_allow_html=True)
        tab_staff, tab_emp = st.tabs([t("login_staff"), t("login_emp")])
        with tab_staff:
            pw = {"admin": S.secret("ADMIN_PASSWORD"), "viewer": S.secret("VIEWER_PASSWORD")}
            roles = [r for r, p in pw.items() if p]
            if not roles:
                st.error(t("no_secrets"))
            else:
                with st.form("login"):
                    role = st.selectbox(t("role"), roles, format_func=t)
                    name = st.text_input(t("user_name"))
                    typed = st.text_input(t("pw"), type="password")
                    if st.form_submit_button(t("login")):
                        if hmac.compare_digest(typed.encode(), pw[role].encode()):
                            S.audit("login", "session", None, role, actor=name.strip() or "—", role=role)
                            st.session_state.role, st.session_state.user_name = role, name.strip()
                            remember(S.make_session_token(role, name.strip(), None, S.token_fp(pw[role])))
                            st.rerun()
                        else:
                            S.audit("login_failed", "session", None, role, actor=name.strip() or "—", role=role)
                            st.error(t("bad_pw"))
        with tab_emp:
            ss = st.session_state
            if ss.get("emp_fail", 0) >= 5:
                st.error(t("emp_locked"))
            else:
                with st.form("emp_login"):
                    nid = st.text_input(t("f_nid"))
                    code = st.text_input(t("emp_code"), type="password")
                    if st.form_submit_button(t("login")):
                        m = S.verify_portal(nid, code)
                        if m:
                            S.audit("login", "session", None, "employee", actor=m["name"], role="employee")
                            ss.role, ss.user_name, ss.member_id, ss.emp_fail = "employee", m["name"], m["id"], 0
                            remember(S.make_session_token("employee", m["name"], m["id"], S.token_fp(m["portal_pw"])))
                            st.rerun()
                        else:
                            S.audit("login_failed", "session", None, f"employee nid ***{str(nid).strip()[-4:]}",
                                    actor="—", role="employee")
                            ss.emp_fail = ss.get("emp_fail", 0) + 1
                            time.sleep(1)
                            st.error(t("emp_bad"))
                st.caption(t("emp_hint"))


# ───────────────────────── الصفحات ─────────────────────────
def page_dash():
    members, reqs = S.load("members"), S.load("requests")
    members["status"] = members["status"].fillna("active")
    open_n = int(reqs["status"].isin(S.OPEN_STATUSES).sum())
    drafts = int((reqs["status"] == "draft").sum())
    st.markdown(f'<div class="hero"><h1>{t("welcome")}</h1><div class="pill">{t("welcome_sub")}</div></div>',
                unsafe_allow_html=True)
    c = st.columns(4)
    stat(c[0], int((members["status"] == "active").sum()), t("m_active"))
    stat(c[1], open_n, t("m_open"), gold=True)
    stat(c[2], int((reqs["status"] == "done").sum()), t("m_done"))
    stat(c[3], int((members["status"] == "terminated").sum()), t("m_term"))
    if drafts:
        st.info(t("drafts_alert").format(n=drafts))
    show_alerts(members, reqs)
    a, b = st.columns(2)
    with a:
        st.subheader(t("recent"))
        if reqs.empty:
            st.info(t("nothing"))
        else:
            r = reqs.head(8)
            table(pd.DataFrame({t("rq_ref"): r["ref_no"], t("rq_member"): r["member_name"],
                                t("rq_status"): r["status"].map(lambda s: t("st_" + s))}))
    with b:
        st.subheader(t("per_policy"))
        rows = []
        for no, school in S.clients().items():
            m = members[members["policy_no"].astype(str) == no]
            rows.append({t("c_policy"): no, t("c_company"): school, t("n_active"): int((m["status"] == "active").sum()),
                         t("n_term"): int((m["status"] == "terminated").sum())})
        table(pd.DataFrame(rows))


def schools_admin():
    schools, provs = S.school_list(), S.provider_list()
    names, NEW = [p["name"] for p in provs], "__new__"
    with st.expander(t("sc_add")):
        with st.form("sc_add_form", clear_on_submit=True):
            c = st.columns(2)
            name = c[0].text_input(t("sc_name"))
            no = c[1].text_input(t("c_policy"))
            choice = st.selectbox(t("sc_provider"), names + [NEW],
                                  format_func=lambda x: t("sc_new_provider") if x == NEW else x)
            c2 = st.columns(2)
            new_name = c2[0].text_input(t("sc_new_name"))
            email = c2[1].text_input(t("sc_email"))
            st.caption(t("sc_add_hint"))
            if st.form_submit_button(t("save")):
                try:
                    rec, e = S.add_school(name, no, new_name if choice == NEW else choice, email)
                except Exception as ex:  # noqa: BLE001
                    rec, e = None, None
                    st.error(t("sc_fail").format(e=ex))
                if e:
                    st.error(t(e))
                elif rec:
                    flash("success", t("sc_added"))
                    st.rerun()
    with st.expander(t("sc_manage")):
        table(pd.DataFrame([{t("c_policy"): no, t("sc_name"): s_["name"], t("sc_provider"): s_["provider"] or "—",
                             t("sc_email"): S.provider_for(no)["email"] or "—",
                             t("sc_status"): t("sc_on") if s_["active"] else t("sc_off")} for no, s_ in schools.items()]))
        no = st.selectbox(t("c_policy"), list(schools), format_func=lambda n: f"{n} - {schools[n]['name']}", key="sc_pick")
        cur = schools[no]
        with st.form(f"sc_edit_{no}"):
            nm = st.text_input(t("sc_name"), value=cur["name"])
            pv = st.selectbox(t("sc_provider"), names, index=names.index(cur["provider"]) if cur["provider"] in names else 0)
            act = st.checkbox(t("sc_active"), value=cur["active"])
            if st.form_submit_button(t("save")):
                try:
                    e = S.update_school(no, nm, pv, act)
                except Exception as ex:  # noqa: BLE001
                    e = None
                    st.error(t("sc_fail").format(e=ex))
                if e:
                    st.error(t(e))
                else:
                    flash("success", t("saved"))
                    st.rerun()
        st.divider()
        st.subheader(t("sc_providers"))
        pl = [p for p in provs if p["id"]]
        if pl:
            pp = st.selectbox(t("sc_provider"), pl, format_func=lambda p: p["name"], key="sc_prov_pick")
            with st.form(f"sc_pemail_{pp['id']}"):
                em = st.text_input(t("sc_email"), value=pp["email"] or "")
                if st.form_submit_button(t("save")):
                    try:
                        e = S.set_provider_email(pp["id"], em)
                    except Exception as ex:  # noqa: BLE001
                        e = None
                        st.error(t("sc_fail").format(e=ex))
                    if e:
                        st.error(t(e))
                    else:
                        flash("success", t("saved"))
                        st.rerun()


def page_policies():
    st.header(t("policies"))
    if can_edit():
        schools_admin()
    pol, members, reqs = S.policies_df(), S.load("members"), S.load("requests")
    members["status"] = members["status"].fillna("active")
    cols = st.columns(2)
    for i, p in enumerate(pol.to_dict("records")):
        no = p["policy_no"]
        m = members[members["policy_no"].astype(str) == no]
        n_open = int(((reqs["policy_no"].astype(str) == no) & reqs["status"].isin(S.OPEN_STATUSES)).sum())
        expired = isinstance(p["end_date"], str) and p["end_date"] < date.today().isoformat()
        badge = f'<span class="badge {"bad" if expired else "ok"}">{t("pol_expired" if expired else "pol_active")}</span>'
        with cols[i % 2]:
            st.markdown(f"""<div class="pcard">
<div class="top"><span class="no">#{no}</span>{badge}</div>
<div class="school">{html.escape(p["school"] or "—")}</div>
<div style="font-size:13px;color:#5b6f70">{t("pol_provider")}: {html.escape(S.provider_for(no)["name"] or "—")}</div>
<div class="box">{t("pol_start")}: <b>{S.fmt_date(p["start_date"])}</b> &nbsp;|&nbsp; {t("pol_end")}: <b>{S.fmt_date(p["end_date"])}</b></div>
<div class="counts"><div><b>{int((m["status"] == "active").sum())}</b>{t("n_active")}</div>
<div><b>{int((m["status"] == "terminated").sum())}</b>{t("n_term")}</div>
<div><b>{n_open}</b>{t("pol_open")}</div></div></div>""", unsafe_allow_html=True)
            if can_edit():
                with st.expander(t("pol_edit")):
                    with st.form(f"pol_{no}"):
                        s = st.date_input(t("pol_start"), value=date_or_none(p["start_date"]) or date.today(),
                                          min_value=date(2020, 1, 1), max_value=date(2100, 1, 1), key=f"ps_{no}")
                        e = st.date_input(t("pol_end"), value=date_or_none(p["end_date"]) or date.today(),
                                          min_value=date(2020, 1, 1), max_value=date(2100, 1, 1), key=f"pe_{no}")
                        if st.form_submit_button(t("save")):
                            S.save_policy_dates(no, s, e)
                            S.notify_policy(no, s, e, user())
                            flash("success", t("saved"))
                            st.rerun()


def show_preview(file, caption):
    try:
        st.image(file, caption=caption, width="stretch")
    except Exception:  # noqa: BLE001
        st.warning(t("scan_img_fail"))


def add_member_tab():
    """إضافة عضو بالمسح الذكي: ارفع البطاقة (والكارنيه) ← قراءة ← راجع ← إنشاء الطلب."""
    st.caption(t("scan_privacy") if ocr.claude_available() else t("scan_no_ai"))
    ss = st.session_state
    ss.setdefault("up_ver", 0)
    ss.setdefault("scan_ver", 0)
    pol = st.selectbox(t("c_policy"), list(S.clients()), format_func=policy_label, key="add_pol")
    c1, c2 = st.columns(2)
    types = ["jpg", "jpeg", "png", "webp"]
    nid_file = c1.file_uploader(t("scan_nid"), type=types, key=f"up_nid_{ss.up_ver}")
    card_file = c2.file_uploader(t("scan_card"), type=types, key=f"up_card_{ss.up_ver}")
    if card_file and not nid_file:
        st.info(t("scan_need_nid"))
    if (nid_file or card_file) and st.button(t("scan_read"), key=f"scan_btn_{ss.up_ver}"):
        with st.spinner(t("scan_reading")):
            ss["add_scan"] = ocr.read_all(nid_file, card_file)
        ss["scan_ver"] += 1
        st.rerun()
    res = ss.get("add_scan")
    d = res["data"] if res else {}
    if res:
        if res["engine"] == "claude":
            st.success(t("scan_engine_claude"))
        elif res["engine"] == "tesseract":
            st.warning(t("scan_engine_ocr"))
        for w in res["warnings"]:
            st.warning(t(w))
        for e in res["errors"]:
            st.error(t("scan_error").format(e=e))
        if res["uncertain"]:
            st.warning(t("scan_uncertain").format(fields=", ".join(t(k) for k in res["uncertain"])))
        if not d:
            st.error(t("scan_nothing"))
    fv = ss.scan_ver
    left, right = st.columns([1, 1.6], gap="large")
    with left:  # صور المسح جنب البيانات عشان الموظف يطابقها بعينه
        if nid_file:
            show_preview(nid_file, t("scan_nid"))
        if card_file:
            show_preview(card_file, t("scan_card"))
        if not (nid_file or card_file):
            st.info(t("scan_upload_hint"))
    with right, st.form(f"add_member_{fv}"):
        r1 = st.columns(2)
        name = r1[0].text_input(t("c_name"), value=d.get("name", ""), key=f"a_name_{fv}")
        nid = r1[1].text_input(t("f_nid"), value=d.get("national_id", ""), key=f"a_nid_{fv}")
        r2 = st.columns(2)
        dob = r2[0].date_input(t("c_dob"), value=date_or_none(d.get("dob")), min_value=date(1930, 1, 1),
                               max_value=date.today(), key=f"a_dob_{fv}")
        gopts = ["", "M", "F"]
        gender = r2[1].selectbox(t("c_gender"), gopts, index=gopts.index(d.get("gender") or ""),
                                 format_func=lambda g: t("g_" + g) if g else "—", key=f"a_g_{fv}")
        r3 = st.columns(2)
        card = r3[0].text_input(t("c_card"), value=d.get("card_no", ""), key=f"a_card_{fv}")
        copts = ["", "A", "B", "C", "D"]
        categ = r3[1].selectbox(t("c_cat"), copts, index=copts.index(d.get("category") or ""),
                                format_func=lambda g: g or "—", key=f"a_cat_{fv}")
        r4 = st.columns(2)
        end = r4[0].date_input(t("c_end"), value=date_or_none(d.get("source_end")), min_value=date(2020, 1, 1),
                               max_value=date(2100, 1, 1), key=f"a_end_{fv}")
        dep = r4[1].selectbox(t("c_dep"), S.DEPENDENCIES, key=f"a_dep_{fv}")
        r5 = st.columns(3)
        staff = r5[0].text_input(t("c_staff"), key=f"a_staff_{fv}")
        phone = r5[1].text_input(t("f_phone"), key=f"a_phone_{fv}")
        eff = r5[2].date_input(t("f_eff"), value=date.today(), key=f"a_eff_{fv}")
        if st.form_submit_button(t("submit_add")):
            if not (staff.strip() and phone.strip() and categ):
                st.error(t("err_required"))
            else:
                rec, e = S.create_add_request(pol, {"name": name, "staff_no": staff, "national_id": nid,
                                                    "phone": phone, "card_no": card, "dob": dob, "gender": gender,
                                                    "category": categ, "source_end": end, "dependency": dep}, eff, user())
                if e:
                    st.error(t(e))
                else:
                    flash("success", t("ok_req").format(ref=rec["ref_no"]))
                    ss.pop("add_scan", None)
                    ss["up_ver"] += 1
                    ss["scan_ver"] += 1
                    st.rerun()


def page_members():
    st.header(t("members"))
    members, reqs = S.load("members"), S.load("requests")
    members["status"] = members["status"].fillna("active")
    f = st.columns([1.4, 1, 1, 1.4])
    policy = f[0].selectbox(t("flt_policy"), ["*"] + list(S.clients()), format_func=all_or(policy_label))
    cat = f[1].selectbox(t("flt_cat"), ["*", "A", "B", "C", "D"], format_func=all_or(str))
    stt = f[2].selectbox(t("flt_status"), ["*", "active", "terminated"], format_func=all_or(lambda s: t("ms_" + s)))
    q = f[3].text_input(t("search"))
    view = members
    if policy != "*":
        view = view[view["policy_no"].astype(str) == policy]
    if cat != "*":
        view = view[view["category"] == cat]
    if stt != "*":
        view = view[view["status"] == stt]
    if q:
        hay = view[["name", "staff_no", "card_no"]].fillna("").astype(str).agg(" ".join, axis=1)
        view = view[hay.str.contains(q, case=False, na=False, regex=False)]
    c = st.columns(6)
    stat(c[0], len(view), t("n_total"))
    stat(c[1], int((view["status"] == "active").sum()), t("n_active"))
    stat(c[2], int((view["status"] == "terminated").sum()), t("n_term"), gold=True)
    for col, k in zip(c[3:], "BCD"):
        stat(col, int((view["category"] == k).sum()), f"{t('f_tier')} {k}")
    shown = member_table(view, reqs)
    table(shown)
    st.download_button(t("export_view"), S.to_excel_bytes(shown), "members.xlsx", mime=XLSX)
    if not can_edit():
        st.caption(t("readonly"))
        return
    tab_add, tab_act, tab_card = st.tabs([t("tab_add"), t("tab_act"), t("tab_card")])
    with tab_add:
        add_member_tab()
    with tab_act:
        pool = view[view["status"] == "active"].head(300)
        if pool.empty:
            st.info(t("nothing"))
            return
        ids = pool["id"].tolist()
        lab = dict(zip(pool["id"], pool["name"].astype(str) + " | " + pool["staff_no"].fillna("—").astype(str)))
        mid = st.selectbox(t("choose_member"), ids, format_func=lab.get)
        m = pool[pool["id"] == mid].iloc[0]
        action = st.radio(t("action"), ["delete", "replace", "upgrade"], format_func=lambda a: t("act_" + a), horizontal=True)
        details = st.text_input(t("f_details"), key=f"det_{mid}_{action}")
        if action == "delete":
            eff = st.date_input(t("del_date"), value=date.today(), min_value=date.today() - timedelta(days=30),
                                max_value=date.today(), key=f"deld_{mid}")
            damaged = st.file_uploader(t("damaged_img"), type=["jpg", "jpeg", "png"], key=f"dmg_{mid}")
            ok = st.checkbox(t("confirm_ck"), key=f"cnf_{mid}")
            if st.button(t("submit_req"), disabled=not (damaged and ok), key=f"btn_del_{mid}"):
                rec, e = S.create_delete_request(m, eff, user(), details or None)
                if e:
                    st.error(t(e))
                else:
                    flash("success", t("ok_req").format(ref=rec["ref_no"]))
                    st.rerun()
        elif action == "replace":
            reason = st.selectbox(t("f_reason"), ["lost", "damaged"], format_func=lambda r: t("reason_" + r))
            if st.button(t("submit_req"), key=f"btn_rep_{mid}"):
                rec, e = S.create_replace_request(m, reason, user(), details or None)
                if e:
                    st.error(t(e))
                else:
                    flash("success", t("ok_req").format(ref=rec["ref_no"]))
                    st.rerun()


        else:
            cur_cat = S.norm_category(m["category"])
            st.caption(f"{t('c_oldcat')}: {cur_cat or '—'}")
            tiers = [k for k in "ABCD" if k != cur_cat]
            new_cat = st.selectbox(t("c_newcat"), tiers, key=f"upc_{mid}")
            if st.button(t("submit_req"), key=f"btn_upg_{mid}"):
                rec, e = S.create_upgrade_request(m, new_cat, user(), details or None)
                if e:
                    st.error(t(e))
                else:
                    flash("success", t("ok_req").format(ref=rec["ref_no"]))
                    st.rerun()
    with tab_card:
        member_card_tab(pool)


def member_card_tab(pool):
    if pool.empty:
        st.info(t("nothing"))
        return
    lab = dict(zip(pool["id"], pool["name"].astype(str) + " | " + pool["staff_no"].fillna("—").astype(str)))
    mid = st.selectbox(t("choose_member"), list(lab), format_func=lab.get, key="card_member")
    m = pool[pool["id"] == mid].iloc[0]
    st.download_button(t("card_dl"), card_bytes(m), f"card_{S.str_id(m['staff_no']) or mid}.pdf",
                       mime="application/pdf", key=f"dl_card_{mid}")
    st.divider()
    has_code = S.nn(m.get("portal_pw")) is not None
    st.caption(t("code_has") if has_code else t("code_none"))
    if not S.nn(m["national_id"]):
        st.warning(t("code_need_nid"))
    elif st.button(t("code_gen"), key=f"gen_{mid}"):
        try:
            st.session_state["_new_code"] = (mid, S.set_portal_code(mid, str(m["name"])))
        except Exception as e:  # noqa: BLE001
            st.error(t("code_fail").format(e=e))
    shown = st.session_state.get("_new_code")
    if shown and shown[0] == mid:
        st.success(t("code_show"))
        st.code(shown[1], language=None)


def card_bytes(m):
    pol = str(m["policy_no"])
    pols = S.policies_df()
    row = pols[pols["policy_no"] == pol]
    start, end = (row.iloc[0]["start_date"], row.iloc[0]["end_date"]) if not row.empty else (None, None)
    return cards.generate_card_pdf(m.to_dict() if hasattr(m, "to_dict") else m, S.school_name(pol), start, end)


def page_requests():
    st.header(t("requests"))
    reqs = S.load("requests")
    counts = reqs["status"].value_counts()
    sel = st.radio(t("flt_status"), ["*"] + S.REQ_STATUSES, horizontal=True, key="req_filter",
                   label_visibility="collapsed",
                   format_func=lambda s: f"{t('all') if s == '*' else t('st_' + s)} "
                                         f"({len(reqs) if s == '*' else int(counts.get(s, 0))})")
    f = st.columns(3)
    typ = f[0].selectbox(t("rq_type"), ["*"] + S.REQ_TYPES, format_func=all_or(lambda x: t("ty_" + x)))
    pol = f[1].selectbox(t("flt_policy"), ["*"] + list(S.clients()), format_func=all_or(policy_label))
    q = f[2].text_input(t("search"))
    v = reqs
    if sel != "*":
        v = v[v["status"] == sel]
    if typ != "*":
        v = v[v["type"] == typ]
    if pol != "*":
        v = v[v["policy_no"].astype(str) == pol]
    if q:
        hay = v[["ref_no", "member_name", "staff_no"]].fillna("").astype(str).agg(" ".join, axis=1)
        v = v[hay.str.contains(q, case=False, na=False, regex=False)]
    if v.empty:
        st.info(t("nothing"))
        return
    table(pd.DataFrame({
        t("rq_ref"): v["ref_no"], t("rq_type"): v["type"].map(lambda x: t("ty_" + x)), t("rq_member"): v["member_name"],
        t("rq_staff"): v["staff_no"].fillna("—"), t("rq_policy"): v["policy_no"],
        t("rq_date"): v["effective_date"].map(S.fmt_date), t("rq_status"): v["status"].map(lambda s: t("st_" + s)),
        t("rq_created"): v["created_at"].map(S.fmt_ts), t("rq_by"): v["created_by"].fillna("—")}))
    st.subheader(t("req_details"))
    lab = dict(zip(v["id"], v["ref_no"].astype(str) + " | " + v["member_name"].astype(str)))
    rid = st.selectbox(t("choose_req"), list(lab), format_func=lab.get)
    r = v[v["id"] == rid].iloc[0].to_dict()
    st.markdown(f"**{r['ref_no']}** — {t('ty_' + r['type'])} — {t('st_' + r['status'])}")
    p = r["payload"] if isinstance(r["payload"], dict) else {}
    shown = {t(PAYLOAD_LABELS[k]): (S.fmt_date(val) if k in ("dob", "source_start", "source_end") else
                                    (t("g_" + val) if k == "gender" else (t("reason_" + val) if k == "reason" else val)))
             for k, val in p.items() if k in PAYLOAD_LABELS and S.nn(val) is not None}
    if shown:
        table(pd.DataFrame([shown]))
    if S.nn(r.get("details")):
        st.caption(f"{t('f_details')}: {r['details']}")
    nxt = S.TRANSITIONS.get(r["status"], [])
    if not can_edit():
        st.caption(t("readonly"))
        return
    if not nxt:
        st.caption(t("no_actions"))
        return
    if "done" in nxt and r["type"] in ("add", "delete", "upgrade"):
        st.caption(t("done_note_" + r["type"]))
    cols = st.columns(len(nxt))
    for col, s in zip(cols, nxt):
        if col.button(f"{t('move_to')}: {t('st_' + s)}", key=f"to_{rid}_{s}"):
            try:
                S.change_status(rid, s, user())
                flash("success", t("status_changed"))
            except Exception as e:  # noqa: BLE001
                flash("error", f"{t('err_transition')} ({e})")
            st.rerun()


def page_import():
    st.header(t("import"))
    tab1, tab2 = st.tabs([t("tab_masters"), t("tab_files")])
    with tab1:
        pol = st.selectbox(t("c_policy"), list(S.clients()), format_func=policy_label, key="mp")
        members = S.load("members")
        cur = members[members["policy_no"].astype(str) == pol].copy()
        if not cur.empty:
            cur["status"] = cur["status"].fillna("active")
            st.download_button(t("imp_dl_master"), S.to_excel_bytes(member_table(cur, S.load("requests"))),
                               f"MASTER_{pol}_{date.today()}.xlsx", mime=XLSX)
        if not can_edit():
            st.caption(t("readonly"))
        else:
            up = st.file_uploader(t("imp_up"), type=["xlsx", "xls", "xlsm", "csv"], key="master_up")
            if up:
                df, err = S.parse_allianz_file(up)
                if err or df.empty:
                    st.error(f"{t('imp_fail')} {err or ''}")
                else:
                    det = S.detect_columns(df)
                    st.caption(t("imp_preview"))
                    table(df.head(8).astype(str))
                    st.subheader(t("imp_map"))
                    opts = [None] + list(df.columns)
                    mapping, cols = {}, st.columns(4)
                    for i, fld in enumerate(S.ALIASES):
                        mapping[fld] = cols[i % 4].selectbox(
                            t(PAYLOAD_LABELS[fld]), opts, index=opts.index(det[fld]) if fld in det else 0,
                            format_func=lambda c: t("imp_skip") if c is None else str(c), key=f"map_{fld}_{up.name}")
                    if not mapping["name"]:
                        st.error(t("err_need_name"))
                    else:
                        rows = S.rows_from_df(df, mapping)
                        keys = {r["staff_no"] for r in rows if r["staff_no"]}
                        absent = int((cur["staff_no"].map(S.str_id).map(lambda x: x not in keys)).sum()) if not cur.empty else 0
                        st.write(t("imp_count").format(n=len(rows)))
                        if absent:
                            st.info(t("imp_missing").format(n=absent))
                        if st.button(t("imp_go"), key="imp_go"):
                            new, upd, same = S.upsert_members(pol, rows)
                            if new or upd:
                                S.notify_import(pol, new, upd, same, user())
                            flash("success", t("imp_result").format(new=new, upd=upd, same=same))
                            st.rerun()
    with tab2:
        c = st.columns(2)
        pol = c[0].selectbox(t("c_policy"), list(S.clients()), format_func=policy_label, key="fp")
        rtype = c[1].radio(t("rq_type"), S.REQ_TYPES, format_func=lambda x: t("ty_" + x), horizontal=True, key="ft")
        reqs = S.load("requests")
        df = reqs[(reqs["type"] == rtype) & (reqs["policy_no"].astype(str) == pol) & (reqs["status"] == "draft")]
        if df.empty:
            st.info(t("files_none"))
            return
        lab = dict(zip(df["id"], df["ref_no"].astype(str) + " | " + df["member_name"].astype(str)))
        ids = st.multiselect(t("files_pick"), list(lab), default=list(lab), format_func=lab.get)
        sel = df[df["id"].isin(ids)]
        exp = S.export_df(rtype, sel)
        need = {"add": ["Employee No", "Category", "Start Date", "Date of Birth", "Gender"],
                "delete": ["Employee No", "Card Number", "End Date"]}.get(rtype)
        if need and not exp.empty:
            bad = exp[exp[need].isna().any(axis=1)]
            if not bad.empty:
                st.warning(t("files_missing").format(names=", ".join(bad["Employee Name"].astype(str))))
        table(exp)
        c1, c2 = st.columns(2)
        c1.download_button(t("files_dl"), S.to_excel_bytes(exp), f"{rtype.upper()}_{pol}_{date.today()}.xlsx",
                           mime=XLSX, disabled=sel.empty)
        if can_edit() and c2.button(t("files_mark_sent"), disabled=sel.empty):
            for i in ids:
                S.change_status(i, "sent", user())
            flash("success", t("files_marked").format(n=len(ids)))
            st.rerun()
        if not sel.empty:
            kind = {"add": "Addition", "delete": "Deletion", "replace": "Card replacement",
                    "upgrade": "Tier upgrade"}[rtype]
            school = S.school_name(pol)
            prov = S.provider_for(pol)
            subject = f"{kind} request - Policy {pol} - {school}"
            body = (f"Dear {prov['name'] or 'Insurance'} team,\n\nPlease find attached the {kind.lower()} file for policy "
                    f"{pol} ({school}) - {len(sel)} member(s).\nKindly process it and confirm once done.\n\n"
                    f"Best regards,\n{user()}")
            if not prov["email"]:
                st.warning(t("files_no_email").format(p=prov["name"] or "—"))
            if rtype in ("add", "delete") and (prov["name"] or "").casefold() != "allianz":
                st.info(t("files_format_note"))
            st.link_button(t("files_mail"), f"mailto:{prov['email']}?subject={quote(subject)}&body={quote(body)}")
            st.caption(t("files_mail_note"))
            with st.expander(t("files_mail_text")):
                st.code(f"To: {prov['email'] or '—'}\nSubject: {subject}\n\n{body}", language=None)


def page_settings():
    st.header(t("settings"))
    st.write("**Providers:** " + ", ".join(S.provider_names()))
    table(pd.DataFrame({t("c_policy"): list(S.clients()), t("c_company"): list(S.clients().values())}))
    if S.secret_cookie():
        st.success(t("remember_on"))
    else:
        st.warning(t("remember_off"))
    st.subheader(t("set_scan"))
    if ocr.claude_available():
        st.success(t("scan_ai_on"))
    else:
        st.warning(t("scan_no_ai"))
    st.subheader(t("set_notif"))
    if S.SB:
        st.success(t("sb_ok"))
    else:
        st.warning(t("sb_err").format(e=S.SB_ERR) if S.SB_ERR else t("notif_demo_warn"))
    n = S.load("notifications")
    c = st.columns(3)
    for col, s in zip(c, ["pending", "sent", "failed"]):
        stat(col, int((n["status"] == s).sum()), t("notif_" + s))
    if can_edit() and st.button(t("notif_test")):
        S.notify("test", f"✅ رسالة تجربة من Myshurance\nبواسطة: {user() or '—'}\nالوقت: {S._t()}")
        flash("success", t("notif_test_sent"))
        st.rerun()
    if not n.empty:
        table(pd.DataFrame({t("rq_created"): n.head(20)["created_at"].map(S.fmt_ts),
                            t("rq_status"): n.head(20)["status"],
                            "message": n.head(20)["message"].astype(str).str.split("\n").str[0]}))


def show_alerts(members, reqs):
    al = S.alerts(members, reqs, S.load("approvals"), S.policies_df())
    msgs = [(k, n) for k, n in (("al_stale_req", len(al["stale_requests"])), ("al_stale_ap", len(al["stale_approvals"])),
                                ("al_pol_exp", len(al["policies_expired"])), ("al_pol_soon", len(al["policies_soon"])),
                                ("al_mem_soon", len(al["members_soon"]))) if n]
    st.subheader(t("al_title"))
    if not msgs:
        st.success(t("al_none"))
        return
    for k, n in msgs:
        (st.error if k == "al_pol_exp" else st.warning)(t(k).format(n=n))
    if len(al["stale_requests"]):
        r = al["stale_requests"]
        with st.expander(t("al_stale_req").format(n=len(r))):
            table(pd.DataFrame({t("rq_ref"): r["ref_no"], t("rq_type"): r["type"].map(lambda x: t("ty_" + x)),
                                t("rq_member"): r["member_name"], t("rq_status"): r["status"].map(lambda x: t("st_" + x))}))
    if len(al["members_soon"]):
        mm = al["members_soon"]
        with st.expander(t("al_mem_soon").format(n=len(mm))):
            table(pd.DataFrame({t("c_name"): mm["name"], t("c_staff"): mm["staff_no"].fillna("—"),
                                t("c_policy"): mm["policy_no"], t("c_end"): mm["source_end"].map(S.fmt_date)}))


def approvals_table(v):
    return pd.DataFrame({
        t("rq_ref"): v["ref_no"], t("rq_member"): v["member_name"], t("rq_staff"): v["staff_no"].fillna("—"),
        t("rq_policy"): v["policy_no"], t("ap_type"): v["approval_type"].map(lambda x: t("apt_" + x) if x else "—"),
        t("pol_provider"): v["provider"].fillna("—"), t("ap_hospital"): v["hospital"].fillna("—"),
        t("ap_amount"): pd.to_numeric(v["amount"], errors="coerce").fillna(0),
        t("rq_status"): v["status"].map(lambda x: t("ast_" + x)), t("rq_created"): v["created_at"].map(S.fmt_ts),
        t("rq_by"): v["created_by"].fillna("—"), t("ap_decided_by"): v["decided_by"].fillna("—")})


def page_approvals():
    st.header(t("approvals"))
    appr, members = S.load("approvals"), S.load("members")
    members["status"] = members["status"].fillna("active")
    counts = appr["status"].value_counts()
    c = st.columns(3)
    for col, k in zip(c, S.APPROVAL_STATUSES):
        stat(col, int(counts.get(k, 0)), t("ast_" + k), gold=(k == "pending"))
    if can_edit():
        with st.expander(t("ap_new"), expanded=appr.empty):
            pool = members[members["status"] == "active"].head(500)
            if pool.empty:
                st.info(t("nothing"))
            else:
                lab = dict(zip(pool["id"], pool["name"].astype(str) + " | " + pool["staff_no"].fillna("—").astype(str)))
                with st.form("ap_form", clear_on_submit=True):
                    mid = st.selectbox(t("choose_member"), list(lab), format_func=lab.get)
                    r1 = st.columns(2)
                    typ = r1[0].selectbox(t("ap_type"), S.APPROVAL_TYPES, format_func=lambda x: t("apt_" + x))
                    hosp = r1[1].text_input(t("ap_hospital"))
                    amount = st.number_input(t("ap_amount"), min_value=0.0, step=100.0)
                    notes = st.text_input(t("f_details"))
                    if st.form_submit_button(t("ap_submit")):
                        mrow = pool[pool["id"] == mid].iloc[0]
                        rec, e = S.create_approval(mrow, typ, S.provider_for(mrow["policy_no"])["name"] or "Allianz",
                                                   hosp, amount, notes, user())
                        if e:
                            st.error(t(e))
                        else:
                            flash("success", t("ok_ap").format(ref=rec["ref_no"]))
                            st.rerun()
    sel = st.radio(t("flt_status"), ["*"] + S.APPROVAL_STATUSES, horizontal=True, key="ap_filter",
                   label_visibility="collapsed",
                   format_func=lambda s_: f"{t('all') if s_ == '*' else t('ast_' + s_)} "
                                          f"({len(appr) if s_ == '*' else int(counts.get(s_, 0))})")
    v = appr if sel == "*" else appr[appr["status"] == sel]
    if v.empty:
        st.info(t("nothing"))
        return
    table(approvals_table(v))
    if not can_edit():
        st.caption(t("readonly"))
        return
    pend = v[v["status"] == "pending"]
    if pend.empty:
        return
    lab = dict(zip(pend["id"], pend["ref_no"].astype(str) + " | " + pend["member_name"].astype(str)))
    aid = st.selectbox(t("choose_ap"), list(lab), format_func=lab.get)
    b = st.columns(2)
    for col, new, key in ((b[0], "approved", "ap_approve"), (b[1], "rejected", "ap_reject")):
        if col.button(t(key), key=f"{new}_{aid}", width="stretch"):
            try:
                S.decide_approval(aid, new, user())
                flash("success", t("ap_decided"))
            except Exception as e:  # noqa: BLE001
                flash("error", f"{t('err_transition')} ({e})")
            st.rerun()


def _local(series):
    return pd.to_datetime(series, utc=True, errors="coerce").dt.tz_convert(S.CAIRO)


def _in_month(df, ym):
    if df.empty or ym == "*":
        return df
    return df[_local(df["created_at"]).dt.strftime("%Y-%m") == ym]


def monthly_summary(reqs, appr, ym):
    r, a = _in_month(reqs, ym), _in_month(appr, ym)
    rows = [{"": t("ty_" + k), t("rp_created"): int((r["type"] == k).sum()),
             t("rp_done"): int(((r["type"] == k) & (r["status"] == "done")).sum())} for k in S.REQ_TYPES]
    amounts = pd.to_numeric(a["amount"], errors="coerce").fillna(0)
    ap = {k: int((a["status"] == k).sum()) for k in S.APPROVAL_STATUSES}
    total = float(amounts[a["status"] == "approved"].sum())
    return r, a, pd.DataFrame(rows), ap, total


def page_reports():
    st.header(t("reports"))
    members, reqs, appr, pols = S.load("members"), S.load("requests"), S.load("approvals"), S.policies_df()
    members["status"] = members["status"].fillna("active")
    labels = [t("rp_search"), t("rp_analytics"), t("rp_monthly"), t("rp_export")] + ([t("rp_audit")] if can_edit() else [])
    tabs = st.tabs(labels)
    t_search, t_an, t_month, t_exp = tabs[:4]

    with t_search:
        q = st.text_input(t("rp_search_ph"), key="rp_q")
        if q.strip():
            hay = members[["name", "staff_no", "card_no", "national_id"]].fillna("").astype(str).agg(" ".join, axis=1)
            hit = members[hay.str.contains(q.strip(), case=False, na=False, regex=False)].head(100)
            st.caption(t("rp_found").format(n=len(hit)))
            if not hit.empty:
                table(member_table(hit, reqs))
                lab = dict(zip(hit["id"], hit["name"].astype(str) + " | " + hit["staff_no"].fillna("—").astype(str)))
                mid = st.selectbox(t("rp_pick"), list(lab), format_func=lab.get, key="rp_member")
                st.subheader(t("rp_history"))
                mr, ma = reqs[reqs["member_id"] == mid], appr[appr["member_id"] == mid]
                if mr.empty and ma.empty:
                    st.info(t("nothing"))
                if not mr.empty:
                    table(pd.DataFrame({t("rq_ref"): mr["ref_no"], t("rq_type"): mr["type"].map(lambda x: t("ty_" + x)),
                                        t("rq_status"): mr["status"].map(lambda x: t("st_" + x)),
                                        t("rq_created"): mr["created_at"].map(S.fmt_ts)}))
                if not ma.empty:
                    table(approvals_table(ma))

    with t_an:
        act = members[members["status"] == "active"]
        charts = [("rp_by_tier", act["category"].fillna("—").value_counts()),
                  ("rp_by_dep", act["dependency"].fillna("—").value_counts()),
                  ("rp_req_type", reqs["type"].map(lambda x: t("ty_" + x)).value_counts() if not reqs.empty else None),
                  ("rp_req_status", reqs["status"].map(lambda x: t("st_" + x)).value_counts() if not reqs.empty else None),
                  ("rp_ap_status", appr["status"].map(lambda x: t("ast_" + x)).value_counts() if not appr.empty else None)]
        if not appr.empty:
            amt = appr.assign(_a=pd.to_numeric(appr["amount"], errors="coerce").fillna(0))
            charts += [("rp_ap_amount", amt.groupby(amt["status"].map(lambda x: t("ast_" + x)))["_a"].sum()),
                       ("rp_ap_provider", appr["provider"].fillna("—").value_counts())]
        cols = st.columns(2)
        shown = 0
        for key, data in charts:
            if data is None or data.empty:
                continue
            with cols[shown % 2]:
                st.subheader(t(key))
                st.bar_chart(data)
            shown += 1
        if not shown:
            st.info(t("nothing"))

    with t_month:
        months = {datetime_ym for df in (reqs, appr) if not df.empty
                  for datetime_ym in _local(df["created_at"]).dt.strftime("%Y-%m").dropna()}
        months.add(date.today().strftime("%Y-%m"))
        ym = st.selectbox(t("rp_month"), ["*"] + sorted(months, reverse=True),
                          format_func=lambda x: t("rp_all_time") if x == "*" else x)
        r, a, summary, ap, total = monthly_summary(reqs, appr, ym)
        c = st.columns(4)
        stat(c[0], len(r), t("requests"))
        stat(c[1], len(a), t("approvals"))
        stat(c[2], ap["approved"], t("ast_approved"))
        stat(c[3], f"{total:,.0f}", t("rp_approved_total"), gold=True)
        table(summary)
        lines = [f"Myshurance - {t('rp_monthly')} ({t('rp_all_time') if ym == '*' else ym})"]
        lines += [f"{row['']}: {row[t('rp_created')]} / {t('rp_done')} {row[t('rp_done')]}" for row in summary.to_dict("records")]
        lines += [f"{t('approvals')}: " + " | ".join(f"{t('ast_' + k)} {n}" for k, n in ap.items()),
                  f"{t('rp_approved_total')}: {total:,.0f}"]
        st.caption(t("rp_text"))
        st.code("\n".join(lines), language=None)
        xl = S.to_excel_sheets({"Summary": summary, "Requests": S.export_all_requests(r), "Approvals": approvals_table(a)})
        st.download_button(t("rp_dl_month"), xl, f"Myshurance_report_{'all' if ym == '*' else ym}.xlsx", mime=XLSX)

    with t_exp:
        what = st.selectbox(t("rp_export_what"), ["all", "members", "requests", "approvals", "policies"],
                            format_func=lambda k: t("rp_ex_" + k))
        sheets = {"Members": member_table(members, reqs), "Requests": S.export_all_requests(reqs),
                  "Approvals": approvals_table(appr), "Policies": pols}
        pick = sheets if what == "all" else {what.capitalize(): sheets[what.capitalize()]}
        st.download_button(t("rp_export"), S.to_excel_sheets(pick), f"Myshurance_{what}_{date.today()}.xlsx", mime=XLSX)

    if can_edit():
        with tabs[4]:
            audit_tab()


def audit_tab():
    log = S.load("audit_log")
    st.caption(t("au_note"))
    f = st.columns([1.4, 1.4, 1])
    acts = ["*"] + sorted(log["action"].dropna().unique().tolist())
    act = f[0].selectbox(t("au_action"), acts, format_func=lambda a: t("au_all") if a == "*" else t("aua_" + a))
    q = f[1].text_input(t("search"), key="au_q")
    lim = f[2].selectbox("#", [200, 500, 1000], key="au_lim")
    v = log if act == "*" else log[log["action"] == act]
    if q:
        hay = v[["actor", "ref", "details"]].fillna("").astype(str).agg(" ".join, axis=1)
        v = v[hay.str.contains(q, case=False, na=False, regex=False)]
    v = v.head(lim)
    if v.empty:
        st.info(t("nothing"))
        return
    shown = pd.DataFrame({t("au_time"): v["created_at"].map(S.fmt_ts), t("au_actor"): v["actor"].fillna("—"),
                          t("au_role"): v["role"].fillna("—"),
                          t("au_action"): v["action"].map(lambda a: t("aua_" + a) if a else "—"),
                          t("au_ref"): v["ref"].fillna("—"), t("au_details"): v["details"].fillna("—")})
    table(shown)
    st.download_button(t("rp_export"), S.to_excel_bytes(shown), f"audit_{date.today()}.xlsx", mime=XLSX)


def page_employee():
    members = S.load("members")
    hit = members[members["id"] == st.session_state.get("member_id")]
    if hit.empty:
        st.error(t("emp_missing"))
        return
    m = hit.iloc[0]
    pol = str(m["policy_no"])
    pols = S.policies_df()
    prow = pols[pols["policy_no"] == pol]
    st.markdown(f'<div class="hero"><h1>{html.escape(str(m["name"]))}</h1>'
                f'<div class="pill">{t("emp_title")}</div></div>', unsafe_allow_html=True)
    status = S.nn(m["status"]) or "active"
    c = st.columns(4)
    stat(c[0], S.nn(m["category"]) or "—", t("c_cat"))
    stat(c[1], S.nn(m["dependency"]) or "—", t("c_dep"))
    stat(c[2], t("ms_" + status), t("c_mstatus"), gold=True)
    stat(c[3], pol, S.school_name(pol))
    st.write("")
    info = {t("c_name"): m["name"], t("c_staff"): S.nn(m["staff_no"]) or "—", t("c_card"): S.nn(m["card_no"]) or "—",
            t("c_dob"): S.fmt_date(m["dob"]), t("c_gender"): t("g_" + m["gender"]) if m["gender"] in ("M", "F") else "—",
            t("pol_start"): S.fmt_date(prow.iloc[0]["start_date"]) if not prow.empty else "—",
            t("pol_end"): S.fmt_date(prow.iloc[0]["end_date"]) if not prow.empty else "—"}
    table(pd.DataFrame([info]))
    st.subheader(t("emp_card"))
    if status == "active":
        st.download_button(t("emp_dl_card"), card_bytes(m), f"card_{S.str_id(m['staff_no']) or 'member'}.pdf",
                           mime="application/pdf")
    else:
        st.info(t("emp_no_card"))
    reqs, appr = S.load("requests"), S.load("approvals")
    mr, ma = reqs[reqs["member_id"] == m["id"]], appr[appr["member_id"] == m["id"]]
    st.subheader(t("emp_my_req"))
    if mr.empty:
        st.info(t("nothing"))
    else:
        table(pd.DataFrame({t("rq_ref"): mr["ref_no"], t("rq_type"): mr["type"].map(lambda x: t("ty_" + x)),
                            t("rq_status"): mr["status"].map(lambda x: t("st_" + x)),
                            t("rq_created"): mr["created_at"].map(S.fmt_ts)}))
    if status == "active":
        with st.expander(t("emp_ap_new")):
            st.caption(t("emp_ap_hint"))
            with st.form("emp_ap_form", clear_on_submit=True):
                r1 = st.columns(2)
                typ = r1[0].selectbox(t("ap_type"), S.APPROVAL_TYPES, format_func=lambda x: t("apt_" + x))
                hosp = r1[1].text_input(t("ap_hospital"), max_chars=120)
                amount = st.number_input(t("ap_amount"), min_value=0.0, max_value=10_000_000.0, step=100.0)
                notes = st.text_input(t("f_details"), max_chars=300)
                if st.form_submit_button(t("emp_ap_submit")):
                    rec, e = S.employee_submit_approval(m.to_dict(), typ, hosp, amount, notes)
                    if e:
                        st.error(t(e))
                    else:
                        flash("success", t("emp_ap_sent").format(ref=rec["ref_no"]))
                        st.rerun()
    st.subheader(t("emp_my_ap"))
    if ma.empty:
        st.info(t("nothing"))
    else:
        table(approvals_table(ma)[[t("rq_ref"), t("ap_type"), t("pol_provider"), t("ap_hospital"), t("ap_amount"),
                                   t("rq_status"), t("rq_created")]])
    st.caption(t("emp_note"))


# ───────────────────────── التشغيل ─────────────────────────
def logout_button():
    if st.button(t("logout")):
        for k in ("role", "user_name", "member_id", "_new_code"):
            st.session_state.pop(k, None)
        st.session_state["_cookie_out"] = ("clear", None)
        st.session_state["_no_auto"] = True  # عشان الكوكي القديم ما يدخّلوش تاني قبل ما يتمسح
        st.rerun()


def run_page(runner):
    try:
        runner()
    except Exception as e:  # noqa: BLE001
        if e.__class__.__module__.startswith("streamlit.runtime.scriptrunner"):
            raise  # st.rerun / st.stop لازم يعدّوا
        st.error(t("page_error"))
        with st.expander(t("details")):
            st.code(traceback.format_exc())


def main():
    with st.sidebar:
        st.radio("lang", ["العربية", "English"], horizontal=True, key="lang_label", label_visibility="collapsed")
    inject_css()
    try_auto_login()
    emit_cookie()
    if "role" not in st.session_state:
        login_screen()
        return
    brand = ('<div class="brand"><div class="logo">sM</div><div class="name">Myshurance</div></div>'
             f'<div class="tagline">{t("tagline")}</div>')
    if st.session_state.role == "employee":  # بوابة الموظف: عرض بياناته بس، من غير أي صفحة إدارة
        with st.sidebar:
            st.markdown(brand, unsafe_allow_html=True)
            st.divider()
            logout_button()
            st.caption(f"{user() or '—'} · {t('employee')}")
        show_flash()
        run_page(page_employee)
        return
    try:
        open_n = int(S.load("requests")["status"].isin(S.OPEN_STATUSES).sum())
        pend_n = int((S.load("approvals")["status"] == "pending").sum())
    except Exception:  # noqa: BLE001
        open_n = pend_n = 0
    pages = ["dash", "members", "requests", "approvals", "policies", "import", "reports", "settings"]
    icons = {"dash": "▦", "members": "👥", "requests": "📋", "approvals": "🏥", "policies": "🛡️", "import": "📄",
             "reports": "📊", "settings": "⚙️"}
    badge = {"requests": open_n, "approvals": pend_n}
    with st.sidebar:
        st.markdown(brand, unsafe_allow_html=True)
        st.divider()
        page = st.radio("nav", pages, label_visibility="collapsed", key="page",
                        format_func=lambda k: f"{icons[k]}  {t(k)}" + (f"  ({badge[k]})" if badge.get(k) else ""))
        st.divider()
        logout_button()
        st.caption(f"{user() or '—'} · {t(st.session_state.role)}")
        if not S.SB:
            st.caption(t("demo"))
    show_flash()
    run_page({"dash": page_dash, "members": page_members, "requests": page_requests, "approvals": page_approvals,
              "policies": page_policies, "import": page_import, "reports": page_reports,
              "settings": page_settings}[page])


main()
