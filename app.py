import streamlit as st
import sqlite3
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
import json

# ایمپورت اسکنر حرفه‌ای
try:
    from streamlit_qrcode_scanner import qrcode_scanner
    HAS_SCANNER_PKG = True
except ImportError:
    HAS_SCANNER_PKG = False

# ==========================================
# تنظیمات صفحه
# ==========================================
st.set_page_config(page_title="سیستم یکپارچه فروشگاه اسپرت", page_icon="🚗", layout="wide")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {background-color: transparent !important;}
    
    .stMarkdown, p, h1, h2, h3, h4, label { direction: rtl; text-align: right; font-family: 'Tahoma', sans-serif !important; }
    .stButton>button { width: 100%; border-radius: 8px; }
    .invoice-box { border: 2px dashed #4CAF50; padding: 20px; border-radius: 10px; background-color: #f9f9f9; color: #333; margin-top: 15px; direction: rtl; text-align: right; }
    .metric-box { padding: 15px; border-radius: 10px; background-color: #e8f5e9; border: 1px solid #4CAF50; margin-bottom: 20px; text-align: center; font-size: 20px; font-weight: bold; color: #2e7d32; }
</style>
""", unsafe_allow_html=True)

def get_iran_time():
    iran_tz = pytz.timezone('Asia/Tehran')
    return datetime.now(iran_tz)

def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def get_admin_password():
    try:
        return st.secrets["admin_password"]
    except Exception:
        return "2613"

def get_telegram_secrets():
    try:
        return st.secrets.get("telegram_token", ""), st.secrets.get("telegram_chat_id", "")
    except Exception:
        return "", ""

def send_telegram_msg(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({'chat_id': chat_id, 'text': text}).encode('utf-8')
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=5)
        return True
    except:
        return False

def hash_password(raw_password):
    return hashlib.sha256(str(raw_password).encode("utf-8")).hexdigest()

def verify_staff_password(input_password, stored_password):
    if stored_password == hash_password(input_password):
        return True, False
    if stored_password == input_password:
        return True, True
    return False, False

# ==========================================
# توابع دیتابیس
# ==========================================
DB_NAME = "inventory.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (code TEXT PRIMARY KEY, name TEXT, category TEXT, purchase_price REAL, sale_price REAL, stock INTEGER)''')
    c.execute("PRAGMA table_info(products)")
    cols = [col[1] for col in c.fetchall()]
    if 'compatible_cars' not in cols:
        c.execute("ALTER TABLE products ADD COLUMN compatible_cars TEXT DEFAULT 'عمومی'")

    c.execute('''CREATE TABLE IF NOT EXISTS sales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT, name TEXT, quantity INTEGER,
                  sale_price REAL, sale_date TEXT, timestamp DATETIME)''')
    c.execute("PRAGMA table_info(sales)")
    sales_cols = [col[1] for col in c.fetchall()]
    if 'customer_name' not in sales_cols:
        c.execute("ALTER TABLE sales ADD COLUMN customer_name TEXT DEFAULT ''")
        c.execute("ALTER TABLE sales ADD COLUMN customer_phone TEXT DEFAULT ''")
        c.execute("ALTER TABLE sales ADD COLUMN car_model TEXT DEFAULT ''")
        c.execute("ALTER TABLE sales ADD COLUMN install_fee REAL DEFAULT 0")
        c.execute("ALTER TABLE sales ADD COLUMN net_profit REAL DEFAULT 0")
    if 'staff_name' not in sales_cols:
        c.execute("ALTER TABLE sales ADD COLUMN staff_name TEXT DEFAULT 'ادمین (بدون پورسانت)'")
        c.execute("ALTER TABLE sales ADD COLUMN staff_commission REAL DEFAULT 0")
    if 'discount' not in sales_cols:
        c.execute("ALTER TABLE sales ADD COLUMN discount REAL DEFAULT 0")

    c.execute('''CREATE TABLE IF NOT EXISTS ledger
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, record_type TEXT, person_name TEXT, amount REAL, due_date TEXT, description TEXT, status TEXT, timestamp DATETIME)''')
    c.execute('''CREATE TABLE IF NOT EXISTS expenses
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, amount REAL, exp_date TEXT, timestamp DATETIME)''')
                 
    c.execute('''CREATE TABLE IF NOT EXISTS staff
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, commission_rate REAL, timestamp DATETIME)''')
    c.execute("PRAGMA table_info(staff)")
    staff_cols_db = [col[1] for col in c.fetchall()]
    if 'password' not in staff_cols_db:
        c.execute("ALTER TABLE staff ADD COLUMN password TEXT DEFAULT '1234'")
    
    conn.commit()
    conn.close()

def get_low_stock_products():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT name, stock FROM products WHERE stock < 3", conn)
    conn.close()
    return df

def get_pending_ledgers():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT record_type, person_name, amount, due_date FROM ledger WHERE status='معلق'", conn)
    conn.close()
    return df

init_db()

# ==========================================
# مدیریت وضعیت سیستم و لاگین
# ==========================================
if "user_role" not in st.session_state: st.session_state.user_role = None
if "user_name" not in st.session_state: st.session_state.user_name = None
if "last_invoice" not in st.session_state: st.session_state.last_invoice = None
if "scanned_add_code" not in st.session_state: st.session_state.scanned_add_code = ""

st.sidebar.title("🚗 سیستم فروشگاه اسپرت")
st.sidebar.markdown("---")

# 🔒 سیستم احراز هویت
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
        conn = sqlite3.connect(DB_NAME)
        staff_df = pd.read_sql_query("SELECT name FROM staff", conn)
        conn.close()
        
        if not staff_df.empty:
            staff_name_input = st.sidebar.selectbox("نام خود را انتخاب کنید:", staff_df['name'].tolist())
            staff_pass_input = st.sidebar.text_input("رمز عبور خود را وارد کنید:", type="password")
            
            if st.sidebar.button("ورود به پنل فروش"):
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("SELECT password FROM staff WHERE name=?", (staff_name_input,))
                res = c.fetchone()
                conn.close()
                
                is_valid, needs_upgrade = verify_staff_password(staff_pass_input, res[0]) if res else (False, False)
                if is_valid:
                    if needs_upgrade:
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        c.execute("UPDATE staff SET password=? WHERE name=?", (hash_password(staff_pass_input), staff_name_input))
                        conn.commit()
                        conn.close()
                    st.session_state.user_role = "Staff"
                    st.session_state.user_name = staff_name_input
                    st.rerun()
                else:
                    st.sidebar.error("❌ رمز عبور اشتباه است!")
        else:
            st.sidebar.warning("هنوز هیچ شاگردی ثبت نشده است! ابتدا صاحب مغازه باید شاگردها را تعریف کند.")

    st.title("🛡️ به نرم‌افزار جامع فروشگاه خوش آمدید")
    st.info("👈 برای شروع کار، لطفاً از منوی سمت چپ وارد حساب کاربری خود شوید.")
    st.stop() 

# اگر لاگین شده بود:
st.sidebar.success(f"👤 کاربر فعال: {st.session_state.user_name}")
if st.sidebar.button("خروج از سیستم"):
    st.session_state.user_role = None
    st.session_state.user_name = None
    st.rerun()

st.sidebar.markdown("---")
if st.session_state.user_role == "Admin":
    menu = ["🛒 ثبت فروش / خدمات", "📦 مدیریت انبار", "➕ افزودن کالا", "📊 گزارش‌ها و داشبورد", "📒 دفتر حساب (چک‌ها)", "👥 مدیریت پرسنل (شاگردان)"]
else:
    menu = ["🛒 ثبت فروش / خدمات", "📦 جستجو در انبار"]

choice = st.sidebar.radio("منوی اختصاصی شما:", menu)

if st.session_state.user_role == "Admin":
    st.sidebar.markdown("---")
    if os.path.exists(DB_NAME):
        with open(DB_NAME, "rb") as file:
            st.sidebar.download_button(label="💾 دانلود بک‌آپ دیتابیس", data=file, file_name=f"Backup_{datetime.now().strftime('%Y%m%d')}.db", mime="application/octet-stream")
    st.sidebar.caption("⚠️ اگه این اپ روی Streamlit Community Cloud دیپلوی شده، این فایل با هر ریدیپلوی/ریستارت ممکنه پاک بشه. مرتب بک‌آپ بگیر یا به یه دیتابیس ابری پایدار وصل شو.")
            
    low_stock_df = get_low_stock_products()
    if not low_stock_df.empty:
        st.sidebar.error("⚠️ کمبود موجودی انبار:")
        for _, row in low_stock_df.iterrows():
            st.sidebar.warning(f"{row['name']} ({row['stock']} عدد)")

    pending_df = get_pending_ledgers()
    if not pending_df.empty:
        st.sidebar.error("📅 وضعیت چک‌ها و حساب‌های باز:")
        today_jalali = jdatetime.date.today()
        
        for _, row in pending_df.iterrows():
            l_type = "طلب از:" if row['record_type'] == 'customer_debt' else "بدهی به:"
            due_date_str = row['due_date']
            
            try:
                due_date_obj = jdatetime.datetime.strptime(due_date_str, '%Y/%m/%d').date()
                diff_days = (due_date_obj - today_jalali).days
                
                if diff_days < 0:
                    st.sidebar.error(f"🚨 گذشته! {l_type} {row['person_name']}\nمبلغ: {row['amount']:,.0f} T\n({abs(diff_days)} روز تاخیر)")
                elif diff_days <= 2:
                    st.sidebar.warning(f"⚠️ فوری! {l_type} {row['person_name']}\nمبلغ: {row['amount']:,.0f} T\nسررسید: {due_date_str}")
                else:
                    st.sidebar.info(f"عادی: {l_type} {row['person_name']}\nمبلغ: {row['amount']:,.0f} T\nسررسید: {due_date_str}")
            except (ValueError, TypeError):
                st.sidebar.info(f"{l_type} {row['person_name']}\nمبلغ: {row['amount']:,.0f} T\nسررسید: {due_date_str}")

# ==========================================
# بخش 1: ثبت فروش، خدمات و مرجوعی
# ==========================================
if choice == "🛒 ثبت فروش / خدمات":
    st.header("🛒 ثبت فاکتور مشتری")
    
    conn = sqlite3.connect(DB_NAME)
    staff_df_list = pd.read_sql_query("SELECT name FROM staff", conn)
    vip_df = pd.read_sql_query("SELECT DISTINCT customer_name, customer_phone, car_model FROM sales WHERE customer_name != '' OR customer_phone != ''", conn)
    conn.close()
    
    staff_options = ["ادمین (بدون پورسانت)"] + staff_df_list['name'].tolist() if not staff_df_list.empty else ["ادمین (بدون پورسانت)"]
    if not vip_df.empty:
        vip_df.fillna('', inplace=True)

    tab_sale, tab_service, tab_refund = st.tabs(["🛒 فروش قطعه و کالا", "🔧 ثبت خدمات (بدون کالا)", "🔄 مرجوعی کالا"])
    
    with tab_sale:
        col1, col2 = st.columns([1, 2])
        with col1:
            scan_method = st.radio("روش جستجو:", ("دوربین (اسکنر خودکار)", "کیبورد / بارکدخوان فیزیکی", "جستجوی نام کالا"))
            code_input = ""
            
            if scan_method == "کیبورد / بارکدخوان فیزیکی":
                code_input = st.text_input("کد کالا را وارد/اسکن کنید:", key="barcode_input_sale")
            elif scan_method == "دوربین (اسکنر خودکار)":
                if HAS_SCANNER_PKG:
                    scanned_code = qrcode_scanner(key='pro_scanner_sale')
                    if scanned_code: code_input = scanned_code
                else: st.error("اسکنر نصب نیست.")
            elif scan_method == "جستجوی نام کالا":
                search_q = st.text_input("نام کالا یا ماشین:")
                if search_q:
                    conn = sqlite3.connect(DB_NAME)
                    m_df = pd.read_sql_query(
                        "SELECT code, name, compatible_cars FROM products WHERE name LIKE ? OR compatible_cars LIKE ?",
                        conn, params=(f"%{search_q}%", f"%{search_q}%")
                    )
                    conn.close()
                    if not m_df.empty:
                        opts = (m_df['name'] + " (مناسب: " + m_df['compatible_cars'] + ") - کد: " + m_df['code']).tolist()
                        code_input = st.selectbox("انتخاب کالا:", opts).split("کد: ")[1].strip()

        with col2:
            if code_input:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("SELECT * FROM products WHERE code=?", (code_input,))
                product = c.fetchone()
                conn.close()

                if product:
                    st.subheader(f"📦 {product[1]}")
                    st.markdown(f"**قیمت فروش:** {product[4]:,.0f} تومان | **موجودی:** {product[5]} عدد")
                    
                    st.markdown("---")
                    st.markdown("📝 **اطلاعات ثبت فاکتور**")
                    f_qty = st.number_input("تعداد", min_value=1, max_value=product[5] if product[5]>0 else 1)
                    
                    f_install = st.number_input("اجرت نصب (تومان)", min_value=0, step=10000, value=0)
                    if f_install >= 0:
                        st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#2e7d32; font-weight:bold; font-size: 14px;'>💳 معادل: {f_install:,.0f} تومان</div>", unsafe_allow_html=True)
                    
                    max_discount = int((product[4] * f_qty) + f_install)
                    f_discount = st.number_input("مبلغ تخفیف (تومان)", min_value=0, max_value=max_discount, step=10000, value=0)
                    if f_discount >= 0:
                        st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#d32f2f; font-weight:bold; font-size: 14px;'>🎁 معادل تخفیف: {f_discount:,.0f} تومان</div>", unsafe_allow_html=True)
                    
                    if st.session_state.user_role == "Admin":
                        s_staff = st.selectbox("👷‍♂️ ثبت به نام (جهت پورسانت):", staff_options)
                    else:
                        s_staff = st.session_state.user_name
                        st.info(f"👷‍♂️ فاکتور به نام شما ({s_staff}) ثبت می‌شود.")
                    
                    # 🌟 ارتقای قطعی برای موبایل: جستجوی متنی خالص (بدون منوی انتخابی)
                    st.markdown("---")
                    st.markdown("🔍 **تکمیل خودکار اطلاعات مشتری**")
                    vip_search_q = st.text_input("⌨️ شماره موبایل (مثلاً 0935) یا نام مشتری را تایپ کرده و Enter بزنید:", key="vip_search_sale")
                    
                    c_name_val, c_phone_val, c_car_val = "", "", ""
                    if vip_search_q and not vip_df.empty:
                        match = vip_df[(vip_df['customer_phone'].astype(str).str.contains(vip_search_q, case=False, na=False)) | 
                                       (vip_df['customer_name'].astype(str).str.contains(vip_search_q, case=False, na=False))]
                        if not match.empty:
                            c_info = match.iloc[0]
                            c_name_val, c_phone_val, c_car_val = str(c_info['customer_name']), str(c_info['customer_phone']), str(c_info['car_model'])
                            st.success(f"✅ مشتری پیدا شد: {c_name_val} - {c_phone_val}")
                        else:
                            st.warning("⚠️ مشتری با این مشخصات در سیستم یافت نشد.")

                    cc1, cc2 = st.columns(2)
                    with cc1: c_name = st.text_input("نام مشتری (اختیاری)", value=c_name_val, key="name_s")
                    with cc2: c_phone = st.text_input("شماره موبایل (اختیاری)", value=c_phone_val, key="phone_s")
                    c_car = st.text_input("مدل ماشین", value=c_car_val, key="car_s")

                    if st.button("✅ ثبت نهایی فاکتور کالا", use_container_width=True):
                        now_dt = get_iran_time()
                        now_str = jdatetime.datetime.fromgregorian(datetime=now_dt).strftime('%Y/%m/%d - %H:%M')

                        net_prof = ((product[4] - product[3]) * f_qty) + f_install - f_discount
                        total_bill = (product[4] * f_qty) + f_install - f_discount

                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        c.execute("UPDATE products SET stock = stock - ? WHERE code = ? AND stock >= ?", (f_qty, code_input, f_qty))
                        if c.rowcount == 0:
                            conn.close()
                            st.error("موجودی کافی نیست! (شاید هم‌زمان توسط شخص دیگری فروخته شده)")
                        else:
                            staff_rate = 0
                            if s_staff != "ادمین (بدون پورسانت)":
                                c.execute("SELECT commission_rate FROM staff WHERE name=?", (s_staff,))
                                res = c.fetchone()
                                if res: staff_rate = res[0]
                            staff_comm = net_prof * (staff_rate / 100.0) if net_prof > 0 else 0

                            c.execute('''INSERT INTO sales (product_code, name, quantity, sale_price, sale_date, timestamp, customer_name, customer_phone, car_model, install_fee, net_profit, staff_name, staff_commission, discount) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                                      (code_input, product[1], f_qty, product[4], now_str, now_dt, c_name, c_phone, c_car, f_install, net_prof, s_staff, staff_comm, f_discount))
                            conn.commit()
                            conn.close()

                            st.session_state.last_invoice = {"date":now_str, "c_name":c_name or "نقدی", "c_phone":c_phone, "c_car":c_car, "p_name":product[1], "qty":f_qty, "price":product[4], "install":f_install, "discount":f_discount, "total":total_bill, "staff":s_staff}
                            st.success("فروش ثبت شد!")
                            st.rerun()
                else:
                    st.warning("کالایی یافت نشد.")

    with tab_service:
        st.info("در این بخش می‌توانید اجرت نصب و تعمیرات را بدون فروش کالا ثبت کنید.")
        s_name = st.text_input("شرح خدمات (مثال: نصب سیستم صوتی)")
        
        s_fee = st.number_input("مبلغ اجرت (تومان)", min_value=0, step=50000)
        if s_fee >= 0:
            st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#2e7d32; font-weight:bold; font-size: 14px;'>💳 معادل: {s_fee:,.0f} تومان</div>", unsafe_allow_html=True)
        
        if st.session_state.user_role == "Admin":
            s_staff_srv = st.selectbox("👷‍♂️ ثبت به نام نصاب:", staff_options, key="staff_srv")
        else:
            s_staff_srv = st.session_state.user_name
            st.info(f"👷‍♂️ فاکتور خدمات به نام شما ({s_staff_srv}) ثبت می‌شود.")
        
        # 🌟 ارتقای جستجوی متنی خالص برای بخش خدمات
        st.markdown("---")
        st.markdown("🔍 **تکمیل خودکار اطلاعات مشتری**")
        vip_search_q_srv = st.text_input("⌨️ شماره موبایل (مثلاً 0935) یا نام مشتری را تایپ کرده و Enter بزنید:", key="vip_search_srv")
        
        cs_name_val, cs_phone_val, cs_car_val = "", "", ""
        if vip_search_q_srv and not vip_df.empty:
            match_srv = vip_df[(vip_df['customer_phone'].astype(str).str.contains(vip_search_q_srv, case=False, na=False)) | 
                               (vip_df['customer_name'].astype(str).str.contains(vip_search_q_srv, case=False, na=False))]
            if not match_srv.empty:
                c_info_srv = match_srv.iloc[0]
                cs_name_val, cs_phone_val, cs_car_val = str(c_info_srv['customer_name']), str(c_info_srv['customer_phone']), str(c_info_srv['car_model'])
                st.success(f"✅ مشتری پیدا شد: {cs_name_val} - {cs_phone_val}")
            else:
                st.warning("⚠️ مشتری با این مشخصات در سیستم یافت نشد.")

        sc1, sc2 = st.columns(2)
        with sc1: s_cname = st.text_input("نام مشتری", value=cs_name_val, key="cname_srv_input")
        with sc2: s_cphone = st.text_input("شماره موبایل", value=cs_phone_val, key="cphone_srv_input")
        s_ccar = st.text_input("مدل خودرو", value=cs_car_val, key="ccar_srv_input")
        
        if st.button("🔧 ثبت خدمات", use_container_width=True):
            if s_name and s_fee > 0:
                now_dt = get_iran_time()
                now_str = jdatetime.datetime.fromgregorian(datetime=now_dt).strftime('%Y/%m/%d - %H:%M')
                
                staff_rate = 0
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                if s_staff_srv != "ادمین (بدون پورسانت)":
                    c.execute("SELECT commission_rate FROM staff WHERE name=?", (s_staff_srv,))
                    res = c.fetchone()
                    if res: staff_rate = res[0]
                staff_comm = s_fee * (staff_rate / 100.0)
                
                c.execute('''INSERT INTO sales (product_code, name, quantity, sale_price, sale_date, timestamp, customer_name, customer_phone, car_model, install_fee, net_profit, staff_name, staff_commission, discount) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                          ('SERVICE', s_name, 0, 0, now_str, now_dt, s_cname, s_cphone, s_ccar, s_fee, s_fee, s_staff_srv, staff_comm, 0))
                conn.commit()
                conn.close()
                st.session_state.last_invoice = {"date":now_str, "c_name":s_cname or "نقدی", "c_phone":s_cphone, "c_car":s_ccar, "p_name":s_name, "qty":0, "price":0, "install":s_fee, "discount":0, "total":s_fee, "staff":s_staff_srv}
                st.success("خدمات ثبت شد!")
                st.rerun()
            else:
                st.error("شرح و مبلغ الزامی است.")
                
    with tab_refund:
        st.info("🔄 در این بخش می‌توانید فاکتورهای اشتباه یا اجناس مرجوعی را باطل کنید. با این کار، جنس به انبار برمی‌گردد و از صندوق مالی کسر می‌شود.")
        if st.session_state.user_role == "Admin":
            conn = sqlite3.connect(DB_NAME)
            recent_sales = pd.read_sql_query("SELECT id, product_code as 'کد کالا', name as 'شرح', quantity as 'تعداد', sale_date as 'تاریخ', customer_name as 'مشتری', staff_name as 'پرسنل' FROM sales ORDER BY id DESC LIMIT 30", conn)
            conn.close()
            
            if not recent_sales.empty:
                st.markdown("**آخرین فاکتورهای صادر شده:**")
                st.dataframe(recent_sales, hide_index=True, use_container_width=True)
                
                st.markdown("---")
                refund_id = st.number_input("کد ردیف فاکتور (id) جهت مرجوعی و ابطال را وارد کنید:", min_value=0, step=1)
                confirm_refund = st.checkbox("تایید می‌کنم که این فاکتور باطل و کالا به انبار مرجوع شود.")
                
                if st.button("🗑️ ابطال فاکتور و بازگشت به انبار", disabled=not confirm_refund, type="primary", use_container_width=True):
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("SELECT product_code, quantity FROM sales WHERE id=?", (refund_id,))
                    sale_rec = c.fetchone()
                    if sale_rec:
                        p_code, p_qty = sale_rec
                        if p_code != 'SERVICE':
                            c.execute("UPDATE products SET stock = stock + ? WHERE code=?", (p_qty, p_code))
                        c.execute("DELETE FROM sales WHERE id=?", (refund_id,))
                        conn.commit()
                        st.success("✅ فاکتور با موفقیت باطل شد و موجودی به انبار بازگشت.")
                    else:
                        st.error("فاکتوری با این کد یافت نشد.")
                    conn.close()
                    st.rerun()
            else:
                st.warning("هیچ فاکتوری جهت مرجوعی وجود ندارد.")
        else:
            st.error("🔒 فقط صاحب مغازه (ادمین) دسترسی به ابطال و مرجوعی فاکتورها را دارد.")

    if st.session_state.last_invoice:
        inv = st.session_state.last_invoice
        st.markdown("---")
        st.subheader("🧾 فاکتور مشتری")
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
# بخش 2: انبار و هشدار کسری لیست خرید
# ==========================================
elif choice == "📦 مدیریت انبار" or choice == "📦 جستجو در انبار":
    st.header("📦 انبار مرکزی" if choice == "📦 مدیریت انبار" else "📦 جستجوی کالاها")
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT code as 'کد', name as 'نام', compatible_cars as 'ماشین', category as 'دسته', purchase_price as 'خرید', sale_price as 'فروش', stock as 'موجودی' FROM products", conn)
    conn.close()

    if st.session_state.user_role != "Admin":
        df = df.drop(columns=['خرید'])

    st.subheader("📋 جستجوی پیشرفته")
    sc1, sc2 = st.columns([2, 1])
    with sc1: search = st.text_input("🔍 سرچ (نام، ماشین، دسته یا کد):")
    with sc2: scan_chk = st.checkbox("فعال‌سازی اسکنر")
    
    q_code = ""
    if scan_chk and HAS_SCANNER_PKG:
        scanned_inv = qrcode_scanner(key='inv_scan')
        if scanned_inv: q_code = scanned_inv
        
    dsp_df = df.copy()
    if search:
        mask = dsp_df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
        dsp_df = dsp_df[mask]
    elif q_code:
        dsp_df = dsp_df[dsp_df['کد'] == q_code]

    st.dataframe(dsp_df, use_container_width=True, hide_index=True)
    
    if st.session_state.user_role == "Admin" and not dsp_df.empty:
        excel_data = convert_df_to_excel(dsp_df)
        st.download_button(label="📥 دانلود لیست کل انبار (فایل Excel)", data=excel_data, file_name=f"Inventory_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    if st.session_state.user_role == "Admin":
        st.markdown("---")
        out_df = df[df['موجودی'] < 3]
        if not out_df.empty:
            st.error(f"⚠️ تعداد {len(out_df)} کالا موجودی صفر یا رو به اتمام (زیر ۳ عدد) دارند:")
            st.dataframe(out_df, use_container_width=True, hide_index=True)
            reorder_excel = convert_df_to_excel(out_df)
            st.download_button(label="🛒 دانلود لیست کسری‌ها (جهت سفارش به عمده‌فروش)", data=reorder_excel, file_name=f"Reorder_List_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            
        st.markdown("---")
        st.subheader("🛠️ ویرایش / حذف کالا (مختص ادمین)")
        e_mode = st.radio("روش انتخاب:", ("جستجوی نام/کد", "اسکن با دوربین"), horizontal=True)
        e_code = ""
        if e_mode == "جستجوی نام/کد":
            s_query = st.text_input("بخشی از نام یا کد را سرچ کنید:")
            if s_query:
                conn = sqlite3.connect(DB_NAME)
                m_df = pd.read_sql_query(
                    "SELECT code, name FROM products WHERE name LIKE ? OR code LIKE ?",
                    conn, params=(f"%{s_query}%", f"%{s_query}%")
                )
                conn.close()
                if not m_df.empty:
                    opt = st.selectbox("انتخاب کالا:", (m_df['code'] + " - " + m_df['name']).tolist())
                    e_code = opt.split(" - ")[0]
        else:
            if HAS_SCANNER_PKG:
                scanned_e = qrcode_scanner(key='e_scan')
                if scanned_e: e_code = scanned_e
                
        if e_code:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT * FROM products WHERE code=?", (e_code,))
            p = c.fetchone()
            conn.close()
            if p:
                en = st.text_input("نام", p[1])
                ecar = st.text_input("ماشین", p[6])
                ecat = st.text_input("دسته", p[2])
                
                eb = st.number_input("خرید (تومان)", value=int(p[3]), step=10000)
                st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#0088cc; font-weight:bold; font-size: 14px;'>💳 معادل: {eb:,.0f} تومان</div>", unsafe_allow_html=True)
                
                es = st.number_input("فروش (تومان)", value=int(p[4]), step=10000)
                st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#0088cc; font-weight:bold; font-size: 14px;'>💳 معادل: {es:,.0f} تومان</div>", unsafe_allow_html=True)
                
                est = st.number_input("موجودی", value=int(p[5]))
                if st.button("💾 ذخیره تغییرات", use_container_width=True):
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("UPDATE products SET name=?, compatible_cars=?, category=?, purchase_price=?, sale_price=?, stock=? WHERE code=?", (en, ecar, ecat, eb, es, est, e_code))
                    conn.commit()
                    conn.close()
                    st.success("آپدیت شد!")
                    st.rerun()

# ==========================================
# افزودن کالا 
# ==========================================
elif choice == "➕ افزودن کالا":
    st.header("➕ افزودن کالای جدید به انبار")
    
    tab_manual, tab_bulk = st.tabs(["➕ ثبت تکی کالا", "📂 ورود گروهی با اکسل"])
    
    with tab_manual:
        a_mode = st.radio("روش ورود کد:", ("دستی / تولید خودکار", "اسکن دوربین"))
        
        if a_mode == "اسکن دوربین" and HAS_SCANNER_PKG:
            scanned = qrcode_scanner(key='new_scan')
            if scanned: st.session_state.scanned_add_code = scanned
                
        val = st.session_state.scanned_add_code if a_mode == "اسکن دوربین" else ""
        p_code = st.text_input("کد/بارکد (خالی بگذارید تا خودکار ساخته شود):", value=val)
        
        pn = st.text_input("نام کالا *")
        pc = st.text_input("مناسب خودرو (مثال 206):", "عمومی")
        pcat = st.selectbox("دسته‌بندی", ["هدلایت", "روکش", "سیستم صوتی", "تزئینات", "سایر"])
        
        c1, c2 = st.columns(2)
        with c1: 
            pb = st.number_input("قیمت خرید (تومان)", step=10000, min_value=0)
            st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#2e7d32; font-weight:bold; font-size: 14px;'>💳 معادل: {pb:,.0f} تومان</div>", unsafe_allow_html=True)
        with c2: 
            ps = st.number_input("قیمت فروش (تومان)", step=10000, min_value=0)
            st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#2e7d32; font-weight:bold; font-size: 14px;'>💳 معادل: {ps:,.0f} تومان</div>", unsafe_allow_html=True)
            
        pst = st.number_input("موجودی", min_value=0)
        
        if st.button("➕ ثبت کالا", type="primary", use_container_width=True):
            if not pn: st.error("نام الزامی است.")
            else:
                fc = p_code.strip() if p_code.strip() else "AUTO-"+get_iran_time().strftime("%Y%m%d%H%M%S")
                try:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("INSERT INTO products (code, name, category, purchase_price, sale_price, stock, compatible_cars) VALUES (?,?,?,?,?,?,?)", (fc, pn, pcat, pb, ps, pst, pc))
                    conn.commit()
                    conn.close()
                    st.session_state.scanned_add_code = ""
                    st.success("ثبت شد!")
                except sqlite3.IntegrityError:
                    st.error("کد تکراری است!")
                
    with tab_bulk:
        st.info("💡 با این قابلیت می‌توانید صدها کالا را در یک چشم به هم زدن وارد سیستم کنید! ابتدا فایل نمونه را دانلود کنید، لیست اجناس را در آن پر کنید و سپس فایل تکمیل‌شده را آپلود کنید.")
        
        sample_df = pd.DataFrame(columns=['کد کالا (اختیاری)', 'نام کالا', 'مناسب خودرو', 'دسته‌بندی', 'قیمت خرید', 'قیمت فروش', 'موجودی'])
        sample_excel = convert_df_to_excel(sample_df)
        st.download_button(label="📥 ۱. دانلود فایل نمونه اکسل (خام)", data=sample_excel, file_name="Template_Products.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        st.markdown("---")
        uploaded_file = st.file_uploader("📤 ۲. فایل اکسل تکمیل‌شده را اینجا آپلود کنید:", type=['xlsx'])
        
        if uploaded_file is not None:
            if st.button("🚀 ۳. پردازش و ثبت گروهی کالاها", type="primary", use_container_width=True):
                try:
                    bulk_df = pd.read_excel(uploaded_file)
                    expected_cols = ['کد کالا (اختیاری)', 'نام کالا', 'مناسب خودرو', 'دسته‌بندی', 'قیمت خرید', 'قیمت فروش', 'موجودی']
                    
                    if all(col in bulk_df.columns for col in expected_cols):
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        success_count = 0
                        error_count = 0
                        
                        for index, row in bulk_df.iterrows():
                            p_name = str(row['نام کالا'])
                            if p_name == 'nan' or not p_name.strip(): 
                                continue
                                
                            p_code = str(row['کد کالا (اختیاری)'])
                            if p_code == 'nan' or not p_code.strip():
                                fc = "AUTO-" + get_iran_time().strftime("%Y%m%d%H%M%S") + str(index)
                            else:
                                fc = p_code.strip()
                                
                            pc = str(row['مناسب خودرو']) if str(row['مناسب خودرو']) != 'nan' else "عمومی"
                            pcat = str(row['دسته‌بندی']) if str(row['دسته‌بندی']) != 'nan' else "سایر"
                            pb = float(row['قیمت خرید']) if str(row['قیمت خرید']) != 'nan' else 0
                            ps = float(row['قیمت فروش']) if str(row['قیمت فروش']) != 'nan' else 0
                            pst = int(row['موجودی']) if str(row['موجودی']) != 'nan' else 0

                            try:
                                c.execute("INSERT INTO products (code, name, category, purchase_price, sale_price, stock, compatible_cars) VALUES (?,?,?,?,?,?,?)", (fc, p_name, pcat, pb, ps, pst, pc))
                                success_count += 1
                            except sqlite3.IntegrityError:
                                error_count += 1

                        conn.commit()
                        conn.close()
                        
                        if success_count > 0:
                            st.success(f"✅ عالی! {success_count} کالا با موفقیت به انبار اضافه شد.")
                        if error_count > 0:
                            st.warning(f"⚠️ {error_count} کالا ثبت نشد (احتمالاً کد آن‌ها تکراری بوده است).")
                    else:
                        st.error("❌ ستون‌های فایل اکسل با نمونه همخوانی ندارد. لطفاً فقط فایل نمونه را پر کنید.")
                except Exception as e:
                    st.error(f"خطا در خواندن فایل: {e}")

# ==========================================
# داشبورد و گزارش‌ها و تلگرام
# ==========================================
elif choice == "📊 گزارش‌ها و داشبورد":
    st.header("📊 داشبورد مدیریت مالی")
    
    conn = sqlite3.connect(DB_NAME)
    inv_df_capital = pd.read_sql_query("SELECT purchase_price, stock FROM products", conn)
    total_capital = (inv_df_capital['purchase_price'] * inv_df_capital['stock']).sum()
    st.markdown(f"<div class='metric-box'>💎 ارزش کل سرمایه خوابیده در انبار: {total_capital:,.0f} تومان</div>", unsafe_allow_html=True)

    t_rep, t_chart, t_exp, t_staff, t_vip, t_discount = st.tabs(["📋 گزارش فروش", "📈 نمودارها", "💸 دخل‌وخرج", "👥 عملکرد پرسنل", "🏆 مشتریان VIP", "📉 تخفیف‌ها"])
    
    sales_df = pd.read_sql_query("SELECT * FROM sales", conn)
    exp_df = pd.read_sql_query("SELECT * FROM expenses", conn)
    conn.close()
    
    now_dt = get_iran_time().replace(tzinfo=None)
    d_prof, today_sales_amt = 0, 0
    
    if not sales_df.empty:
        sales_df['timestamp'] = pd.to_datetime(sales_df['timestamp']).dt.tz_localize(None)
        sales_df['درآمد نهایی فاکتور'] = (sales_df['quantity'] * sales_df['sale_price']) + sales_df['install_fee'] - sales_df['discount']
    if not exp_df.empty:
        exp_df['timestamp'] = pd.to_datetime(exp_df['timestamp']).dt.tz_localize(None)

    with t_rep:
        if not sales_df.empty:
            d_sales = sales_df[sales_df['timestamp'] >= (now_dt - timedelta(days=1))]
            m_sales = sales_df[sales_df['timestamp'] >= (now_dt - timedelta(days=31))]
            
            d_exp_sum = exp_df[exp_df['timestamp'] >= (now_dt - timedelta(days=1))]['amount'].sum() if not exp_df.empty else 0
            m_exp_sum = exp_df[exp_df['timestamp'] >= (now_dt - timedelta(days=31))]['amount'].sum() if not exp_df.empty else 0
            
            c1, c2 = st.columns(2)
            with c1:
                st.info("📊 فروش ۲۴ ساعت گذشته")
                today_sales_amt = d_sales['درآمد نهایی فاکتور'].sum()
                d_prof = d_sales['net_profit'].sum() - d_exp_sum - d_sales['staff_commission'].sum()
                st.metric("درآمد کل صندوق", f"{today_sales_amt:,.0f} T")
                st.metric("سود خالص صاحب مغازه", f"{d_prof:,.0f} T")
            with c2:
                st.success("📊 فروش ۳۱ روز گذشته")
                m_prof = m_sales['net_profit'].sum() - m_exp_sum - m_sales['staff_commission'].sum()
                st.metric("درآمد کل صندوق", f"{m_sales['درآمد نهایی فاکتور'].sum():,.0f} T")
                st.metric("سود خالص صاحب مغازه", f"{m_prof:,.0f} T")
            
            df_to_show = sales_df[['sale_date', 'name', 'staff_name', 'discount', 'درآمد نهایی فاکتور', 'net_profit', 'staff_commission']]
            st.dataframe(df_to_show, hide_index=True, use_container_width=True)
            
            excel_sales = convert_df_to_excel(df_to_show)
            st.download_button(label="📥 دانلود گزارش فروش (Excel)", data=excel_sales, file_name=f"Sales_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else: st.info("فروشی ثبت نشده.")
        
    with t_chart:
        if not sales_df.empty:
            st.subheader("روند درآمد ۳۰ روز اخیر")
            chart_data = sales_df[['sale_date', 'درآمد نهایی فاکتور']].copy()
            chart_data['date'] = chart_data['sale_date'].str.split(" - ").str[0]
            st.line_chart(chart_data.groupby('date')['درآمد نهایی فاکتور'].sum())
            
    with t_exp:
        st.subheader("➕ ثبت هزینه جدید (اجاره، برق، و...)")
        ex_t = st.text_input("شرح هزینه")
        
        ex_a = st.number_input("مبلغ (تومان)", step=50000)
        if ex_a >= 0:
            st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#2e7d32; font-weight:bold; font-size: 14px;'>💳 معادل: {ex_a:,.0f} تومان</div>", unsafe_allow_html=True)
        
        if st.button("ثبت خرج‌کرد", use_container_width=True):
            if ex_t and ex_a > 0:
                n_str = jdatetime.datetime.fromgregorian(datetime=get_iran_time()).strftime('%Y/%m/%d')
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("INSERT INTO expenses (title, amount, exp_date, timestamp) VALUES (?,?,?,?)", (ex_t, ex_a, n_str, get_iran_time()))
                conn.commit()
                conn.close()
                st.success("هزینه ثبت شد.")
                st.rerun()
        if not exp_df.empty:
            st.dataframe(exp_df[['exp_date', 'title', 'amount']], hide_index=True, use_container_width=True)
            
    with t_staff:
        if not sales_df.empty:
            st.subheader("👷‍♂️ عملکرد و حقوق پرسنل (شاگردان)")
            staff_perf = sales_df[sales_df['staff_name'] != 'ادمین (بدون پورسانت)'].groupby('staff_name').agg({'quantity':'sum', 'درآمد نهایی فاکتور':'sum', 'staff_commission':'sum'}).reset_index()
            staff_perf.columns = ['نام شاگرد', 'تعداد کار/قطعه', 'درآمدزایی برای مغازه', 'مبلغ پورسانت او (تومان)']
            st.dataframe(staff_perf, hide_index=True, use_container_width=True)
            
    with t_vip:
        if not sales_df.empty:
            st.subheader("👑 مشتریان برتر")
            vip = sales_df[sales_df['customer_name'] != ''].groupby(['customer_name', 'customer_phone']).agg({'درآمد نهایی فاکتور':'sum'}).reset_index().sort_values(by='درآمد نهایی فاکتور', ascending=False)
            vip.columns = ['نام', 'موبایل', 'جمع پرداختی']
            st.dataframe(vip, hide_index=True, use_container_width=True)
            
    with t_discount:
        if not sales_df.empty:
            st.subheader("📉 گزارش تخفیف‌های داده شده توسط شاگردان")
            discount_df = sales_df[sales_df['discount'] > 0]
            if not discount_df.empty:
                st.warning(f"مجموع کل تخفیف‌های داده شده: {discount_df['discount'].sum():,.0f} تومان")
                st.dataframe(discount_df[['sale_date', 'staff_name', 'name', 'discount', 'درآمد نهایی فاکتور']], hide_index=True, use_container_width=True)
            else:
                st.success("تا کنون هیچ تخفیفی روی فاکتورها ثبت نشده است.")

    st.markdown("---")
    st.subheader("📤 ارسال گزارش مالی به تلگرام")
    tg_token, tg_chat_id = get_telegram_secrets()
    if tg_token and tg_chat_id:
        if st.button("ارسال خلاصه گزارش امروز به کانال/گروه تلگرام 🚀", use_container_width=True):
            today_str = jdatetime.datetime.fromgregorian(datetime=now_dt).strftime('%Y/%m/%d')
            msg_text = f"📊 گزارش مالی پایان روز ({today_str})\n\n💰 مجموع درآمد فروش و خدمات: {today_sales_amt:,.0f} تومان\n💎 سود خالص تقریبی: {d_prof:,.0f} تومان\n\n📌 توجه: مبالغ چک‌ها و طلب‌ها در این گزارش لحاظ نشده است."
            if send_telegram_msg(tg_token, tg_chat_id, msg_text):
                st.success("✅ گزارش با موفقیت به تلگرام شما ارسال شد!")
            else:
                st.error("❌ خطا در ارسال! اینترنت گوشی یا تنظیمات Token ربات را بررسی کنید.")
    else:
        st.info("💡 برای فعال‌سازی ارسال گزارش خودکار، باید `telegram_token` و `telegram_chat_id` را در تنظیمات Secrets وارد کنید.")

# ==========================================
# دفتر حساب
# ==========================================
elif choice == "📒 دفتر حساب (چک‌ها)":
    st.header("📒 دفتر طلب و بدهی")
    t1, t2 = st.tabs(["💵 طلب از مشتریان", "💳 بدهی و چک‌های ما"])
    
    def render_ledger(l_type, title, p_label):
        st.markdown(f"### ➕ ثبت {title} جدید")
        c1, c2 = st.columns(2)
        with c1: 
            name = st.text_input(p_label, key=f"name_{l_type}")
            amt = st.number_input("مبلغ (تومان)", step=100000, key=f"amt_{l_type}")
            if amt >= 0:
                st.markdown(f"<div style='margin-top:-15px; margin-bottom:10px; color:#2e7d32; font-weight:bold; font-size: 14px;'>💳 معادل: {amt:,.0f} تومان</div>", unsafe_allow_html=True)
            
        with c2:
            date = st.text_input("سررسید (مثال: 1403/06/10)", key=f"date_{l_type}")
            desc = st.text_input("بابت", key=f"desc_{l_type}")
            
        if st.button(f"✅ ثبت در دفتر {title}", use_container_width=True, key=f"btn_add_{l_type}"):
            if name and amt > 0:
                now_str = jdatetime.datetime.fromgregorian(datetime=get_iran_time()).strftime('%Y/%m/%d')
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("INSERT INTO ledger (record_type, person_name, amount, due_date, description, status, timestamp) VALUES (?,?,?,?,?,?,?)", (l_type, name, amt, date, desc, "معلق", now_str))
                conn.commit()
                conn.close()
                st.rerun()
                
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query(f"SELECT id as 'کد', person_name as '{p_label}', amount as 'مبلغ', due_date as 'سررسید', description as 'بابت' FROM ledger WHERE record_type='{l_type}'", conn)
        conn.close()
        
        if not df.empty:
            st.markdown("---")
            st.dataframe(df, hide_index=True, use_container_width=True)
            
            ex_ledger = convert_df_to_excel(df)
            st.download_button(label=f"📥 دانلود لیست {title} (Excel)", data=ex_ledger, file_name=f"Ledger_{l_type}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"dl_{l_type}")
            
            did = st.number_input(f"برای حذف {title} کد را وارد کنید:", min_value=0, key=f"d_{l_type}")
            confirm_del = st.checkbox("تایید می‌کنم که می‌خوام این مورد رو برای همیشه حذف کنم", key=f"confirm_del_{l_type}")
            if st.button("✅ تسویه و حذف از لیست", key=f"b_{l_type}", disabled=not confirm_del):
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("DELETE FROM ledger WHERE id=?", (did,))
                conn.commit()
                conn.close()
                st.rerun()
                
    with t1: render_ledger("customer_debt", "طلب", "مشتری بدهکار")
    with t2: render_ledger("owner_debt", "بدهی", "شخص طلبکار")

# ==========================================
# مدیریت پرسنل 
# ==========================================
elif choice == "👥 مدیریت پرسنل (شاگردان)":
    st.header("👥 مدیریت شاگردان و تعیین حقوق/پورسانت")
    
    st.subheader("➕ افزودن شاگرد جدید")
    c1, c2, c3 = st.columns(3)
    with c1:
        new_staff_name = st.text_input("نام شاگرد (مثال: علی)")
    with c2:
        new_staff_pass = st.text_input("رمز عبور اختصاصی شاگرد (حداقل ۴ کاراکتر)", value="")
    with c3:
        new_staff_rate = st.number_input("پورسانت از سود/اجرت (%)", min_value=0.0, max_value=100.0, value=20.0, step=1.0)
        
    if st.button("ثبت مشخصات شاگرد", use_container_width=True):
        if new_staff_name and new_staff_pass and len(new_staff_pass) >= 4:
            try:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("INSERT INTO staff (name, password, commission_rate, timestamp) VALUES (?,?,?,?)", (new_staff_name, hash_password(new_staff_pass), new_staff_rate, get_iran_time()))
                conn.commit()
                conn.close()
                st.success(f"شاگرد جدید ({new_staff_name}) ثبت شد! رمز عبور: «{new_staff_pass}» — همین الان یادداشتش کن و به شاگرد بده، چون از این به بعد به‌صورت امن (هش‌شده) ذخیره می‌شه و دیگه قابل نمایش نیست.")
            except sqlite3.IntegrityError:
                st.error("این نام قبلاً در سیستم ثبت شده است.")
        elif new_staff_name and new_staff_pass:
            st.error("رمز عبور باید حداقل ۴ کاراکتر باشد.")
        else:
            st.error("لطفاً نام و رمز عبور را وارد کنید.")
            
    st.markdown("---")
    st.subheader("📋 لیست شاگردان مغازه")
    conn = sqlite3.connect(DB_NAME)
    staff_df_disp = pd.read_sql_query("SELECT id as 'کد سیستم', name as 'نام شاگرد', commission_rate as 'درصد پورسانت (%)' FROM staff", conn)
    conn.close()
    
    if not staff_df_disp.empty:
        staff_df_disp['رمز عبور'] = '🔒 هش‌شده'
        st.dataframe(staff_df_disp, hide_index=True, use_container_width=True)
        st.caption("رمزها به‌صورت امن ذخیره می‌شن و دیگه قابل نمایش نیستن. برای عوض کردن رمز یه شاگرد، فعلاً باید حذفش کنی و دوباره با رمز جدید ثبتش کنی.")
        del_staff_id = st.number_input("برای اخراج و حذف شاگرد، کد سیستم او را وارد کنید:", min_value=0)
        confirm_staff_del = st.checkbox("تایید می‌کنم که می‌خوام این شاگرد رو حذف کنم")
        if st.button("🗑️ حذف شاگرد", disabled=not confirm_staff_del):
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("DELETE FROM staff WHERE id=?", (del_staff_id,))
            conn.commit()
            conn.close()
            st.success("شاگرد با موفقیت از سیستم حذف شد.")
            st.rerun()
    else:
        st.warning("هنوز هیچ شاگردی ثبت نشده است.")
