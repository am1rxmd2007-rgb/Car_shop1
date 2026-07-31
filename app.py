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
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import A5

# ایمپورت اسکنر حرفه‌ای
try:
    from streamlit_qrcode_scanner import qrcode_scanner
    HAS_SCANNER_PKG = True
except ImportError:
    HAS_SCANNER_PKG = False

# ==========================================
# تنظیمات صفحه و استایل‌ها (Mobile-First)
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
# لیست‌های پایه (Dropdown)
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

# ==========================================
# توابع کمکی
# ==========================================
def get_iran_time():
    return datetime.now(pytz.timezone('Asia/Tehran'))

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
    except: return False

def hash_password(raw_password):
    return hashlib.sha256(str(raw_password).encode("utf-8")).hexdigest()

# ==========================================
# دیتابیس (Supabase / SQLite Fallback)
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
    # نکته: در SQLite، "INTEGER PRIMARY KEY AUTOINCREMENT" باید یکجا و به‌عنوان
    # تنها تعریف کلید اصلی ستون باشد؛ اضافه‌کردن یک "PRIMARY KEY(id)" جداگانه
    # باعث خطای "more than one primary key" و کرش کامل برنامه می‌شود.
    id_type = "SERIAL PRIMARY KEY" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"

    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS products (
                code TEXT PRIMARY KEY, name TEXT, category TEXT, purchase_price REAL, 
                sale_price REAL, stock INTEGER, compatible_cars TEXT DEFAULT 'عمومی'
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
                due_date TEXT, description TEXT, status TEXT, timestamp TIMESTAMP
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS expenses (
                id {id_type}, title TEXT, amount REAL, exp_date TEXT, timestamp TIMESTAMP
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS staff (
                id {id_type}, name TEXT UNIQUE, password TEXT DEFAULT '1234', 
                commission_rate REAL, timestamp TIMESTAMP
            )
        """))

init_db()

# ==========================================
# تولید فاکتور PDF
# ==========================================
def generate_pdf_invoice(inv):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A5)
    width, height = A5
    
    try:
        pdfmetrics.registerFont(TTFont('Vazir', 'Vazirmatn.ttf'))
        c.setFont('Vazir', 14)
        has_font = True
    except:
        c.setFont('Helvetica-Bold', 14)
        has_font = False

    def draw_rtl_text(text_str, x, y):
        if has_font:
            reshaped_text = arabic_reshaper.reshape(str(text_str))
            bidi_text = get_display(reshaped_text)
            c.drawRightString(x, y, bidi_text)
        else:
            c.drawRightString(x, y, str(text_str))

    draw_rtl_text("فروشگاه لوازم جانبی و اسپرت خودرو", width - 30, height - 40)
    c.setFont('Vazir' if has_font else 'Helvetica', 10)
    
    y = height - 70
    draw_rtl_text(f"تاریخ: {inv['date']}", width - 30, y)
    draw_rtl_text(f"مشتری: {inv['c_name']} | خودرو: {inv['c_car']}", width - 30, y - 20)
    draw_rtl_text(f"شماره تماس: {inv['c_phone']} | صندوق‌دار: {inv['staff']}", width - 30, y - 40)
    c.line(30, y - 55, width - 30, y - 55)
    
    y -= 75
    draw_rtl_text(f"شرح کالا / خدمات: {inv['p_name']}", width - 30, y)
    draw_rtl_text(f"تعداد: {inv['qty']} عدد", width - 30, y - 20)
    draw_rtl_text(f"قیمت واحد: {inv['price']:,} تومان", width - 30, y - 40)
    draw_rtl_text(f"اجرت نصب: {inv['install']:,} تومان", width - 30, y - 60)
    if inv['discount'] > 0:
        draw_rtl_text(f"تخفیف: {inv['discount']:,} تومان", width - 30, y - 80)
        y -= 20
        
    c.line(30, y - 75, width - 30, y - 75)
    c.setFont('Vazir' if has_font else 'Helvetica-Bold', 12)
    draw_rtl_text(f"جمع کل پرداختی: {inv['total']:,} تومان", width - 30, y - 100)
    
    c.setFont('Vazir' if has_font else 'Helvetica', 9)
    draw_rtl_text("از اعتماد و خرید شما سپاسگزاریم", width / 2 + 50, 30)
    
    c.save()
    buffer.seek(0)
    return buffer

# ==========================================
# مدیریت وضعیت سیستم و لاگین
# ==========================================
for key in ["user_role", "user_name", "last_invoice", "scanned_add_code"]:
    if key not in st.session_state: st.session_state[key] = None if "code" not in key else ""
for key in ["name_s", "phone_s", "car_s", "last_search_sale", "vip_search_sale_input"]:
    if key not in st.session_state: st.session_state[key] = ""
if "clear_sale_form" not in st.session_state: st.session_state.clear_sale_form = False

st.sidebar.title("🚗 سیستم فروشگاه اسپرت")
st.sidebar.caption(f"📡 اتصال دیتابیس: {db_type}")
st.sidebar.markdown("---")

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
            else: st.sidebar.error("رمز اشتباه است!")
    else:
        staff_df = pd.read_sql_query("SELECT name FROM staff", engine)
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
                else: st.sidebar.error("❌ رمز عبور اشتباه است!")
        else: st.sidebar.warning("هنوز هیچ شاگردی ثبت نشده است!")
    st.title("🛡️ به نرم‌افزار جامع فروشگاه خوش آمدید")
    st.info("👈 برای شروع کار، لطفاً از منوی سمت چپ وارد حساب کاربری خود شوید.")
    st.stop() 

st.sidebar.success(f"👤 کاربر فعال: {st.session_state.user_name}")

if st.session_state.user_role == "Staff":
    with st.sidebar.expander("🔑 تغییر رمز عبور من"):
        old_pw = st.text_input("رمز فعلی", type="password")
        new_pw = st.text_input("رمز جدید (حداقل ۴ حرف)", type="password")
        if st.button("ثبت رمز جدید"):
            with engine.begin() as conn:
                curr = conn.execute(text("SELECT password FROM staff WHERE name=:n"), {"n": st.session_state.user_name}).fetchone()
                if curr and curr[0] == hash_password(old_pw):
                    conn.execute(text("UPDATE staff SET password=:p WHERE name=:n"), {"p": hash_password(new_pw), "n": st.session_state.user_name})
                    st.success("رمز با موفقیت تغییر کرد!")
                else: st.error("رمز فعلی اشتباه است.")

if st.sidebar.button("خروج از سیستم"):
    st.session_state.user_role = None; st.session_state.user_name = None; st.rerun()

menu = ["🛒 ثبت فروش / خدمات", "📦 مدیریت انبار", "➕ افزودن کالا", "📊 گزارش‌ها و داشبورد", "📒 دفتر حساب (چک‌ها)", "👥 مدیریت پرسنل"] if st.session_state.user_role == "Admin" else ["🛒 ثبت فروش / خدمات", "📦 جستجو در انبار"]
choice = st.sidebar.radio("منوی اختصاصی شما:", menu)

# ==========================================
# 1. ثبت فروش، خدمات و مرجوعی
# ==========================================
if choice == "🛒 ثبت فروش / خدمات":
    st.header("🛒 ثبت فاکتور مشتری")
    
    staff_df_list = pd.read_sql_query("SELECT name FROM staff", engine)
    vip_df = pd.read_sql_query("SELECT DISTINCT customer_name, customer_phone, car_model FROM sales WHERE customer_name != '' OR customer_phone != ''", engine)
    staff_options = ["ادمین (بدون پورسانت)"] + staff_df_list['name'].tolist() if not staff_df_list.empty else ["ادمین (بدون پورسانت)"]

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
            elif scan_method == "جستجوی نام کالا":
                search_q = st.text_input("نام کالا یا ماشین:")
                if search_q:
                    like_q = f"%{search_q}%"
                    m_df = pd.read_sql_query(
                        text("SELECT code, name, compatible_cars FROM products WHERE name LIKE :q OR compatible_cars LIKE :q"),
                        engine, params={"q": like_q}
                    )
                    if not m_df.empty:
                        opts = (m_df['name'] + " (مناسب: " + m_df['compatible_cars'] + ") - کد: " + m_df['code']).tolist()
                        code_input = st.selectbox("انتخاب کالا:", opts).split("کد: ")[1].strip()

        with col2:
            if code_input:
                with engine.connect() as conn:
                    product = conn.execute(text("SELECT * FROM products WHERE code=:c"), {"c": code_input}).fetchone()

                if product:
                    st.subheader(f"📦 {product[1]}")
                    st.markdown(f"**قیمت فروش:** {product[4]:,.0f} تومان | **موجودی:** {product[5]} عدد")
                    
                    f_qty = st.number_input("تعداد", min_value=1, max_value=product[5] if product[5]>0 else 1)
                    
                    f_install = st.number_input("اجرت نصب (تومان)", min_value=0, step=10000, value=0)
                    if f_install >= 0: st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#2e7d32; font-weight:bold; font-size: 14px;'>💳 معادل: {f_install:,.0f} تومان</div>", unsafe_allow_html=True)
                    
                    max_discount = int((product[4] * f_qty) + f_install)
                    f_discount = st.number_input("مبلغ تخفیف (تومان)", min_value=0, max_value=max_discount, step=10000, value=0)
                    if f_discount >= 0: st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#d32f2f; font-weight:bold; font-size: 14px;'>🎁 معادل تخفیف: {f_discount:,.0f} تومان</div>", unsafe_allow_html=True)
                    
                    s_staff = st.selectbox("👷‍♂️ ثبت به نام:", staff_options) if st.session_state.user_role == "Admin" else st.session_state.user_name
                    
                    st.markdown("🔍 **تکمیل اطلاعات مشتری**")
                    if st.session_state.get('clear_sale_form'):
                        st.session_state["name_s"] = ""; st.session_state["phone_s"] = ""; st.session_state["car_s"] = "عمومی (همه خودروها)"
                        st.session_state.last_search_sale = ""; st.session_state["vip_search_sale_input"] = ""; st.session_state['clear_sale_form'] = False

                    vip_search_q = st.text_input("⌨️ شماره موبایل مشتری قدیمی (جستجو):", key="vip_search_sale_input")
                    if vip_search_q and vip_search_q != st.session_state.last_search_sale:
                        st.session_state.last_search_sale = vip_search_q
                        if not vip_df.empty:
                            match = vip_df[(vip_df['customer_phone'].astype(str).str.contains(vip_search_q, case=False, na=False))]
                            if not match.empty:
                                st.session_state["name_s"] = str(match.iloc[0]['customer_name'])
                                st.session_state["phone_s"] = str(match.iloc[0]['customer_phone'])
                                
                    cc1, cc2 = st.columns(2)
                    with cc1: c_name = st.text_input("نام مشتری", key="name_s")
                    with cc2: c_phone = st.text_input("موبایل", key="phone_s")
                    
                    car_opt = st.selectbox("مدل ماشین", CAR_MODELS + ["سایر (تایپ دستی)"])
                    c_car = st.text_input("لطفاً نام خودرو را وارد کنید:") if car_opt == "سایر (تایپ دستی)" else car_opt

                    if st.button("✅ ثبت نهایی فاکتور کالا", use_container_width=True):
                        now_dt = get_iran_time()
                        now_str = jdatetime.datetime.fromgregorian(datetime=now_dt.replace(tzinfo=None)).strftime('%Y/%m/%d - %H:%M')
                        net_prof = ((product[4] - product[3]) * f_qty) + f_install - f_discount
                        total_bill = (product[4] * f_qty) + f_install - f_discount

                        with engine.begin() as conn:
                            res = conn.execute(text("UPDATE products SET stock = stock - :q WHERE code = :c AND stock >= :q"), {"q": f_qty, "c": code_input})
                            if res.rowcount == 0:
                                st.error("موجودی کافی نیست!")
                            else:
                                staff_rate = 0
                                if s_staff != "ادمین (بدون پورسانت)":
                                    s_res = conn.execute(text("SELECT commission_rate FROM staff WHERE name=:n"), {"n": s_staff}).fetchone()
                                    if s_res: staff_rate = s_res[0]
                                
                                conn.execute(text("""
                                    INSERT INTO sales (product_code, name, quantity, sale_price, sale_date, timestamp, 
                                    customer_name, customer_phone, car_model, install_fee, net_profit, staff_name, staff_commission, discount) 
                                    VALUES (:pc, :n, :q, :sp, :sd, :ts, :cn, :cp, :cm, :i, :np, :sn, :sc, :d)
                                """), {
                                    "pc": code_input, "n": product[1], "q": f_qty, "sp": product[4], "sd": now_str, 
                                    "ts": now_dt.replace(tzinfo=None), "cn": c_name, "cp": c_phone, "cm": c_car, 
                                    "i": f_install, "np": net_prof, "sn": s_staff, "sc": (net_prof * (staff_rate/100) if net_prof>0 else 0), "d": f_discount
                                })
                                st.session_state.last_invoice = {"date":now_str, "c_name":c_name or "نقدی", "c_phone":c_phone, "c_car":c_car, "p_name":product[1], "qty":f_qty, "price":product[4], "install":f_install, "discount":f_discount, "total":total_bill, "staff":s_staff}
                                st.session_state['clear_sale_form'] = True
                                st.success("فروش ثبت شد!")
                                st.rerun()

    with tab_service:
        s_name = st.text_input("شرح خدمات (مثال: نصب سیستم صوتی)")
        
        s_fee = st.number_input("مبلغ اجرت (تومان)", min_value=0, step=50000)
        if s_fee >= 0: st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#2e7d32; font-weight:bold; font-size: 14px;'>💳 معادل: {s_fee:,.0f} تومان</div>", unsafe_allow_html=True)
            
        s_staff_srv = st.selectbox("👷‍♂️ ثبت به نام نصاب:", staff_options, key="staff_srv") if st.session_state.user_role == "Admin" else st.session_state.user_name
        
        sc1, sc2 = st.columns(2)
        with sc1: s_cname = st.text_input("نام مشتری", key="name_srv_s")
        with sc2: s_cphone = st.text_input("شماره موبایل", key="phone_srv_s")
        
        car_opt_srv = st.selectbox("مدل خودرو", CAR_MODELS + ["سایر (تایپ دستی)"], key="car_srv_opt")
        s_ccar = st.text_input("لطفاً نام خودرو را وارد کنید:", key="car_srv_txt") if car_opt_srv == "سایر (تایپ دستی)" else car_opt_srv
        
        if st.button("🔧 ثبت خدمات", use_container_width=True):
            if s_name and s_fee > 0:
                now_dt = get_iran_time()
                now_str = jdatetime.datetime.fromgregorian(datetime=now_dt.replace(tzinfo=None)).strftime('%Y/%m/%d - %H:%M')
                
                with engine.begin() as conn:
                    staff_rate = 0
                    if s_staff_srv != "ادمین (بدون پورسانت)":
                        s_res = conn.execute(text("SELECT commission_rate FROM staff WHERE name=:n"), {"n": s_staff_srv}).fetchone()
                        if s_res: staff_rate = s_res[0]
                    
                    conn.execute(text("""
                        INSERT INTO sales (product_code, name, quantity, sale_price, sale_date, timestamp, customer_name, customer_phone, car_model, install_fee, net_profit, staff_name, staff_commission, discount) 
                        VALUES ('SERVICE', :n, 0, 0, :sd, :ts, :cn, :cp, :cm, :i, :i, :sn, :sc, 0)
                    """), {"n": s_name, "sd": now_str, "ts": now_dt.replace(tzinfo=None), "cn": s_cname, "cp": s_cphone, "cm": s_ccar, "i": s_fee, "sn": s_staff_srv, "sc": s_fee * (staff_rate/100.0)})
                
                st.session_state.last_invoice = {"date":now_str, "c_name":s_cname or "نقدی", "c_phone":s_cphone, "c_car":s_ccar, "p_name":s_name, "qty":0, "price":0, "install":s_fee, "discount":0, "total":s_fee, "staff":s_staff_srv}
                st.success("خدمات ثبت شد!")
                st.rerun()
            else: st.error("شرح و مبلغ الزامی است.")
                
    with tab_refund:
        if st.session_state.user_role == "Admin":
            recent_sales = pd.read_sql_query("SELECT id, product_code as 'کد کالا', name as 'شرح', quantity as 'تعداد', sale_date as 'تاریخ', customer_name as 'مشتری', staff_name as 'پرسنل' FROM sales ORDER BY id DESC LIMIT 30", engine)
            if not recent_sales.empty:
                st.dataframe(recent_sales, hide_index=True, use_container_width=True)
                refund_id = st.number_input("کد ردیف فاکتور (id) جهت ابطال:", min_value=0, step=1)
                confirm_refund = st.checkbox("تایید ابطال فاکتور و بازگشت به انبار")
                
                if st.button("🗑️ ابطال فاکتور", disabled=not confirm_refund, type="primary"):
                    with engine.begin() as conn:
                        sale_rec = conn.execute(text("SELECT product_code, quantity FROM sales WHERE id=:i"), {"i": refund_id}).fetchone()
                        if sale_rec:
                            if sale_rec[0] != 'SERVICE':
                                conn.execute(text("UPDATE products SET stock = stock + :q WHERE code=:c"), {"q": sale_rec[1], "c": sale_rec[0]})
                            conn.execute(text("DELETE FROM sales WHERE id=:i"), {"i": refund_id})
                            st.success("فاکتور باطل شد و موجودی به انبار بازگشت.")
                        else: st.error("فاکتوری یافت نشد.")
            else: st.warning("فاکتوری وجود ندارد.")
        else: st.error("فقط ادمین دسترسی دارد.")

    if st.session_state.last_invoice:
        inv = st.session_state.last_invoice
        st.markdown("---")
        st.subheader("🧾 فاکتور مشتری")
        
        # دکمه پرینت PDF
        pdf_bytes = generate_pdf_invoice(inv)
        st.download_button(label="📥 دانلود فاکتور PDF (آماده چاپ)", data=pdf_bytes, file_name=f"Invoice_{inv['c_phone']}.pdf", mime="application/pdf", type="primary", use_container_width=True)
        
        dis_text = f"\n🎁 تخفیف اعمال شده: {inv['discount']:,} تومان" if inv['discount'] > 0 else ""
        inv_text = f"🧾 فاکتور فروشگاه\nتاریخ: {inv['date']}\n👤 مشتری: {inv['c_name']}\n🚗 خودرو: {inv['c_car']}\n👷‍♂️ مسئول: {inv['staff']}\n-------------------\n📦 شرح: {inv['p_name']}\n🔢 تعداد: {inv['qty']}\n💵 فی: {inv['price']:,} تومان\n🔧 اجرت: {inv['install']:,} تومان{dis_text}\n-------------------\n💰 جمع کل: {inv['total']:,} تومان\n✨ سپاس از اعتماد شما ✨"
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
# 2. انبار و افزودن کالا (شامل ورود گروهی اکسل)
# ==========================================
elif choice in ["📦 مدیریت انبار", "📦 جستجو در انبار"]:
    st.header(choice)
    df = pd.read_sql_query("SELECT code as 'کد', name as 'نام', compatible_cars as 'ماشین', category as 'دسته', purchase_price as 'خرید', sale_price as 'فروش', stock as 'موجودی' FROM products", engine)
    if st.session_state.user_role != "Admin": df = df.drop(columns=['خرید'])

    sc1, sc2 = st.columns([2, 1])
    with sc1: search = st.text_input("🔍 سرچ:")
    with sc2: scan_chk = st.checkbox("فعال‌سازی اسکنر")
    q_code = qrcode_scanner(key='inv_scan') if (scan_chk and HAS_SCANNER_PKG) else ""
        
    dsp_df = df.copy()
    if search:
        mask = dsp_df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
        dsp_df = dsp_df[mask]
    elif q_code: dsp_df = dsp_df[dsp_df['کد'] == q_code]

    st.dataframe(dsp_df, use_container_width=True, hide_index=True)
    
    if st.session_state.user_role == "Admin":
        if not dsp_df.empty:
            st.download_button(label="📥 دانلود لیست انبار (Excel)", data=convert_df_to_excel(dsp_df), file_name=f"Inventory_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        out_df = df[df['موجودی'] < 3]
        if not out_df.empty:
            st.error(f"⚠️ {len(out_df)} کالا موجودی رو به اتمام دارند:")
            st.dataframe(out_df, use_container_width=True, hide_index=True)
            st.download_button(label="🛒 دانلود لیست کسری‌ها", data=convert_df_to_excel(out_df), file_name=f"Reorder_{datetime.now().strftime('%Y%m%d')}.xlsx")

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
            pb = st.number_input("قیمت خرید", step=10000)
            if pb >= 0: st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#2e7d32; font-weight:bold; font-size: 14px;'>💳 معادل: {pb:,.0f} تومان</div>", unsafe_allow_html=True)
        with c2: 
            ps = st.number_input("قیمت فروش", step=10000)
            if ps >= 0: st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#2e7d32; font-weight:bold; font-size: 14px;'>💳 معادل: {ps:,.0f} تومان</div>", unsafe_allow_html=True)
            
        stock = st.number_input("موجودی", min_value=0)
        
        if st.button("ثبت کالا", type="primary"):
            if name:
                fc = code.strip() or f"AUTO-{get_iran_time().strftime('%Y%m%d%H%M%S%f')}"
                try:
                    with engine.begin() as conn:
                        conn.execute(text("INSERT INTO products VALUES (:c, :n, :cat, :pb, :ps, :st, :car)"), 
                                     {"c": fc, "n": name, "cat": cat, "pb": pb, "ps": ps, "st": stock, "car": car})
                    st.session_state.scanned_add_code = ""
                    st.success("کالا ثبت شد!")
                except Exception: st.error("کد تکراری است!")
            else: st.error("نام کالا الزامی است.")
            
    with tab_bulk:
        st.info("ابتدا فایل نمونه را دانلود کنید، پر کنید و آپلود نمایید.")
        sample_df = pd.DataFrame(columns=['کد کالا (اختیاری)', 'نام کالا', 'مناسب خودرو', 'دسته‌بندی', 'قیمت خرید', 'قیمت فروش', 'موجودی'])
        st.download_button(label="📥 دانلود قالب اکسل", data=convert_df_to_excel(sample_df), file_name="Template_Products.xlsx")
        uploaded_file = st.file_uploader("📤 آپلود فایل اکسل تکمیل‌شده:", type=['xlsx'])
        if uploaded_file and st.button("🚀 پردازش فایل"):
            try:
                bulk_df = pd.read_excel(uploaded_file)
                success_count, error_count = 0, 0
                with engine.begin() as conn:
                    for index, row in bulk_df.iterrows():
                        p_name = str(row['نام کالا'])
                        if p_name == 'nan' or not p_name.strip(): continue
                        p_code = str(row['کد کالا (اختیاری)'])
                        fc = f"AUTO-{get_iran_time().strftime('%Y%m%d%H%M%S%f')}" if p_code == 'nan' else p_code.strip()
                        pc = str(row['مناسب خودرو']) if str(row['مناسب خودرو']) != 'nan' else "عمومی"
                        pcat = str(row['دسته‌بندی']) if str(row['دسته‌بندی']) != 'nan' else "سایر"
                        pb = float(row['قیمت خرید']) if str(row['قیمت خرید']) != 'nan' else 0
                        ps = float(row['قیمت فروش']) if str(row['قیمت فروش']) != 'nan' else 0
                        pst = int(row['موجودی']) if str(row['موجودی']) != 'nan' else 0
                        try:
                            conn.execute(text("INSERT INTO products VALUES (:c, :n, :cat, :pb, :ps, :st, :car)"), 
                                         {"c": fc, "n": p_name, "cat": pcat, "pb": pb, "ps": ps, "st": pst, "car": pc})
                            success_count += 1
                        except: error_count += 1
                if success_count > 0: st.success(f"✅ {success_count} کالا اضافه شد.")
                if error_count > 0: st.warning(f"⚠️ {error_count} کالا تکراری بود و ثبت نشد.")
            except Exception as e: st.error("فایل نامعتبر است.")

# ==========================================
# 3. داشبورد و گزارش‌ها با فیلتر پیشرفته
# ==========================================
elif choice == "📊 گزارش‌ها و داشبورد":
    st.header("📊 داشبورد مدیریت مالی")
    time_filter = st.selectbox("📅 فیلتر بازه زمانی:", ["امروز", "۷ روز گذشته", "ماه جاری (۳۰ روز)", "همه زمان‌ها"])
    now = datetime.now()
    if time_filter == "امروز": start_dt = now - timedelta(days=1)
    elif time_filter == "۷ روز گذشته": start_dt = now - timedelta(days=7)
    elif time_filter == "ماه جاری (۳۰ روز)": start_dt = now - timedelta(days=30)
    else: start_dt = now - timedelta(days=3650) # ده سال
    
    sales_df = pd.read_sql_query("SELECT * FROM sales", engine)
    exp_df = pd.read_sql_query("SELECT * FROM expenses", engine)
    
    if not sales_df.empty:
        _ts = pd.to_datetime(sales_df['timestamp'])
        sales_df['timestamp'] = _ts.dt.tz_convert(None) if _ts.dt.tz is not None else _ts
        sales_df = sales_df[sales_df['timestamp'] >= start_dt]
        sales_df['discount'] = sales_df['discount'].fillna(0)
        sales_df['install_fee'] = sales_df['install_fee'].fillna(0)
        sales_df['staff_commission'] = sales_df['staff_commission'].fillna(0)
        sales_df['net_profit'] = sales_df['net_profit'].fillna(0)
        sales_df['درآمد نهایی'] = (sales_df['quantity'] * sales_df['sale_price']) + sales_df['install_fee'] - sales_df['discount']
        
    if not exp_df.empty:
        _ts_exp = pd.to_datetime(exp_df['timestamp'])
        exp_df['timestamp'] = _ts_exp.dt.tz_convert(None) if _ts_exp.dt.tz is not None else _ts_exp
        exp_df = exp_df[exp_df['timestamp'] >= start_dt]

    t_rep, t_chart, t_exp, t_staff = st.tabs(["📋 فروش", "📈 نمودار", "💸 خرج‌کرد", "👥 پرسنل"])
    
    with t_rep:
        if not sales_df.empty:
            total_rev = sales_df['درآمد نهایی'].sum()
            total_exp = exp_df['amount'].sum() if not exp_df.empty else 0
            total_prof = sales_df['net_profit'].sum() - total_exp - sales_df['staff_commission'].sum()
            c1, c2 = st.columns(2)
            c1.metric("درآمد صندوق", f"{total_rev:,.0f} T")
            c2.metric("سود خالص صاحب مغازه", f"{total_prof:,.0f} T")
            st.dataframe(sales_df[['sale_date', 'name', 'staff_name', 'درآمد نهایی', 'net_profit']], hide_index=True, use_container_width=True)
            st.download_button(label="📥 دانلود گزارش", data=convert_df_to_excel(sales_df), file_name=f"Report.xlsx")
            
            tg_token, tg_chat_id = get_telegram_secrets()
            if tg_token and tg_chat_id and st.button("ارسال گزارش به تلگرام 🚀"):
                msg = f"📊 گزارش فیلتر شده:\nدرآمد: {total_rev:,.0f}\nسود خالص: {total_prof:,.0f}"
                if send_telegram_msg(tg_token, tg_chat_id, msg): st.success("ارسال شد!")
                else: st.error("خطا در ارسال.")
        else: st.info("داده‌ای یافت نشد.")
        
    with t_chart:
        if not sales_df.empty:
            chart_data = sales_df[['sale_date', 'درآمد نهایی']].copy()
            chart_data['date'] = chart_data['sale_date'].str.split(" - ").str[0]
            st.line_chart(chart_data.groupby('date')['درآمد نهایی'].sum())
            
    with t_exp:
        ex_t = st.text_input("شرح هزینه")
        ex_a = st.number_input("مبلغ (تومان)", step=50000)
        
        if ex_a >= 0: st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#2e7d32; font-weight:bold; font-size: 14px;'>💳 معادل: {ex_a:,.0f} تومان</div>", unsafe_allow_html=True)
            
        if st.button("ثبت خرج‌کرد") and ex_t and ex_a > 0:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO expenses (title, amount, exp_date, timestamp) VALUES (:t, :a, :d, :ts)"), 
                             {"t": ex_t, "a": ex_a, "d": jdatetime.datetime.now().strftime('%Y/%m/%d'), "ts": datetime.now()})
            st.success("ثبت شد."); st.rerun()
        if not exp_df.empty: st.dataframe(exp_df[['exp_date', 'title', 'amount']], hide_index=True)
            
    with t_staff:
        if not sales_df.empty:
            staff_perf = sales_df[sales_df['staff_name'] != 'ادمین (بدون پورسانت)'].groupby('staff_name').agg({'quantity':'sum', 'درآمد نهایی':'sum', 'staff_commission':'sum'}).reset_index()
            st.dataframe(staff_perf, hide_index=True, use_container_width=True)

# ==========================================
# 4. دفتر حساب کامل (Ledger)
# ==========================================
elif choice == "📒 دفتر حساب (چک‌ها)":
    st.header("📒 دفتر طلب و بدهی")
    t1, t2 = st.tabs(["💵 طلب از مشتریان", "💳 بدهی و چک‌های ما"])
    
    def render_ledger(l_type, title, p_label):
        c1, c2 = st.columns(2)
        with c1: 
            name = st.text_input(p_label, key=f"n_{l_type}")
            amt = st.number_input("مبلغ", step=100000, key=f"a_{l_type}")
            if amt >= 0: st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#2e7d32; font-weight:bold; font-size: 14px;'>💳 معادل: {amt:,.0f} تومان</div>", unsafe_allow_html=True)
        with c2:
            date = st.text_input("سررسید (مثال: 1403/06/10)", key=f"d_{l_type}")
            desc = st.text_input("بابت", key=f"ds_{l_type}")
            
        if st.button(f"✅ ثبت {title}", key=f"b_{l_type}") and name and amt > 0:
            with engine.begin() as conn:
                conn.execute(text("INSERT INTO ledger (record_type, person_name, amount, due_date, description, status, timestamp) VALUES (:rt, :p, :a, :d, :ds, 'معلق', :ts)"), 
                             {"rt": l_type, "p": name, "a": amt, "d": date, "ds": desc, "ts": datetime.now()})
            st.rerun()
                
        df_ledger = pd.read_sql_query(f"SELECT id as 'کد', person_name as '{p_label}', amount as 'مبلغ', due_date as 'سررسید', description as 'بابت' FROM ledger WHERE record_type='{l_type}'", engine)
        if not df_ledger.empty:
            st.dataframe(df_ledger, hide_index=True, use_container_width=True)
            did = st.number_input(f"کد جهت حذف {title}:", min_value=1, key=f"del_{l_type}")
            if st.button("تسویه و حذف", key=f"bd_{l_type}"):
                with engine.begin() as conn: conn.execute(text("DELETE FROM ledger WHERE id=:i"), {"i": did})
                st.rerun()
                
    with t1: render_ledger("customer_debt", "طلب", "مشتری بدهکار")
    with t2: render_ledger("owner_debt", "بدهی", "شخص طلبکار")

# ==========================================
# 5. مدیریت پرسنل
# ==========================================
elif choice == "👥 مدیریت پرسنل":
    st.header("👥 مدیریت شاگردان")
    c1, c2, c3 = st.columns(3)
    with c1: new_n = st.text_input("نام شاگرد")
    with c2: new_p = st.text_input("رمز (حداقل ۴ حرف)")
    with c3: new_r = st.number_input("پورسانت (%)", value=20.0)
        
    if st.button("ثبت شاگرد"):
        if new_n and len(new_p) >= 4:
            try:
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO staff (name, password, commission_rate, timestamp) VALUES (:n, :p, :r, :ts)"), 
                                 {"n": new_n, "p": hash_password(new_p), "r": new_r, "ts": datetime.now()})
                st.success("ثبت شد!")
            except: st.error("نام تکراری است.")
        else: st.error("اطلاعات را کامل وارد کنید.")
            
    df_staff = pd.read_sql_query("SELECT id, name as 'نام', commission_rate as 'پورسانت' FROM staff", engine)
    if not df_staff.empty:
        st.dataframe(df_staff, hide_index=True, use_container_width=True)
        del_id = st.number_input("کد جهت اخراج:", min_value=0)
        if st.button("🗑️ حذف شاگرد"):
            with engine.begin() as conn: conn.execute(text("DELETE FROM staff WHERE id=:i"), {"i": del_id})
            st.rerun()
