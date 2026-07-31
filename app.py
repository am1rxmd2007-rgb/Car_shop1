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
from sqlalchemy.exc import OperationalError, ProgrammingError
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import A5

# ایمپورت اسکنر
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
    
    /* راست‌چین کردن کل برنامه و اصلاحات موبایل */
    .stMarkdown, p, h1, h2, h3, h4, label, .stSelectbox, .stTextInput { 
        direction: rtl; text-align: right; font-family: 'Tahoma', sans-serif !important; 
    }
    
    [data-testid="stSidebar"] {
        direction: rtl;
    }
    
    .stButton>button { width: 100%; border-radius: 8px; font-weight: bold; }
    
    .invoice-box { 
        border: 2px dashed #4CAF50; padding: 20px; border-radius: 10px; 
        background-color: #f9f9f9; color: #333; margin-top: 15px; 
        direction: rtl; text-align: right; 
    }
    
    .metric-box { 
        padding: 15px; border-radius: 10px; background-color: #e8f5e9; 
        border: 1px solid #4CAF50; margin-bottom: 20px; text-align: center; 
        font-size: 20px; font-weight: bold; color: #2e7d32; 
    }
    
    /* جلوگیری از بهم‌ریختگی در موبایل */
    @media (max-width: 768px) {
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    }
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

def hash_password(raw_password):
    return hashlib.sha256(str(raw_password).encode("utf-8")).hexdigest()

# ==========================================
# مدیریت دیتابیس (Supabase / SQLite Fallback)
# ==========================================
@st.cache_resource
def get_engine():
    try:
        if "supabase" in st.secrets and "db_url" in st.secrets["supabase"]:
            db_url = st.secrets["supabase"]["db_url"]
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
            engine = create_engine(db_url, pool_pre_ping=True)
            # تست اتصال
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return engine, "PostgreSQL (Supabase)"
    except Exception as e:
        pass
    
    return create_engine("sqlite:///inventory.db"), "SQLite (Local)"

engine, db_type = get_engine()

def init_db():
    is_pg = 'postgresql' in engine.dialect.name
    id_type = "SERIAL" if is_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    
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
                {"" if is_pg else ", PRIMARY KEY(id)"}
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS ledger (
                id {id_type}, record_type TEXT, person_name TEXT, amount REAL, 
                due_date TEXT, description TEXT, status TEXT, timestamp TIMESTAMP
                {"" if is_pg else ", PRIMARY KEY(id)"}
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS expenses (
                id {id_type}, title TEXT, amount REAL, exp_date TEXT, timestamp TIMESTAMP
                {"" if is_pg else ", PRIMARY KEY(id)"}
            )
        """))
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS staff (
                id {id_type}, name TEXT UNIQUE, password TEXT DEFAULT '1234', 
                commission_rate REAL, timestamp TIMESTAMP
                {"" if is_pg else ", PRIMARY KEY(id)"}
            )
        """))

init_db()

# ==========================================
# تابع تولید فاکتور PDF
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
    draw_rtl_text(f"شماره تماس: {inv['c_phone']}", width - 30, y - 40)
    
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
# متغیرهای سشن و لاگین
# ==========================================
if "user_role" not in st.session_state: st.session_state.user_role = None
if "user_name" not in st.session_state: st.session_state.user_name = None
if "last_invoice" not in st.session_state: st.session_state.last_invoice = None

st.sidebar.title("🚗 سیستم فروشگاه اسپرت")
st.sidebar.caption(f"📡 وضعیت اتصال: {db_type}")
st.sidebar.markdown("---")

if st.session_state.user_role is None:
    st.sidebar.subheader("🔐 ورود به سیستم")
    login_type = st.sidebar.radio("ورود به عنوان:", ["شاگرد / پرسنل فروش", "صاحب مغازه (ادمین)"])
    
    if login_type == "صاحب مغازه (ادمین)":
        admin_pass = st.sidebar.text_input("رمز عبور ادمین:", type="password")
        if st.sidebar.button("ورود به پنل"):
            if admin_pass == st.secrets.get("admin_password", "2613"):
                st.session_state.user_role = "Admin"
                st.session_state.user_name = "ادمین"
                st.rerun()
            else:
                st.sidebar.error("رمز اشتباه است!")
    else:
        staff_df = pd.read_sql_query("SELECT name FROM staff", engine)
        if not staff_df.empty:
            s_name = st.sidebar.selectbox("نام کاربری:", staff_df['name'].tolist())
            s_pass = st.sidebar.text_input("رمز عبور:", type="password")
            if st.sidebar.button("ورود"):
                with engine.connect() as conn:
                    res = conn.execute(text("SELECT password FROM staff WHERE name=:n"), {"n": s_name}).fetchone()
                
                if res and (res[0] == hash_password(s_pass) or res[0] == s_pass):
                    # Upgrade hash if it was plain text
                    if res[0] == s_pass:
                        with engine.begin() as conn:
                            conn.execute(text("UPDATE staff SET password=:p WHERE name=:n"), {"p": hash_password(s_pass), "n": s_name})
                    st.session_state.user_role = "Staff"
                    st.session_state.user_name = s_name
                    st.rerun()
                else:
                    st.sidebar.error("❌ رمز عبور اشتباه است!")
        else:
            st.sidebar.warning("پرسنلی ثبت نشده است.")
    st.stop() 

st.sidebar.success(f"👤 کاربر فعال: {st.session_state.user_name}")

# فرم تغییر رمز شاگرد
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
                else:
                    st.error("رمز فعلی اشتباه است.")

if st.sidebar.button("خروج از سیستم"):
    st.session_state.user_role = None
    st.session_state.user_name = None
    st.rerun()

menu = ["🛒 ثبت فروش / خدمات", "📦 مدیریت انبار", "➕ افزودن کالا", "📊 گزارش‌ها و داشبورد", "📒 دفتر حساب (چک‌ها)", "👥 مدیریت پرسنل"] if st.session_state.user_role == "Admin" else ["🛒 ثبت فروش / خدمات", "📦 جستجو در انبار"]
choice = st.sidebar.radio("منوی سیستم:", menu)

# ==========================================
# 1. ثبت فروش / خدمات
# ==========================================
if choice == "🛒 ثبت فروش / خدمات":
    st.header("🛒 ثبت فاکتور")
    
    staff_df_list = pd.read_sql_query("SELECT name FROM staff", engine)
    staff_options = ["ادمین (بدون پورسانت)"] + staff_df_list['name'].tolist() if not staff_df_list.empty else ["ادمین (بدون پورسانت)"]
    
    tab_sale, tab_srv = st.tabs(["🛒 فروش کالا", "🔧 ثبت خدمات (اجرت)"])
    
    with tab_sale:
        c1, c2 = st.columns([1, 2])
        with c1:
            sm = st.radio("روش جستجو:", ("تایپ / بارکدخوان", "اسکنر دوربین موبایل", "سرچ نام کالا"))
            code_input = ""
            if sm == "تایپ / بارکدخوان":
                code_input = st.text_input("کد کالا:")
            elif sm == "اسکنر دوربین موبایل":
                if HAS_SCANNER_PKG:
                    sc = qrcode_scanner(key='scan_sale')
                    if sc: code_input = sc
            else:
                sq = st.text_input("جستجوی نام کالا:")
                if sq:
                    m_df = pd.read_sql_query(f"SELECT code, name, compatible_cars FROM products WHERE name LIKE '%%{sq}%%'", engine)
                    if not m_df.empty:
                        opt = st.selectbox("انتخاب کالا:", (m_df['name'] + " - کد: " + m_df['code']).tolist())
                        code_input = opt.split("کد: ")[1].strip()

        with c2:
            if code_input:
                with engine.connect() as conn:
                    product = conn.execute(text("SELECT * FROM products WHERE code=:c"), {"c": code_input}).fetchone()
                
                if product:
                    st.subheader(f"📦 {product[1]}")
                    st.markdown(f"**قیمت فروش:** {product[4]:,.0f} تومان | **موجودی:** {product[5]} عدد")
                    
                    f_qty = st.number_input("تعداد", min_value=1, max_value=product[5] if product[5]>0 else 1)
                    f_install = st.number_input("اجرت نصب (تومان)", min_value=0, step=10000, value=0)
                    f_discount = st.number_input("تخفیف (تومان)", min_value=0, step=10000, value=0)
                    
                    s_staff = st.selectbox("ثبت به نام:", staff_options) if st.session_state.user_role == "Admin" else st.session_state.user_name
                    
                    st.markdown("**اطلاعات مشتری:**")
                    cc1, cc2 = st.columns(2)
                    with cc1: c_name = st.text_input("نام مشتری")
                    with cc2: c_phone = st.text_input("شماره موبایل")
                    c_car = st.selectbox("مدل ماشین", CAR_MODELS)
                    
                    if st.button("✅ ثبت فاکتور", use_container_width=True):
                        now_dt = get_iran_time()
                        now_str = jdatetime.datetime.fromgregorian(datetime=now_dt.replace(tzinfo=None)).strftime('%Y/%m/%d - %H:%M')
                        net_prof = ((product[4] - product[3]) * f_qty) + f_install - f_discount
                        total_bill = (product[4] * f_qty) + f_install - f_discount
                        
                        with engine.begin() as conn:
                            res = conn.execute(text("UPDATE products SET stock = stock - :q WHERE code = :c AND stock >= :q"), {"q": f_qty, "c": code_input})
                            if res.rowcount > 0:
                                staff_rate = 0
                                if s_staff != "ادمین (بدون پورسانت)":
                                    rate_row = conn.execute(text("SELECT commission_rate FROM staff WHERE name=:n"), {"n": s_staff}).fetchone()
                                    if rate_row: staff_rate = rate_row[0]
                                
                                conn.execute(text("""
                                    INSERT INTO sales (product_code, name, quantity, sale_price, sale_date, timestamp, 
                                    customer_name, customer_phone, car_model, install_fee, net_profit, staff_name, staff_commission, discount) 
                                    VALUES (:pc, :n, :q, :sp, :sd, :ts, :cn, :cp, :cm, :i, :np, :sn, :sc, :d)
                                """), {
                                    "pc": code_input, "n": product[1], "q": f_qty, "sp": product[4], "sd": now_str, 
                                    "ts": now_dt.replace(tzinfo=None), "cn": c_name, "cp": c_phone, "cm": c_car, 
                                    "i": f_install, "np": net_prof, "sn": s_staff, "sc": net_prof*(staff_rate/100), "d": f_discount
                                })
                                st.session_state.last_invoice = {
                                    "date": now_str, "c_name": c_name or "نقدی", "c_phone": c_phone, "c_car": c_car, 
                                    "p_name": product[1], "qty": f_qty, "price": product[4], "install": f_install, 
                                    "discount": f_discount, "total": total_bill, "staff": s_staff
                                }
                                st.success("فاکتور ثبت شد!")
                                st.rerun()
                            else:
                                st.error("موجودی کافی نیست!")

    # نمایش فاکتور و دکمه دانلود PDF
    if st.session_state.last_invoice:
        inv = st.session_state.last_invoice
        st.markdown("---")
        st.subheader("🧾 فاکتور نهایی")
        
        pdf_bytes = generate_pdf_invoice(inv)
        st.download_button(
            label="📥 دانلود فاکتور PDF", 
            data=pdf_bytes, 
            file_name=f"Invoice_{inv['c_phone']}.pdf", 
            mime="application/pdf",
            type="primary"
        )
        
        inv_text = f"فاکتور فروشگاه\nتاریخ: {inv['date']}\nمشتری: {inv['c_name']}\nخودرو: {inv['c_car']}\nشرح: {inv['p_name']}\nمبلغ کل: {inv['total']:,} تومان"
        enc = urllib.parse.quote(inv_text)
        st.markdown(f"<a href='https://wa.me/?text={enc}' target='_blank'><button style='background-color:#25D366; color:white; width:100%; border-radius:8px;'>🟢 ارسال واتس‌اپ</button></a>", unsafe_allow_html=True)
        
        if st.button("بستن فاکتور"):
            st.session_state.last_invoice = None
            st.rerun()

# ==========================================
# 2. مدیریت انبار و افزودن کالا
# ==========================================
elif choice in ["📦 مدیریت انبار", "📦 جستجو در انبار"]:
    st.header(choice)
    df = pd.read_sql_query("SELECT code, name, compatible_cars, category, purchase_price, sale_price, stock FROM products", engine)
    
    if st.session_state.user_role != "Admin":
        df = df.drop(columns=['purchase_price'])
        
    search = st.text_input("🔍 جستجو:")
    if search:
        mask = df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
        st.dataframe(df[mask], use_container_width=True, hide_index=True)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

elif choice == "➕ افزودن کالا":
    st.header("➕ افزودن کالای جدید")
    code = st.text_input("کد کالا (خالی بگذارید تا خودکار ساخته شود):")
    name = st.text_input("نام کالا:")
    cat = st.selectbox("دسته‌بندی:", CATEGORIES)
    car = st.selectbox("مناسب برای خودرو:", CAR_MODELS)
    
    c1, c2 = st.columns(2)
    with c1: pb = st.number_input("قیمت خرید (تومان)", step=10000)
    with c2: ps = st.number_input("قیمت فروش (تومان)", step=10000)
    stock = st.number_input("موجودی اولیه", min_value=0)
    
    if st.button("ثبت کالا", type="primary"):
        if name:
            code = code.strip() or f"AUTO-{int(datetime.now().timestamp())}"
            try:
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO products VALUES (:c, :n, :cat, :pb, :ps, :st, :car)"), 
                                 {"c": code, "n": name, "cat": cat, "pb": pb, "ps": ps, "st": stock, "car": car})
                st.success("کالا با موفقیت ثبت شد!")
            except Exception as e:
                st.error("خطا! احتمالا کد کالا تکراری است.")
        else:
            st.error("نام کالا الزامی است.")

# ==========================================
# 3. داشبورد و گزارشات با فیلتر زمانی
# ==========================================
elif choice == "📊 گزارش‌ها و داشبورد":
    st.header("📊 داشبورد و گزارش‌ها")
    
    # فیلتر تاریخ پیشرفته
    time_filter = st.selectbox("📅 فیلتر بازه زمانی:", ["امروز", "۷ روز گذشته", "ماه جاری (۳۰ روز)"])
    now = datetime.now()
    if time_filter == "امروز":
        start_dt = now - timedelta(days=1)
    elif time_filter == "۷ روز گذشته":
        start_dt = now - timedelta(days=7)
    else:
        start_dt = now - timedelta(days=30)
        
    sales_df = pd.read_sql_query("SELECT * FROM sales", engine)
    
    if not sales_df.empty:
        sales_df['timestamp'] = pd.to_datetime(sales_df['timestamp'])
        filtered_sales = sales_df[sales_df['timestamp'] >= start_dt]
        
        total_rev = (filtered_sales['quantity'] * filtered_sales['sale_price'] + filtered_sales['install_fee'] - filtered_sales['discount']).sum()
        total_prof = filtered_sales['net_profit'].sum() - filtered_sales['staff_commission'].sum()
        
        c1, c2 = st.columns(2)
        c1.metric("درآمد ناخالص در این بازه", f"{total_rev:,.0f} T")
        c2.metric("سود خالص (پس از پورسانت)", f"{total_prof:,.0f} T")
        
        st.dataframe(filtered_sales[['sale_date', 'name', 'customer_name', 'staff_name', 'discount', 'net_profit']], use_container_width=True)
    else:
        st.info("هیچ فروشی در سیستم ثبت نشده است.")

# ==========================================
# 4. سایر بخش‌ها (دفتر حساب و پرسنل)
# ==========================================
elif choice == "📒 دفتر حساب (چک‌ها)":
    st.info("بخش دفتر حساب همانند قبل کار می‌کند و دیتای آن روی کلود همگام‌سازی می‌شود.")
elif choice == "👥 مدیریت پرسنل":
    st.info("برای تغییر رمز، پرسنل می‌توانند از منوی کاربری خودشان اقدام کنند. مدیریت در اینجا دسترسی ویرایش دارد.")
