import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import jdatetime
import pytz
import urllib.parse
import urllib.request
import os
import io
import hashlib
import html
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm

# ایمپورت اسکنر حرفه‌ای (اختیاری)
try:
    from streamlit_qrcode_scanner import qrcode_scanner
    HAS_SCANNER_PKG = True
except ImportError:
    HAS_SCANNER_PKG = False

# ==========================================
# تنظیمات صفحه و استایل‌ها
# ==========================================
st.set_page_config(page_title="سیستم یکپارچه فروشگاه اسپرت", page_icon="🚗", layout="wide")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {background-color: transparent !important;}

    .stMarkdown, p, h1, h2, h3, h4, label, .stSelectbox, .stTextInput {
        direction: rtl; text-align: right; font-family: 'Tahoma', sans-serif !important;
    }
    [data-testid="stSidebar"] { direction: rtl; }
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
    .invoice-box { border: 2px dashed #4CAF50; padding: 20px; border-radius: 10px; background-color: #f9f9f9; color: #333; margin-top: 15px; direction: rtl; text-align: right; }
    .metric-box { padding: 15px; border-radius: 10px; background-color: #e8f5e9; border: 1px solid #4CAF50; margin-bottom: 20px; text-align: center; font-size: 20px; font-weight: bold; color: #2e7d32; }
    @media (max-width: 768px) { .block-container { padding-top: 2rem; padding-bottom: 2rem; } }
</style>
""", unsafe_allow_html=True)

# ==========================================
# لیست‌های پایه
# ==========================================
CAR_MODELS = [
    "عمومی (همه خودروها)", "پراید", "پژو ۲۰۶ / ۲۰۷", "پژو پارس / ۴۰۵",
    "سمند / سورن", "دنا / دنا پلاس", "کوئیک / ساینا", "شاهین / تارا", "ال ۹۰"
]
CATEGORIES = [
    "رینگ", "لاستیک", "فیلتر", "رادیاتور", "روغن و سیالات",
    "سیستم صوتی و مانیتور", "چراغ و هدلایت", "روکش و کفپوش",
    "دزدگیر و ردیاب", "تزئینات بدنه", "سایر"
]
EXPENSE_CATEGORIES = ["اجاره", "حقوق پرسنل", "قبوض", "خرید کالا", "سایر"]
PERSIAN_FONT_CANDIDATES = [
    "Vazirmatn.ttf", "Vazirmatn-Regular.ttf", "fonts/Vazirmatn.ttf",
    "assets/Vazirmatn.ttf", "Vazir.ttf", "IRANSans.ttf",
]

# ==========================================
# توابع کمکی
# ==========================================
def get_iran_time():
    return datetime.now(pytz.timezone('Asia/Tehran'))

def iran_naive():
    return get_iran_time().replace(tzinfo=None)

def jalali_str(dt=None):
    dt = dt or iran_naive()
    return jdatetime.datetime.fromgregorian(datetime=dt).strftime('%Y/%m/%d - %H:%M')

def jalali_date_str(dt=None):
    dt = dt or iran_naive()
    return jdatetime.datetime.fromgregorian(datetime=dt).strftime('%Y/%m/%d')

def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def get_admin_password():
    try: return st.secrets["admin_password"]
    except Exception: return "2613"

def get_telegram_secrets():
    try: return st.secrets.get("telegram_token", ""), st.secrets.get("telegram_chat_id", "")
    except Exception: return "", ""

def send_telegram_msg(token, chat_id, text_msg):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({'chat_id': chat_id, 'text': text_msg}).encode('utf-8')
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=5)
        return True
    except Exception:
        return False

def hash_password(raw_password):
    return hashlib.sha256(str(raw_password).encode("utf-8")).hexdigest()

def show_toman_hint(amount, color="#2e7d32", label="معادل"):
    st.markdown(
        f"<div style='margin-top:-15px; margin-bottom:10px; color:{color}; font-weight:bold; font-size:14px;'>"
        f"💳 {label}: {amount:,.0f} تومان</div>", unsafe_allow_html=True
    )

# ==========================================
# دیتابیس
# ==========================================
@st.cache_resource
def get_engine():
    try:
        if "supabase" in st.secrets and "db_url" in st.secrets["supabase"]:
            db_url = st.secrets["supabase"]["db_url"]
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
            engine_cloud = create_engine(db_url, pool_pre_ping=True)
            with engine_cloud.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine_cloud, "PostgreSQL (Supabase Cloud)"
    except Exception:
        pass
    return create_engine("sqlite:///inventory.db"), "SQLite (Local Offline)"

engine, db_type = get_engine()

def init_db():
    is_pg = 'postgresql' in engine.dialect.name
    id_type = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"

    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT,
                purchase_price REAL DEFAULT 0, sale_price REAL DEFAULT 0, stock INTEGER DEFAULT 0,
                compatible_cars TEXT DEFAULT 'عمومی', min_stock INTEGER DEFAULT 3
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS sales (
                id {id_type}, product_code TEXT, name TEXT, quantity INTEGER,
                sale_price REAL, sale_date TEXT, timestamp TIMESTAMP,
                customer_name TEXT DEFAULT '', customer_phone TEXT DEFAULT '', car_model TEXT DEFAULT '',
                install_fee REAL DEFAULT 0, net_profit REAL DEFAULT 0,
                staff_name TEXT DEFAULT 'ادمین (بدون پورسانت)', staff_commission REAL DEFAULT 0, discount REAL DEFAULT 0
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS ledger (
                id {id_type}, record_type TEXT, person_name TEXT, amount REAL,
                due_date TEXT, description TEXT, status TEXT DEFAULT 'معلق', timestamp TIMESTAMP,
                settled_at TIMESTAMP
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS expenses (
                id {id_type}, title TEXT, amount REAL, exp_date TEXT, timestamp TIMESTAMP,
                category TEXT DEFAULT 'سایر'
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS staff (
                id {id_type}, name TEXT UNIQUE, password TEXT DEFAULT '1234',
                commission_rate REAL DEFAULT 0, timestamp TIMESTAMP, active INTEGER DEFAULT 1
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS stock_adjustments (
                id {id_type}, product_code TEXT, change_qty INTEGER, reason TEXT,
                staff_name TEXT, timestamp TIMESTAMP
            )
        """))

    migrations = [
        "ALTER TABLE products ADD COLUMN min_stock INTEGER DEFAULT 3",
        "ALTER TABLE ledger ADD COLUMN settled_at TIMESTAMP",
        "ALTER TABLE expenses ADD COLUMN category TEXT DEFAULT 'سایر'",
        "ALTER TABLE staff ADD COLUMN active INTEGER DEFAULT 1",
    ]
    for sql in migrations:
        try:
            with engine.begin() as conn:
                conn.execute(text(sql))
        except Exception:
            pass  

init_db()

def get_setting(key, default=""):
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT value FROM settings WHERE key=:k"), {"k": key}).fetchone()
        return row[0] if row and row[0] is not None else default
    except Exception:
        return default

def set_setting(key, value):
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM settings WHERE key=:k"), {"k": key}).fetchone()
        if exists:
            conn.execute(text("UPDATE settings SET value=:v WHERE key=:k"), {"k": key, "v": value})
        else:
            conn.execute(text("INSERT INTO settings (key, value) VALUES (:k, :v)"), {"k": key, "v": value})

def build_full_backup():
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.read_sql_query("SELECT * FROM products", engine).to_excel(writer, index=False, sheet_name='انبار')
        pd.read_sql_query("SELECT * FROM sales", engine).to_excel(writer, index=False, sheet_name='فروش‌ها')
        pd.read_sql_query("SELECT * FROM ledger", engine).to_excel(writer, index=False, sheet_name='دفتر حساب')
        pd.read_sql_query("SELECT * FROM expenses", engine).to_excel(writer, index=False, sheet_name='هزینه‌ها')
        pd.read_sql_query("SELECT id, name, commission_rate, active FROM staff", engine).to_excel(writer, index=False, sheet_name='پرسنل')
        pd.read_sql_query("SELECT * FROM stock_adjustments", engine).to_excel(writer, index=False, sheet_name='اصلاح موجودی')
    return output.getvalue()

# ==========================================
# تولید فاکتور PDF 
# ==========================================
def register_persian_font():
    for path in PERSIAN_FONT_CANDIDATES:
        if os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont('Persian', path))
                return True
            except Exception:
                continue
    return False

def generate_pdf_invoice(inv, shop_name, shop_address, shop_phone, footer_text):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A5)
    width, height = A5

    has_font = register_persian_font()
    font_name = 'Persian' if has_font else 'Helvetica'
    bold_font = 'Persian' if has_font else 'Helvetica-Bold'

    def draw_rtl_text(text_str, x, y, font=None, size=10):
        c.setFont(font or font_name, size)
        if has_font:
            reshaped_text = arabic_reshaper.reshape(str(text_str))
            bidi_text = get_display(reshaped_text)
            c.drawRightString(x, y, bidi_text)
        else:
            c.drawRightString(x, y, str(text_str))

    draw_rtl_text(shop_name, width - 30, height - 40, font=bold_font, size=14)
    y_head = height - 58
    if shop_address:
        draw_rtl_text(shop_address, width - 30, y_head, size=9)
        y_head -= 16
    if shop_phone:
        draw_rtl_text(f"تلفن: {shop_phone}", width - 30, y_head, size=9)

    y = height - 95
    draw_rtl_text(f"تاریخ: {inv['date']}", width - 30, y)
    draw_rtl_text(f"مشتری: {inv['c_name']} | خودرو: {inv['c_car']}", width - 30, y - 20)
    draw_rtl_text(f"شماره تماس: {inv['c_phone']} | صندوق‌دار: {inv['staff']}", width - 30, y - 40)
    c.line(30, y - 55, width - 30, y - 55)

    y -= 75
    draw_rtl_text(f"شرح کالا / خدمات: {inv['p_name']}", width - 30, y)
    draw_rtl_text(f"تعداد: {inv['qty']} عدد", width - 30, y - 20)
    draw_rtl_text(f"قیمت واحد: {inv['price']:,.0f} تومان", width - 30, y - 40)
    draw_rtl_text(f"اجرت نصب: {inv['install']:,.0f} تومان", width - 30, y - 60)
    extra = 0
    if inv['discount'] > 0:
        draw_rtl_text(f"تخفیف: {inv['discount']:,.0f} تومان", width - 30, y - 80)
        extra = 20

    c.line(30, y - 75 - extra, width - 30, y - 75 - extra)
    draw_rtl_text(f"جمع کل پرداختی: {inv['total']:,.0f} تومان", width - 30, y - 100 - extra, font=bold_font, size=12)

    draw_rtl_text(footer_text or "از اعتماد و خرید شما سپاسگزاریم", width / 2 + 50, 30, size=9)

    c.save()
    buffer.seek(0)
    return buffer, has_font

def generate_thermal_pdf_invoice(inv, shop_name, shop_address, shop_phone, footer_text):
    page_width = 80 * mm
    page_height = 150 * mm
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_width, page_height))
    
    has_font = register_persian_font()
    font_name = 'Persian' if has_font else 'Helvetica'
    bold_font = 'Persian' if has_font else 'Helvetica-Bold'

    def draw_rtl_text(text_str, x, y, font=None, size=10, align="right"):
        c.setFont(font or font_name, size)
        if has_font:
            reshaped_text = arabic_reshaper.reshape(str(text_str))
            bidi_text = get_display(reshaped_text)
            if align == "center":
                c.drawCentredString(x, y, bidi_text)
            else:
                c.drawRightString(x, y, bidi_text)
        else:
            if align == "center":
                c.drawCentredString(x, y, str(text_str))
            else:
                c.drawRightString(x, y, str(text_str))

    center_x = page_width / 2
    right_x = page_width - 15

    draw_rtl_text(shop_name, center_x, page_height - 20, font=bold_font, size=12, align="center")
    y = page_height - 35
    if shop_phone:
        draw_rtl_text(f"تلفن: {shop_phone}", center_x, y, size=8, align="center")
        y -= 15

    c.setDash(2, 2)
    c.line(15, y, page_width - 15, y)
    c.setDash()
    y -= 15

    draw_rtl_text(f"تاریخ: {inv['date']}", right_x, y, size=8)
    y -= 12
    draw_rtl_text(f"مشتری: {inv['c_name']}", right_x, y, size=8)
    y -= 12
    draw_rtl_text(f"خودرو: {inv['c_car']}", right_x, y, size=8)
    y -= 15

    c.setDash(2, 2)
    c.line(15, y, page_width - 15, y)
    c.setDash()
    y -= 15

    draw_rtl_text(f"شرح: {inv['p_name']}", right_x, y, font=bold_font, size=9)
    y -= 14
    draw_rtl_text(f"تعداد: {inv['qty']} عدد x {inv['price']:,.0f}", right_x, y, size=9)
    y -= 12
    if inv['install'] > 0:
        draw_rtl_text(f"اجرت نصب: {inv['install']:,.0f}", right_x, y, size=9)
        y -= 12
    if inv['discount'] > 0:
        draw_rtl_text(f"تخفیف: {inv['discount']:,.0f}", right_x, y, size=9)
        y -= 12

    c.setDash(2, 2)
    c.line(15, y, page_width - 15, y)
    c.setDash()
    y -= 15

    draw_rtl_text(f"جمع کل: {inv['total']:,.0f} تومان", right_x, y, font=bold_font, size=11)
    y -= 25

    draw_rtl_text(footer_text or "از اعتماد شما سپاسگزاریم", center_x, y, size=8, align="center")

    c.save()
    buffer.seek(0)
    return buffer

# ==========================================
# مدیریت لاگین
# ==========================================
for key in ["user_role", "user_name", "last_invoice"]:
    if key not in st.session_state: st.session_state[key] = None
for key in ["scanned_add_code", "name_s", "phone_s", "car_s", "last_search_sale", "vip_search_sale_input"]:
    if key not in st.session_state: st.session_state[key] = ""
if "clear_sale_form" not in st.session_state: st.session_state.clear_sale_form = False

shop_name_display = get_setting("shop_name", "فروشگاه لوازم جانبی و اسپرت خودرو")
st.sidebar.title(f"🚗 {shop_name_display}")
st.sidebar.caption(f"📡 اتصال دیتابیس: {db_type}")

if st.session_state.user_role is None:
    st.sidebar.subheader("🔐 ورود به سیستم")
    login_type = st.sidebar.radio("ورود به عنوان:", ["شاگرد / پرسنل فروش", "صاحب مغازه (ادمین)"])

    if login_type == "صاحب مغازه (ادمین)":
        admin_pass = st.sidebar.text_input("رمز عبور ادمین:", type="password")
        if st.sidebar.button("ورود به پنل مدیریت"):
            if admin_pass == get_admin_password():
                st.session_state.user_role = "Admin"
                st.session_state.user_name = "ادمین"
                st.rerun()
            else:
                st.sidebar.error("رمز اشتباه است!")
    else:
        staff_df = pd.read_sql_query("SELECT name FROM staff WHERE active=1 ORDER BY name", engine)
        if not staff_df.empty:
            s_name = st.sidebar.selectbox("نام خود را انتخاب کنید:", staff_df['name'].tolist())
            s_pass = st.sidebar.text_input("رمز عبور خود را وارد کنید:", type="password")
            if st.sidebar.button("ورود به پنل فروش"):
                with engine.connect() as conn:
                    res = conn.execute(text("SELECT password FROM staff WHERE name=:n"), {"n": s_name}).fetchone()
                if res and (res[0] == hash_password(s_pass) or res[0] == s_pass):
                    if res[0] == s_pass:
                        with engine.begin() as conn:
                            conn.execute(text("UPDATE staff SET password=:p WHERE name=:n"), {"p": hash_password(s_pass), "n": s_name})
                    st.session_state.user_role = "Staff"
                    st.session_state.user_name = s_name
                    st.rerun()
                else:
                    st.sidebar.error("❌ رمز عبور اشتباه است!")
        else:
            st.sidebar.warning("هنوز هیچ شاگرد فعالی ثبت نشده است!")
    st.title("🛡️ به نرم‌افزار جامع فروشگاه خوش آمدید")
    st.info("👈 برای شروع کار، لطفاً از منوی سمت چپ وارد حساب کاربری خود شوید.")
    st.stop()

st.sidebar.success(f"👤 کاربر فعال: {st.session_state.user_name}")

if st.sidebar.button("خروج از سیستم"):
    st.session_state.user_role = None
    st.session_state.user_name = None
    st.rerun()

menu = (
    ["🛒 ثبت فروش / خدمات", "📦 مدیریت انبار", "➕ افزودن کالا", "📊 گزارش‌ها و داشبورد",
     "📒 دفتر حساب (چک‌ها)", "👥 مدیریت پرسنل", "⚙️ تنظیمات و پشتیبان‌گیری"]
    if st.session_state.user_role == "Admin"
    else ["🛒 ثبت فروش / خدمات", "📦 جستجو در انبار"]
)
choice = st.sidebar.radio("منوی اختصاصی شما:", menu)

# ==========================================
# 1. ثبت فروش، خدمات و مرجوعی
# ==========================================
if choice == "🛒 ثبت فروش / خدمات":
    st.header("🛒 ثبت فاکتور مشتری")

    staff_df_list = pd.read_sql_query("SELECT name FROM staff WHERE active=1 ORDER BY name", engine)
    vip_df = pd.read_sql_query("SELECT DISTINCT customer_name, customer_phone, car_model FROM sales WHERE customer_name != '' OR customer_phone != ''", engine)
    staff_options = ["ادمین (بدون پورسانت)"] + staff_df_list['name'].tolist()

    tab_sale, tab_service, tab_refund = st.tabs(["🛒 فروش قطعه و کالا", "🔧 ثبت خدمات (بدون کالا)", "🔄 مرجوعی کالا"])

    with tab_sale:
        col1, col2 = st.columns([1, 2])
        with col1:
            scan_method = st.radio("روش جستجو:", ("دوربین (اسکنر خودکار)", "کیبورد / بارکدخوان فیزیکی", "جستجوی نام کالا"))
            code_input = ""
            if scan_method == "کیبورد / بارکدخوان فیزیکی":
                code_input = st.text_input("کد کالا را وارد/اسکن کنید:")
            elif scan_method == "دوربین (اسکنر خودکار)":
                if HAS_SCANNER_PKG:
                    scanned_code = qrcode_scanner(key='pro_scanner_sale')
                    if scanned_code: code_input = scanned_code
                else:
                    st.warning("پکیج اسکنر نصب نیست.")
            elif scan_method == "جستجوی نام کالا":
                search_q = st.text_input("نام کالا یا ماشین:")
                if search_q:
                    like_q = f"%{search_q}%"
                    m_df = pd.read_sql_query(
                        text("SELECT code, name, compatible_cars FROM products WHERE name LIKE :q OR compatible_cars LIKE :q"),
                        engine, params={"q": like_q}
                    )
                    if not m_df.empty:
                        label_map = {f"{r['name']} (مناسب: {r['compatible_cars']}) - کد: {r['code']}": r['code'] for _, r in m_df.iterrows()}
                        picked_label = st.selectbox("انتخاب کالا:", list(label_map.keys()))
                        code_input = label_map[picked_label]
                    else:
                        st.info("کالایی یافت نشد.")

        with col2:
            if code_input:
                with engine.connect() as conn:
                    product = conn.execute(text("SELECT * FROM products WHERE code=:c"), {"c": code_input}).mappings().fetchone()

                if not product:
                    st.error("کالایی با این کد یافت نشد.")
                elif product['stock'] <= 0:
                    st.warning(f"⚠️ «{product['name']}» در حال حاضر در انبار موجود نیست.")
                else:
                    st.subheader(f"📦 {product['name']}")
                    st.markdown(f"**قیمت فروش:** {product['sale_price']:,.0f} تومان | **موجودی:** {product['stock']} عدد")

                    f_qty = st.number_input("تعداد", min_value=1, max_value=int(product['stock']))

                    f_install = st.number_input("اجرت نصب (تومان)", min_value=0, step=10000, value=0)
                    show_toman_hint(f_install)

                    max_discount = int((product['sale_price'] * f_qty) + f_install)
                    f_discount = st.number_input("مبلغ تخفیف (تومان)", min_value=0, max_value=max_discount, step=10000, value=0)
                    show_toman_hint(f_discount, color="#d32f2f", label="معادل تخفیف")

                    s_staff = st.selectbox("👷‍♂️ ثبت به نام:", staff_options) if st.session_state.user_role == "Admin" else st.session_state.user_name

                    st.markdown("🔍 **تکمیل اطلاعات مشتری**")
                    if st.session_state.get('clear_sale_form'):
                        st.session_state["name_s"] = ""; st.session_state["phone_s"] = ""
                        st.session_state.last_search_sale = ""; st.session_state["vip_search_sale_input"] = ""
                        st.session_state['clear_sale_form'] = False

                    vip_search_q = st.text_input("⌨️ نام یا موبایل مشتری قدیمی (جستجو):", key="vip_search_sale_input")
                    if vip_search_q and vip_search_q != st.session_state.last_search_sale:
                        st.session_state.last_search_sale = vip_search_q
                        if not vip_df.empty:
                            match = vip_df[
                                vip_df['customer_phone'].astype(str).str.contains(vip_search_q, case=False, na=False) |
                                vip_df['customer_name'].astype(str).str.contains(vip_search_q, case=False, na=False)
                            ]
                            if not match.empty:
                                st.session_state["name_s"] = str(match.iloc[0]['customer_name'])
                                st.session_state["phone_s"] = str(match.iloc[0]['customer_phone'])

                    cc1, cc2 = st.columns(2)
                    with cc1: c_name = st.text_input("نام مشتری", key="name_s")
                    with cc2: c_phone = st.text_input("موبایل", key="phone_s")

                    car_opt = st.selectbox("مدل ماشین", CAR_MODELS + ["سایر (تایپ دستی)"])
                    c_car = st.text_input("لطفاً نام خودرو را وارد کنید:") if car_opt == "سایر (تایپ دستی)" else car_opt

                    if st.button("✅ ثبت نهایی فاکتور کالا", use_container_width=True):
                        now_dt = iran_naive()
                        now_str = jalali_str(now_dt)
                        net_prof = ((product['sale_price'] - product['purchase_price']) * f_qty) + f_install - f_discount
                        total_bill = (product['sale_price'] * f_qty) + f_install - f_discount

                        try:
                            with engine.begin() as conn:
                                curr_stock = conn.execute(text("SELECT stock FROM products WHERE code=:c"), {"c": code_input}).scalar()
                                if curr_stock is None or curr_stock < f_qty:
                                    raise Exception("Insufficient_Stock")

                                conn.execute(text("UPDATE products SET stock = stock - :q WHERE code = :c"), {"q": f_qty, "c": code_input})
                                
                                staff_rate = 0
                                if s_staff != "ادمین (بدون پورسانت)":
                                    s_res = conn.execute(text("SELECT commission_rate FROM staff WHERE name=:n"), {"n": s_staff}).fetchone()
                                    if s_res: staff_rate = s_res[0]

                                conn.execute(text("""
                                    INSERT INTO sales (product_code, name, quantity, sale_price, sale_date, timestamp,
                                    customer_name, customer_phone, car_model, install_fee, net_profit, staff_name, staff_commission, discount)
                                    VALUES (:pc, :n, :q, :sp, :sd, :ts, :cn, :cp, :cm, :i, :np, :sn, :sc, :d)
                                """), {
                                    "pc": code_input, "n": product['name'], "q": f_qty, "sp": product['sale_price'], "sd": now_str,
                                    "ts": now_dt, "cn": c_name, "cp": c_phone, "cm": c_car,
                                    "i": f_install, "np": net_prof, "sn": s_staff,
                                    "sc": float(net_prof * (staff_rate / 100) if net_prof > 0 else 0), "d": f_discount
                                })

                            st.session_state.last_invoice = {
                                "date": now_str, "c_name": c_name or "نقدی", "c_phone": c_phone, "c_car": c_car,
                                "p_name": product['name'], "qty": f_qty, "price": product['sale_price'],
                                "install": f_install, "discount": f_discount, "total": total_bill, "staff": s_staff
                            }
                            st.session_state['clear_sale_form'] = True
                            st.success("فروش با موفقیت ثبت شد و از انبار کسر گردید!")
                            st.rerun()

                        except Exception as e:
                            if "Insufficient_Stock" in str(e):
                                st.error("موجودی کافی نیست! (احتمالاً هم‌زمان توسط شخص دیگری فروخته شده)")
                            else:
                                st.error(f"خطا در ثبت فروش: {e}")

    with tab_service:
        s_name = st.text_input("شرح خدمات (مثال: نصب سیستم صوتی)")

        s_fee = st.number_input("مبلغ اجرت (تومان)", min_value=0, step=50000)
        show_toman_hint(s_fee)

        s_staff_srv = st.selectbox("👷‍♂️ ثبت به نام نصاب:", staff_options, key="staff_srv") if st.session_state.user_role == "Admin" else st.session_state.user_name

        sc1, sc2 = st.columns(2)
        with sc1: s_cname = st.text_input("نام مشتری", key="name_srv_s")
        with sc2: s_cphone = st.text_input("شماره موبایل", key="phone_srv_s")

        car_opt_srv = st.selectbox("مدل خودرو", CAR_MODELS + ["سایر (تایپ دستی)"], key="car_srv_opt")
        s_ccar = st.text_input("لطفاً نام خودرو را وارد کنید:", key="car_srv_txt") if car_opt_srv == "سایر (تایپ دستی)" else car_opt_srv

        if st.button("🔧 ثبت خدمات", use_container_width=True):
            if s_name.strip() and s_fee > 0:
                now_dt = iran_naive()
                now_str = jalali_str(now_dt)

                try:
                    with engine.begin() as conn:
                        staff_rate = 0
                        if s_staff_srv != "ادمین (بدون پورسانت)":
                            s_res = conn.execute(text("SELECT commission_rate FROM staff WHERE name=:n"), {"n": s_staff_srv}).fetchone()
                            if s_res: staff_rate = s_res[0]

                        conn.execute(text("""
                            INSERT INTO sales (product_code, name, quantity, sale_price, sale_date, timestamp, customer_name, customer_phone, car_model, install_fee, net_profit, staff_name, staff_commission, discount)
                            VALUES ('SERVICE', :n, 0, 0, :sd, :ts, :cn, :cp, :cm, :i, :i, :sn, :sc, 0)
                        """), {"n": s_name.strip(), "sd": now_str, "ts": now_dt, "cn": s_cname, "cp": s_cphone, "cm": s_ccar,
                               "i": s_fee, "sn": s_staff_srv, "sc": s_fee * (staff_rate / 100.0)})

                    st.session_state.last_invoice = {
                        "date": now_str, "c_name": s_cname or "نقدی", "c_phone": s_cphone, "c_car": s_ccar,
                        "p_name": s_name.strip(), "qty": 0, "price": 0, "install": s_fee, "discount": 0,
                        "total": s_fee, "staff": s_staff_srv
                    }
                    st.success("خدمات ثبت شد!")
                    st.rerun()
                except Exception as e:
                    st.error(f"خطا: {e}")
            else:
                st.error("شرح و مبلغ الزامی است.")

    with tab_refund:
        if st.session_state.user_role == "Admin":
            st.markdown("ابتدا کالای مرجوعی را پیدا کنید:")
            ref_method = st.radio("روش جستجوی کالا برای مرجوعی:", ("دوربین (اسکنر خودکار)", "کیبورد / بارکدخوان فیزیکی", "جستجوی نام کالا"), key="ref_method")
            ref_code = ""

            if ref_method == "کیبورد / بارکدخوان فیزیکی":
                ref_code = st.text_input("کد کالا را وارد/اسکن کنید:", key="ref_barcode")
            elif ref_method == "دوربین (اسکنر خودکار)":
                if HAS_SCANNER_PKG:
                    scanned_ref = qrcode_scanner(key='ref_scanner')
                    if scanned_ref: ref_code = scanned_ref
                else:
                    st.warning("پکیج اسکنر نصب نیست.")
            elif ref_method == "جستجوی نام کالا":
                ref_q = st.text_input("نام کالا:", key="ref_name")
                if ref_q:
                    ref_df = pd.read_sql_query(
                        text("SELECT code, name FROM products WHERE name LIKE :q"),
                        engine, params={"q": f"%{ref_q}%"}
                    )
                    if not ref_df.empty:
                        label_map = {f"{r['name']} - کد: {r['code']}": r['code'] for _, r in ref_df.iterrows()}
                        picked_label = st.selectbox("انتخاب کالا:", list(label_map.keys()), key="ref_sel")
                        if picked_label:
                            ref_code = label_map[picked_label]
            
            if ref_code:
                st.markdown("---")
                st.markdown("**فاکتورهای اخیر ثبت‌شده برای این کالا:**")
                sales_of_product = pd.read_sql_query(
                    text("SELECT id, product_code, name, quantity, sale_date, customer_name, staff_name FROM sales WHERE product_code = :c ORDER BY id DESC LIMIT 20"),
                    engine, params={"c": ref_code}
                )
                if not sales_of_product.empty:
                    st.dataframe(sales_of_product.rename(columns={'id': 'کد', 'product_code': 'کد کالا', 'name': 'شرح', 'quantity': 'تعداد', 'sale_date': 'تاریخ', 'customer_name': 'مشتری', 'staff_name': 'پرسنل'}), hide_index=True, use_container_width=True)
                    
                    refund_id = st.number_input("کد ردیف فاکتور (کد) جهت ابطال را وارد کنید:", min_value=0, step=1)
                    confirm_refund = st.checkbox("تایید ابطال فاکتور و بازگشت به انبار")

                    if st.button("🗑️ ابطال فاکتور", disabled=not confirm_refund, type="primary") and refund_id > 0:
                        with engine.begin() as conn:
                            sale_rec = conn.execute(text("SELECT product_code, quantity FROM sales WHERE id=:i AND product_code=:c"), {"i": refund_id, "c": ref_code}).mappings().fetchone()
                            if sale_rec:
                                conn.execute(text("UPDATE products SET stock = stock + :q WHERE code=:c"), {"q": sale_rec['quantity'], "c": sale_rec['product_code']})
                                conn.execute(text("DELETE FROM sales WHERE id=:i"), {"i": refund_id})
                                st.success("فاکتور باطل شد و موجودی به انبار بازگشت.")
                                st.rerun()
                            else:
                                st.error("فاکتوری با این کد برای کالای انتخابی یافت نشد.")
                else:
                    st.info("فاکتوری برای این کالا یافت نشد.")
        else:
            st.error("فقط صاحب مغازه (ادمین) دسترسی دارد.")

    if st.session_state.last_invoice:
        inv = st.session_state.last_invoice
        st.markdown("---")
        st.subheader("🧾 فاکتور مشتری")

        shop_name = get_setting("shop_name", "فروشگاه لوازم جانبی و اسپرت خودرو")
        shop_address = get_setting("shop_address", "")
        shop_phone = get_setting("shop_phone", "")
        invoice_footer = get_setting("invoice_footer", "از اعتماد و خرید شما سپاسگزاریم")

        pdf_buffer, has_font = generate_pdf_invoice(inv, shop_name, shop_address, shop_phone, invoice_footer)
        thermal_buffer = generate_thermal_pdf_invoice(inv, shop_name, shop_address, shop_phone, invoice_footer)
        
        c_btn1, c_btn2 = st.columns(2)
        with c_btn1:
            st.download_button(label="📥 دانلود فاکتور A5", data=pdf_buffer,
                                file_name=f"Invoice_{inv['c_phone'] or 'cash'}_A5.pdf", mime="application/pdf",
                                type="primary", use_container_width=True)
        with c_btn2:
            st.download_button(label="🧾 چاپ فیش حرارتی (8cm)", data=thermal_buffer,
                                file_name=f"Invoice_{inv['c_phone'] or 'cash'}_Thermal.pdf", mime="application/pdf",
                                type="primary", use_container_width=True)

        dis_text = f"\n🎁 تخفیف اعمال شده: {inv['discount']:,} تومان" if inv['discount'] > 0 else ""
        inv_text = (f"🧾 {shop_name}\nتاریخ: {inv['date']}\n👤 مشتری: {inv['c_name']}\n🚗 خودرو: {inv['c_car']}\n"
                    f"👷‍♂️ مسئول: {inv['staff']}\n-------------------\n📦 شرح: {inv['p_name']}\n🔢 تعداد: {inv['qty']}\n"
                    f"💵 فی: {inv['price']:,} تومان\n🔧 اجرت: {inv['install']:,} تومان{dis_text}\n-------------------\n"
                    f"💰 جمع کل: {inv['total']:,} تومان\n✨ {invoice_footer} ✨")
        safe_inv_html = html.escape(inv_text).replace(chr(10), '<br>')
        st.markdown(f"<div class='invoice-box'>{safe_inv_html}</div>", unsafe_allow_html=True)
        enc = urllib.parse.quote(inv_text)
        w_link = f"https://wa.me/98{inv['c_phone'][1:]}?text={enc}" if inv['c_phone'].startswith('09') else f"https://wa.me/?text={enc}"
        t_link = f"https://t.me/share/url?url={enc}"
        b1, b2, b3 = st.columns(3)
        with b1: st.markdown(f"<a href='{w_link}' target='_blank'><button style='width:100%; padding:10px; background-color:#25D366; color:white; border:none;'>🟢 ارسال واتس‌اپ</button></a>", unsafe_allow_html=True)
        with b2: st.markdown(f"<a href='{t_link}' target='_blank'><button style='width:100%; padding:10px; background-color:#0088cc; color:white; border:none;'>🔵 ارسال تلگرام</button></a>", unsafe_allow_html=True)
        with b3:
            if st.button("بستن فاکتور", use_container_width=True):
                st.session_state.last_invoice = None
                st.rerun()

# ==========================================
# 2. مدیریت انبار
# ==========================================
elif choice == "📦 مدیریت انبار":
    st.header("📦 مدیریت انبار")
    tab_list, tab_adj = st.tabs(["📋 لیست، ویرایش و حذف", "⚖️ اصلاح موجودی (انبارگردانی)"])

    with tab_list:
        df = pd.read_sql_query("""SELECT code as 'کد', name as 'نام', category as 'دسته', compatible_cars as 'ماشین',
                                          purchase_price as 'خرید', sale_price as 'فروش', stock as 'موجودی', min_stock as 'حد هشدار'
                                   FROM products ORDER BY name""", engine)

        sc1, sc2 = st.columns([2, 1])
        with sc1: search = st.text_input("🔍 سرچ:", key="inv_search")
        with sc2: scan_chk = st.checkbox("فعال‌سازی اسکنر", key="inv_scan_chk")
        q_code = qrcode_scanner(key='inv_scan') if (scan_chk and HAS_SCANNER_PKG) else ""

        dsp_df = df.copy()
        if search:
            mask = dsp_df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
            dsp_df = dsp_df[mask]
        elif q_code:
            dsp_df = dsp_df[dsp_df['کد'] == q_code]

        if not dsp_df.empty:
            cat_opts = CATEGORIES + [c for c in dsp_df['دسته'].dropna().unique().tolist() if c not in CATEGORIES]
            car_opts = CAR_MODELS + [c for c in dsp_df['ماشین'].dropna().unique().tolist() if c not in CAR_MODELS]
            edit_df = dsp_df.copy()
            edit_df['حذف؟'] = False

            edited = st.data_editor(
                edit_df, hide_index=True, use_container_width=True, key="products_editor",
                column_config={
                    "کد": st.column_config.TextColumn(disabled=True),
                    "نام": st.column_config.TextColumn(required=True),
                    "دسته": st.column_config.SelectboxColumn(options=cat_opts),
                    "ماشین": st.column_config.SelectboxColumn(options=car_opts),
                    "خرید": st.column_config.NumberColumn(min_value=0, step=1000),
                    "فروش": st.column_config.NumberColumn(min_value=0, step=1000),
                    "موجودی": st.column_config.NumberColumn(min_value=0, step=1),
                    "حد هشدار": st.column_config.NumberColumn(min_value=0, step=1),
                    "حذف؟": st.column_config.CheckboxColumn(help="برای حذف کامل کالا تیک بزنید"),
                }
            )

            to_delete = edited[edited['حذف؟'] == True]['کد'].tolist()
            confirm_del = False
            if to_delete:
                confirm_del = st.checkbox(f"⚠️ تایید حذف {len(to_delete)} کالای علامت‌خورده (غیرقابل بازگشت)")

            if st.button("💾 ذخیره تغییرات", type="primary", use_container_width=True):
                to_update = edited[edited['حذف؟'] != True]
                with engine.begin() as conn:
                    for _, row in to_update.iterrows():
                        conn.execute(text("""UPDATE products SET name=:n, category=:cat, compatible_cars=:car,
                                              purchase_price=:pb, sale_price=:ps, stock=:st, min_stock=:ms
                                              WHERE code=:c"""),
                                     {"n": row['نام'], "cat": row['دسته'], "car": row['ماشین'],
                                      "pb": row['خرید'], "ps": row['فروش'], "st": row['موجودی'],
                                      "ms": row['حد هشدار'], "c": row['کد']})
                    if to_delete:
                        if confirm_del:
                            for code_del in to_delete:
                                conn.execute(text("DELETE FROM products WHERE code=:c"), {"c": code_del})
                        else:
                            st.warning("موارد علامت‌خورده برای حذف، به دلیل عدم تایید، حذف نشدند. سایر تغییرات ذخیره شد.")
                st.success("تغییرات ذخیره شد.")
                st.rerun()

            st.download_button(label="📥 دانلود لیست انبار (Excel)",
                                data=convert_df_to_excel(dsp_df),
                                file_name=f"Inventory_{iran_naive().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("کالایی یافت نشد.")

        low_df = df[df['موجودی'] < df['حد هشدار']]
        if not low_df.empty:
            st.error(f"⚠️ {len(low_df)} کالا موجودی کمتر از حد هشدار دارند:")
            st.dataframe(low_df, use_container_width=True, hide_index=True)
            st.download_button(label="🛒 دانلود لیست کسری‌ها", data=convert_df_to_excel(low_df),
                                file_name=f"Reorder_{iran_naive().strftime('%Y%m%d')}.xlsx")

    with tab_adj:
        st.subheader("⚖️ اصلاح دستی موجودی")
        st.caption("برای مواردی مثل انبارگردانی، کالای آسیب‌دیده یا اصلاح اشتباه ثبتی قبلی استفاده کنید.")
        
        has_products = False
        with engine.connect() as conn:
            if conn.execute(text("SELECT 1 FROM products LIMIT 1")).fetchone():
                has_products = True
                
        if not has_products:
            st.info("هنوز کالایی ثبت نشده است.")
        else:
            adj_method = st.radio("روش جستجو:", ("دوربین (اسکنر خودکار)", "کیبورد / بارکدخوان فیزیکی", "جستجوی نام کالا"), horizontal=True)
            picked_code = ""

            if adj_method == "کیبورد / بارکدخوان فیزیکی":
                picked_code = st.text_input("کد کالا را وارد/اسکن کنید:", key="adj_barcode_input")
            elif adj_method == "دوربین (اسکنر خودکار)":
                if HAS_SCANNER_PKG:
                    scanned_adj = qrcode_scanner(key='adj_scanner')
                    if scanned_adj:
                        picked_code = scanned_adj
                else:
                    st.warning("پکیج اسکنر نصب نیست.")
            elif adj_method == "جستجوی نام کالا":
                search_q = st.text_input("نام کالا یا ماشین:")
                if search_q:
                    like_q = f"%{search_q}%"
                    m_df = pd.read_sql_query(
                        text("SELECT code, name, stock, compatible_cars FROM products WHERE name LIKE :q OR compatible_cars LIKE :q"),
                        engine, params={"q": like_q}
                    )
                    if not m_df.empty:
                        label_map = {f"{r['name']} (مناسب: {r['compatible_cars']} | موجودی: {r['stock']}) - کد: {r['code']}": r['code'] for _, r in m_df.iterrows()}
                        picked_label = st.selectbox("انتخاب کالا:", list(label_map.keys()), key="adj_select_search")
                        if picked_label:
                            picked_code = label_map[picked_label]
                    else:
                        st.info("کالایی یافت نشد.")

            if picked_code:
                with engine.connect() as conn:
                    current_prod = conn.execute(text("SELECT code, name, stock FROM products WHERE code=:c"), {"c": picked_code}).mappings().fetchone()
                
                if not current_prod:
                    st.error("کالایی با این کد یافت نشد.")
                else:
                    current_stock = int(current_prod['stock'])
                    prod_name = current_prod['name']

                    st.markdown(f"**📦 کالای انتخاب‌شده:** {prod_name} | **موجودی فعلی:** {current_stock}")

                    adj_type = st.radio("نوع اصلاح:", ["➕ افزایش موجودی", "➖ کاهش موجودی"], horizontal=True)
                    adj_qty = st.number_input("تعداد", min_value=1, step=1)
                    adj_reason = st.text_input("دلیل اصلاح (مثال: کالای آسیب‌دیده، انبارگردانی)")

                    if st.button("✅ ثبت اصلاح موجودی", type="primary"):
                        signed = adj_qty if adj_type.startswith("➕") else -adj_qty
                        if current_stock + signed < 0:
                            st.error(f"موجودی کافی برای کاهش {adj_qty} عدد وجود ندارد (موجودی فعلی: {current_stock}).")
                        else:
                            with engine.begin() as conn:
                                conn.execute(text("UPDATE products SET stock = stock + :s WHERE code=:c"), {"s": signed, "c": picked_code})
                                conn.execute(text("""INSERT INTO stock_adjustments (product_code, change_qty, reason, staff_name, timestamp)
                                                      VALUES (:c, :q, :r, :sn, :ts)"""),
                                             {"c": picked_code, "q": signed, "r": adj_reason, "sn": st.session_state.user_name, "ts": iran_naive()})
                            st.success("موجودی اصلاح شد.")
                            st.rerun()

# ==========================================
# 2ب. جستجوی انبار (پرسنل فروش - فقط نمایش)
# ==========================================
elif choice == "📦 جستجو در انبار":
    st.header("📦 جستجو در انبار")
    df = pd.read_sql_query("""SELECT code as 'کد', name as 'نام', category as 'دسته', compatible_cars as 'ماشین',
                                      sale_price as 'فروش', stock as 'موجودی' FROM products ORDER BY name""", engine)
    sc1, sc2 = st.columns([2, 1])
    with sc1: search = st.text_input("🔍 سرچ:")
    with sc2: scan_chk = st.checkbox("فعال‌سازی اسکنر")
    q_code = qrcode_scanner(key='inv_scan_staff') if (scan_chk and HAS_SCANNER_PKG) else ""

    dsp_df = df.copy()
    if search:
        mask = dsp_df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
        dsp_df = dsp_df[mask]
    elif q_code:
        dsp_df = dsp_df[dsp_df['کد'] == q_code]

    st.dataframe(dsp_df, use_container_width=True, hide_index=True)

# ==========================================
# 3. افزودن کالا (تکی و گروهی با اکسل)
# ==========================================
elif choice == "➕ افزودن کالا":
    st.header("➕ افزودن کالا")
    tab_manual, tab_bulk = st.tabs(["➕ ثبت تکی", "📂 ورود گروهی با اکسل"])

    with tab_manual:
        a_mode = st.radio("روش ورود کد:", ("دستی / تولید خودکار", "اسکن دوربین"))

        if a_mode == "اسکن دوربین" and HAS_SCANNER_PKG:
            scanned = qrcode_scanner(key='new_scan')
            if scanned: st.session_state.scanned_add_code = scanned

        val = st.session_state.scanned_add_code if a_mode == "اسکن دوربین" else ""
        code = st.text_input("کد کالا/بارکد (خالی بگذارید تا خودکار ساخته شود):", value=val)

        name = st.text_input("نام کالا:")

        cat_opt = st.selectbox("دسته‌بندی:", CATEGORIES + ["سایر (تایپ دستی)"])
        cat = st.text_input("لطفاً دسته‌بندی جدید را تایپ کنید:") if cat_opt == "سایر (تایپ دستی)" else cat_opt

        car_opt = st.selectbox("مناسب برای خودرو:", CAR_MODELS + ["سایر (تایپ دستی)"])
        car = st.text_input("لطفاً نام خودروی جدید را تایپ کنید:") if car_opt == "سایر (تایپ دستی)" else car_opt

        c1, c2 = st.columns(2)
        with c1:
            pb = st.number_input("قیمت خرید", min_value=0, step=10000)
            show_toman_hint(pb)
        with c2:
            ps = st.number_input("قیمت فروش", min_value=0, step=10000)
            show_toman_hint(ps)

        c3, c4 = st.columns(2)
        with c3: stock = st.number_input("موجودی", min_value=0)
        with c4: min_stock = st.number_input("حد هشدار موجودی", min_value=0, value=3)

        if st.button("ثبت کالا", type="primary"):
            if name.strip():
                fc = code.strip() or f"AUTO-{iran_naive().strftime('%Y%m%d%H%M%S%f')}"
                try:
                    with engine.begin() as conn:
                        conn.execute(text("""INSERT INTO products (code, name, category, purchase_price, sale_price, stock, compatible_cars, min_stock)
                                              VALUES (:c, :n, :cat, :pb, :ps, :st, :car, :ms)"""),
                                     {"c": fc, "n": name.strip(), "cat": cat, "pb": pb, "ps": ps, "st": stock, "car": car, "ms": min_stock})
                    st.session_state.scanned_add_code = ""
                    st.success("کالا ثبت شد!")
                    st.rerun()
                except IntegrityError:
                    st.error(f"کد «{fc}» تکراری است. کد دیگری وارد کنید یا آن را خالی بگذارید.")
                except Exception as e:
                    st.error(f"خطا در ثبت کالا: {e}")
            else:
                st.error("نام کالا الزامی است.")

    with tab_bulk:
        st.info("ابتدا فایل نمونه را دانلود کنید، پر کنید و آپلود نمایید.")
        sample_df = pd.DataFrame(columns=['کد کالا (اختیاری)', 'نام کالا', 'مناسب خودرو', 'دسته‌بندی', 'قیمت خرید', 'قیمت فروش', 'موجودی', 'حد هشدار موجودی'])
        st.download_button(label="📥 دانلود قالب اکسل", data=convert_df_to_excel(sample_df), file_name="Template_Products.xlsx")

        uploaded_file = st.file_uploader("📤 آپلود فایل اکسل تکمیل‌شده:", type=['xlsx'])
        if uploaded_file and st.button("🚀 پردازش فایل"):
            bulk_df = None
            try:
                bulk_df = pd.read_excel(uploaded_file)
            except Exception:
                st.error("فایل اکسل قابل خواندن نیست. لطفاً از فرمت xlsx استفاده کنید.")

            if bulk_df is not None:
                missing_cols = {'نام کالا'} - set(bulk_df.columns)
                if missing_cols:
                    st.error(f"ستون‌های الزامی زیر در فایل یافت نشد: {', '.join(missing_cols)}")
                else:
                    success_count, error_count, error_rows = 0, 0, []
                    with engine.begin() as conn:
                        for index, row in bulk_df.iterrows():
                            p_name = str(row.get('نام کالا', '')).strip()
                            if not p_name or p_name.lower() == 'nan':
                                continue
                            raw_code = str(row.get('کد کالا (اختیاری)', '')).strip()
                            fc = raw_code if raw_code and raw_code.lower() != 'nan' else f"AUTO-{iran_naive().strftime('%Y%m%d%H%M%S%f')}"
                            pc = str(row.get('مناسب خودرو', '')).strip()
                            pc = pc if pc and pc.lower() != 'nan' else "عمومی"
                            pcat = str(row.get('دسته‌بندی', '')).strip()
                            pcat = pcat if pcat and pcat.lower() != 'nan' else "سایر"
                            try:
                                pb = float(row.get('قیمت خرید', 0) or 0)
                                ps = float(row.get('قیمت فروش', 0) or 0)
                                pst = int(row.get('موجودی', 0) or 0)
                                pms = int(row.get('حد هشدار موجودی', 3) or 3)
                            except (ValueError, TypeError):
                                error_count += 1; error_rows.append(index + 2)
                                continue
                            try:
                                conn.execute(text("""INSERT INTO products (code, name, category, purchase_price, sale_price, stock, compatible_cars, min_stock)
                                                      VALUES (:c, :n, :cat, :pb, :ps, :st, :car, :ms)"""),
                                             {"c": fc, "n": p_name, "cat": pcat, "pb": pb, "ps": ps, "st": pst, "car": pc, "ms": pms})
                                success_count += 1
                            except Exception:
                                error_count += 1; error_rows.append(index + 2)
                    if success_count > 0: st.success(f"✅ {success_count} کالا اضافه شد.")
                    if error_count > 0: st.warning(f"⚠️ {error_count} ردیف ثبت نشد (کد تکراری یا داده نامعتبر) - شماره ردیف در اکسل: {error_rows}")

# ==========================================
# 4. داشبورد و گزارش‌ها 
# ==========================================
elif choice == "📊 گزارش‌ها و داشبورد":
    st.header("📊 داشبورد مدیریت مالی")

    iran_now = iran_naive()
    today_start = iran_now.replace(hour=0, minute=0, second=0, microsecond=0)
    jalali_now = jdatetime.datetime.fromgregorian(datetime=iran_now)
    month_start = jdatetime.datetime(jalali_now.year, jalali_now.month, 1).togregorian()

    time_filter = st.selectbox("📅 فیلتر بازه زمانی:", ["امروز", "۷ روز گذشته", "ماه شمسی جاری", "بازه دلخواه", "همه زمان‌ها"])

    end_dt = iran_now + timedelta(days=1)
    if time_filter == "امروز":
        start_dt = today_start
    elif time_filter == "۷ روز گذشته":
        start_dt = iran_now - timedelta(days=7)
    elif time_filter == "ماه شمسی جاری":
        start_dt = month_start
    elif time_filter == "بازه دلخواه":
        cc1, cc2 = st.columns(2)
        with cc1: from_str = st.text_input("از تاریخ (مثال: 1403/01/01)", value=jalali_date_str(iran_now - timedelta(days=30)))
        with cc2: to_str = st.text_input("تا تاریخ (مثال: 1403/06/10)", value=jalali_date_str(iran_now))
        try:
            start_dt = jdatetime.datetime.strptime(from_str.strip(), '%Y/%m/%d').togregorian()
            end_dt = jdatetime.datetime.strptime(to_str.strip(), '%Y/%m/%d').togregorian() + timedelta(days=1)
        except ValueError:
            st.error("فرمت تاریخ نامعتبر است.")
            start_dt = today_start
    else:
        start_dt = iran_now - timedelta(days=3650) 

    sales_df = pd.read_sql_query("SELECT * FROM sales", engine)
    exp_df = pd.read_sql_query("SELECT * FROM expenses", engine)

    if not sales_df.empty:
        sales_df['timestamp'] = pd.to_datetime(sales_df['timestamp'], errors='coerce')
        if sales_df['timestamp'].dt.tz is not None:
            sales_df['timestamp'] = sales_df['timestamp'].dt.tz_convert(None)
            
        sales_df = sales_df[(sales_df['timestamp'] >= start_dt) & (sales_df['timestamp'] <= end_dt)]
        
        for col in ['discount', 'install_fee', 'staff_commission', 'net_profit']:
            sales_df[col] = sales_df[col].fillna(0)
        sales_df['درآمد نهایی'] = (sales_df['quantity'] * sales_df['sale_price']) + sales_df['install_fee'] - sales_df['discount']

    if not exp_df.empty:
        exp_df['timestamp'] = pd.to_datetime(exp_df['timestamp'], errors='coerce')
        if exp_df['timestamp'].dt.tz is not None:
            exp_df['timestamp'] = exp_df['timestamp'].dt.tz_convert(None)
            
        exp_df = exp_df[(exp_df['timestamp'] >= start_dt) & (exp_df['timestamp'] <= end_dt)]
        if 'category' not in exp_df.columns:
            exp_df['category'] = 'سایر'
        exp_df['category'] = exp_df['category'].fillna('سایر')

    t_rep, t_chart, t_exp, t_staff = st.tabs(["📋 فروش", "📈 نمودار و پرفروش‌ترین‌ها", "💸 خرج‌کرد", "👥 پرسنل"])

    with t_rep:
        if not sales_df.empty:
            total_rev = sales_df['درآمد نهایی'].sum()
            total_exp = exp_df['amount'].sum() if not exp_df.empty else 0
            total_prof = sales_df['net_profit'].sum() - total_exp - sales_df['staff_commission'].sum()
            c1, c2 = st.columns(2)
            c1.metric("درآمد صندوق", f"{total_rev:,.0f} T")
            c2.metric("سود خالص صاحب مغازه", f"{total_prof:,.0f} T")
            st.dataframe(sales_df[['sale_date', 'name', 'staff_name', 'درآمد نهایی', 'net_profit']], hide_index=True, use_container_width=True)
            st.download_button(label="📥 دانلود گزارش", data=convert_df_to_excel(sales_df), file_name="Report.xlsx")

            tg_token, tg_chat_id = get_telegram_secrets()
            if tg_token and tg_chat_id and st.button("ارسال گزارش به تلگرام 🚀"):
                msg = f"📊 گزارش فیلتر شده ({time_filter}):\nدرآمد: {total_rev:,.0f}\nسود خالص: {total_prof:,.0f}"
                if send_telegram_msg(tg_token, tg_chat_id, msg): st.success("ارسال شد!")
                else: st.error("خطا در ارسال.")
        else:
            st.info("داده‌ای در این بازه یافت نشد.")

    with t_chart:
        if not sales_df.empty:
            chart_data = sales_df[['sale_date', 'درآمد نهایی']].copy()
            chart_data['date'] = chart_data['sale_date'].str.split(" - ").str[0]
            st.line_chart(chart_data.groupby('date')['درآمد نهایی'].sum())

            st.markdown("**🏆 پرفروش‌ترین کالاها (بر اساس تعداد فروش)**")
            top_products = sales_df[sales_df['product_code'] != 'SERVICE'].groupby('name')['quantity'].sum().sort_values(ascending=False).head(10)
            if not top_products.empty:
                st.bar_chart(top_products)
        else:
            st.info("داده‌ای برای نمایش نمودار وجود ندارد.")

    with t_exp:
        ex_t = st.text_input("شرح هزینه")
        ex_cat = st.selectbox("دسته‌بندی هزینه", EXPENSE_CATEGORIES)
        ex_a = st.number_input("مبلغ (تومان)", min_value=0, step=50000)
        show_toman_hint(ex_a)

        if st.button("ثبت خرج‌کرد") and ex_t and ex_a > 0:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO expenses (title, amount, exp_date, timestamp, category) VALUES (:t, :a, :d, :ts, :cat)"),
                             {"t": ex_t, "a": ex_a, "d": jalali_date_str(), "ts": iran_naive(), "cat": ex_cat})
            st.success("ثبت شد."); st.rerun()

        if not exp_df.empty:
            st.dataframe(exp_df[['exp_date', 'title', 'category', 'amount']], hide_index=True, use_container_width=True)
            st.markdown("**تفکیک هزینه‌ها بر اساس دسته‌بندی**")
            st.bar_chart(exp_df.groupby('category')['amount'].sum())

    with t_staff:
        if not sales_df.empty:
            staff_sales = sales_df[sales_df['staff_name'] != 'ادمین (بدون پورسانت)']
            if not staff_sales.empty:
                staff_perf = staff_sales.groupby('staff_name').agg({'quantity': 'sum', 'درآمد نهایی': 'sum', 'staff_commission': 'sum'}).reset_index()
                st.dataframe(staff_perf, hide_index=True, use_container_width=True)
            else:
                st.info("در این بازه فروشی توسط پرسنل ثبت نشده است.")
        else:
            st.info("داده‌ای یافت نشد.")

# ==========================================
# 5. دفتر حساب کامل (Ledger)
# ==========================================
elif choice == "📒 دفتر حساب (چک‌ها)":
    st.header("📒 دفتر طلب و بدهی")
    t1, t2 = st.tabs(["💵 طلب از مشتریان", "💳 بدهی و چک‌های ما"])

    def render_ledger(l_type, title, p_label):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input(p_label, key=f"n_{l_type}")
            amt = st.number_input("مبلغ", min_value=0, step=100000, key=f"a_{l_type}")
            show_toman_hint(amt)
        with c2:
            date = st.text_input("سررسید (مثال: 1403/06/10)", key=f"d_{l_type}")
            desc = st.text_input("بابت", key=f"ds_{l_type}")

        if st.button(f"✅ ثبت {title}", key=f"b_{l_type}"):
            if name and amt > 0:
                with engine.begin() as conn:
                    conn.execute(text("""INSERT INTO ledger (record_type, person_name, amount, due_date, description, status, timestamp)
                                          VALUES (:rt, :p, :a, :d, :ds, 'معلق', :ts)"""),
                                 {"rt": l_type, "p": name, "a": amt, "d": date, "ds": desc, "ts": iran_naive()})
                st.success("ثبت شد."); st.rerun()
            else:
                st.error("نام و مبلغ الزامی است.")

        show_settled = st.checkbox("نمایش موارد تسویه‌شده هم", key=f"sw_{l_type}")
        status_clause = "" if show_settled else "AND status != 'تسویه شده'"
        df_ledger = pd.read_sql_query(
            text(f"""SELECT id as 'کد', person_name as '{p_label}', amount as 'مبلغ', due_date as 'سررسید',
                            description as 'بابت', status as 'وضعیت'
                     FROM ledger WHERE record_type=:rt {status_clause} ORDER BY id DESC"""),
            engine, params={"rt": l_type}
        )
        if not df_ledger.empty:
            st.dataframe(df_ledger, hide_index=True, use_container_width=True)
            sel_id = st.number_input(f"کد ردیف {title} جهت اقدام:", min_value=0, step=1, key=f"sel_{l_type}")
            bcol1, bcol2 = st.columns(2)
            with bcol1:
                if st.button("✅ ثبت تسویه", key=f"settle_{l_type}") and sel_id > 0:
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE ledger SET status='تسویه شده', settled_at=:ts WHERE id=:i"),
                                     {"ts": iran_naive(), "i": sel_id})
                    st.success("به‌عنوان تسویه‌شده ثبت شد."); st.rerun()
            with bcol2:
                confirm_del = st.checkbox("تایید حذف کامل (غیرقابل بازگشت)", key=f"cd_{l_type}")
                if st.button("🗑️ حذف کامل رکورد", key=f"bd_{l_type}", disabled=not confirm_del) and sel_id > 0:
                    with engine.begin() as conn:
                        conn.execute(text("DELETE FROM ledger WHERE id=:i"), {"i": sel_id})
                    st.success("رکورد حذف شد."); st.rerun()

    with t1: render_ledger("customer_debt", "طلب", "مشتری بدهکار")
    with t2: render_ledger("owner_debt", "بدهی", "شخص طلبکار")

# ==========================================
# 6. مدیریت پرسنل
# ==========================================
elif choice == "👥 مدیریت پرسنل":
    st.header("👥 مدیریت شاگردان")
    c1, c2, c3 = st.columns(3)
    with c1: new_n = st.text_input("نام شاگرد")
    with c2: new_p = st.text_input("رمز (حداقل ۴ حرف)")
    with c3: new_r = st.number_input("پورسانت (%)", min_value=0.0, max_value=100.0, value=20.0)

    if st.button("ثبت شاگرد"):
        if new_n.strip() and len(new_p) >= 4:
            try:
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO staff (name, password, commission_rate, timestamp, active) VALUES (:n, :p, :r, :ts, 1)"),
                                 {"n": new_n.strip(), "p": hash_password(new_p), "r": new_r, "ts": iran_naive()})
                st.success("ثبت شد!")
                st.rerun()
            except IntegrityError:
                st.error("نام تکراری است.")
            except Exception as e:
                st.error(f"خطا: {e}")
        else:
            st.error("نام و رمز (حداقل ۴ حرف) را کامل وارد کنید.")

    df_staff = pd.read_sql_query("SELECT name as 'نام', commission_rate as 'پورسانت (%)', active as 'فعال' FROM staff ORDER BY name", engine)
    if not df_staff.empty:
        df_staff['فعال'] = df_staff['فعال'].astype(bool)
        df_staff['حذف؟'] = False
        edited_staff = st.data_editor(
            df_staff, hide_index=True, use_container_width=True, key="staff_editor",
            column_config={
                "نام": st.column_config.TextColumn(disabled=True),
                "پورسانت (%)": st.column_config.NumberColumn(min_value=0, max_value=100, step=1),
                "فعال": st.column_config.CheckboxColumn(help="غیرفعال یعنی امکان ورود ندارد؛ سابقه فروش او حفظ می‌شود"),
                "حذف؟": st.column_config.CheckboxColumn(help="حذف کامل و غیرقابل بازگشت"),
            }
        )
        to_delete_staff = edited_staff[edited_staff['حذف؟'] == True]['نام'].tolist()
        confirm_del_staff = False
        if to_delete_staff:
            confirm_del_staff = st.checkbox(f"⚠️ تایید حذف کامل {len(to_delete_staff)} نفر (غیرقابل بازگشت)")

        if st.button("💾 ذخیره تغییرات پرسنل", type="primary"):
            to_update_staff = edited_staff[edited_staff['حذف؟'] != True]
            with engine.begin() as conn:
                for _, row in to_update_staff.iterrows():
                    conn.execute(text("UPDATE staff SET commission_rate=:r, active=:a WHERE name=:n"),
                                 {"r": row['پورسانت (%)'], "a": 1 if row['فعال'] else 0, "n": row['نام']})
                if to_delete_staff:
                    if confirm_del_staff:
                        for n in to_delete_staff:
                            conn.execute(text("DELETE FROM staff WHERE name=:n"), {"n": n})
                    else:
                        st.warning("موارد علامت‌خورده برای حذف، به دلیل عدم تایید، حذف نشدند.")
            st.success("تغییرات ذخیره شد.")
            st.rerun()

# ==========================================
# 7. تنظیمات فروشگاه و پشتیبان‌گیری
# ==========================================
elif choice == "⚙️ تنظیمات و پشتیبان‌گیری":
    st.header("⚙️ تنظیمات فروشگاه")

    if db_type.startswith("SQLite"):
        st.error("⚠️ در حال حاضر برنامه از دیتابیس محلی (SQLite) استفاده می‌کند. اگر این برنامه روی Streamlit Cloud اجرا می‌شود، با هر ری‌استارت یا آپدیت سرور، تمام اطلاعات (فروش‌ها، انبار، مشتریان) برای همیشه پاک خواهد شد. برای جلوگیری از این خطر جدی، یک دیتابیس ابری مثل Supabase تنظیم کرده و آدرس آن را در بخش Secrets پروژه‌تان در Streamlit Cloud، با ساختار [supabase] db_url وارد کنید.")

    with st.form("shop_settings_form"):
        s_name = st.text_input("نام فروشگاه", value=get_setting("shop_name", "فروشگاه لوازم جانبی و اسپرت خودرو"))
        s_addr = st.text_input("آدرس فروشگاه", value=get_setting("shop_address", ""))
        s_phone = st.text_input("تلفن فروشگاه", value=get_setting("shop_phone", ""))
        s_footer = st.text_input("متن پایین فاکتور", value=get_setting("invoice_footer", "از اعتماد و خرید شما سپاسگزاریم"))
        if st.form_submit_button("💾 ذخیره تنظیمات", type="primary"):
            set_setting("shop_name", s_name)
            set_setting("shop_address", s_addr)
            set_setting("shop_phone", s_phone)
            set_setting("invoice_footer", s_footer)
            st.success("تنظیمات ذخیره شد.")
            st.rerun()

    st.caption("🔑 رمز عبور ادمین از بخش Secrets پروژه (کلید admin_password) تنظیم می‌شود، نه از این صفحه؛ این یعنی رمز ادمین هیچ‌وقت داخل دیتابیس ذخیره نمی‌شود.")

    st.markdown("---")
    st.subheader("📦 پشتیبان‌گیری کامل از اطلاعات")
    st.caption("یک فایل اکسل چندشیتی شامل انبار، فروش‌ها، دفتر حساب، هزینه‌ها، پرسنل و تاریخچه اصلاح موجودی دانلود کنید.")
    backup_bytes = build_full_backup()
    st.download_button(
        label="📥 دانلود فایل پشتیبان کامل",
        data=backup_bytes,
        file_name=f"Backup_{iran_naive().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
