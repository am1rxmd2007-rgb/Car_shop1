import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import jdatetime
import pytz
import urllib.parse
import os
import io

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

# 🌟 اصلاح باگ منوی موبایل: هدر مخفی نمی‌شود تا دکمه همبرگری در موبایل کار کند
st.markdown("""
<style>
    /* مخفی کردن منوی سه‌نقطه و فوتر استریم‌لیت برای شخصی‌سازی ظاهر */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {background-color: transparent !important;}
    
    /* تنظیمات راست‌چین و فونت */
    .stMarkdown, p, h1, h2, h3, h4, label { direction: rtl; text-align: right; font-family: 'Tahoma', sans-serif !important; }
    .stButton>button { width: 100%; border-radius: 8px; }
    .invoice-box { border: 2px dashed #4CAF50; padding: 20px; border-radius: 10px; background-color: #f9f9f9; color: #333; margin-top: 15px; direction: rtl; text-align: right; }
    .metric-box { padding: 15px; border-radius: 10px; background-color: #e8f5e9; border: 1px solid #4CAF50; margin-bottom: 20px; text-align: center; font-size: 20px; font-weight: bold; color: #2e7d32; }
</style>
""", unsafe_allow_html=True)

def get_iran_time():
    iran_tz = pytz.timezone('Asia/Tehran')
    return datetime.now(iran_tz)

# تابع تبدیل دیتافریم به فایل اکسل
def convert_df_to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

# ==========================================
# توابع دیتابیس (حفظ اصالت و امنیت کامل)
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
    c.execute('''CREATE TABLE IF NOT EXISTS blind_inventory
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT, product_name TEXT,
                  counted_stock INTEGER, expected_stock INTEGER, 
                  staff_name TEXT, timestamp TEXT, status TEXT)''')
    
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

# 🔒 سیستم احراز هویت (Login)
if st.session_state.user_role is None:
    st.sidebar.subheader("🔐 ورود به سیستم")
    login_type = st.sidebar.radio("ورود به عنوان:", ["شاگرد / پرسنل فروش", "صاحب مغازه (ادمین)"])
    
    if login_type == "صاحب مغازه (ادمین)":
        admin_pass = st.sidebar.text_input("رمز عبور ادمین:", type="password")
        if st.sidebar.button("ورود به پنل مدیریت"):
            if admin_pass == "2613":
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
            if st.sidebar.button("ورود به پنل فروش"):
                st.session_state.user_role = "Staff"
                st.session_state.user_name = staff_name_input
                st.rerun()
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

# تنظیم منوها
st.sidebar.markdown("---")
if st.session_state.user_role == "Admin":
    menu = ["🛒 ثبت فروش / خدمات", "📦 مدیریت انبار", "➕ افزودن کالا", "📊 گزارش‌ها و داشبورد", "📒 دفتر حساب (چک‌ها)", "👥 مدیریت پرسنل (شاگردان)", "🕵️‍♂️ گزارش انبارگردانی"]
else:
    menu = ["🛒 ثبت فروش / خدمات", "📦 جستجو در انبار", "🔍 انبارگردانی فیزیکی"]

choice = st.sidebar.radio("منوی اختصاصی شما:", menu)

# ابزارهای فقط ادمین در سایدبار
if st.session_state.user_role == "Admin":
    st.sidebar.markdown("---")
    if os.path.exists(DB_NAME):
        with open(DB_NAME, "rb") as file:
            st.sidebar.download_button(label="💾 دانلود بک‌آپ دیتابیس", data=file, file_name=f"Backup_{datetime.now().strftime('%Y%m%d')}.db", mime="application/octet-stream")
            
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
            except:
                st.sidebar.info(f"{l_type} {row['person_name']}\nمبلغ: {row['amount']:,.0f} T\nسررسید: {due_date_str}")

# ==========================================
# بخش 1: ثبت فروش و خدمات
# ==========================================
if choice == "🛒 ثبت فروش / خدمات":
    st.header("🛒 ثبت فاکتور مشتری")
    
    conn = sqlite3.connect(DB_NAME)
    staff_df_list = pd.read_sql_query("SELECT name FROM staff", conn)
    conn.close()
    staff_options = ["ادمین (بدون پورسانت)"] + staff_df_list['name'].tolist() if not staff_df_list.empty else ["ادمین (بدون پورسانت)"]

    tab_sale, tab_service = st.tabs(["🛒 فروش قطعه و کالا", "🔧 ثبت خدمات و تعمیرات (بدون کالا)"])
    
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
                    m_df = pd.read_sql_query(f"SELECT code, name, compatible_cars FROM products WHERE name LIKE '%{search_q}%' OR compatible_cars LIKE '%{search_q}%'", conn)
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
                    
                    with st.form("sale_form"):
                        f_qty = st.number_input("تعداد", min_value=1, max_value=product[5] if product[5]>0 else 1)
                        f_install = st.number_input("اجرت نصب (تومان)", min_value=0, step=10000, value=0)
                        f_discount = st.number_input("مبلغ تخفیف (تومان)", min_value=0, step=10000, value=0)
                        
                        if st.session_state.user_role == "Admin":
                            s_staff = st.selectbox("👷‍♂️ ثبت به نام (جهت پورسانت):", staff_options)
                        else:
                            s_staff = st.session_state.user_name
                            st.info(f"👷‍♂️ فاکتور به نام شما ({s_staff}) ثبت می‌شود.")
                        
                        cc1, cc2 = st.columns(2)
                        with cc1: c_name = st.text_input("نام مشتری (اختیاری)")
                        with cc2: c_phone = st.text_input("شماره موبایل (اختیاری)")
                        c_car = st.text_input("مدل ماشین")

                        if st.form_submit_button("✅ ثبت نهایی فاکتور"):
                            if product[5] >= f_qty:
                                new_stock = product[5] - f_qty
                                now_dt = get_iran_time()
                                now_str = jdatetime.datetime.fromgregorian(datetime=now_dt).strftime('%Y/%m/%d - %H:%M')
                                
                                net_prof = ((product[4] - product[3]) * f_qty) + f_install - f_discount
                                total_bill = (product[4] * f_qty) + f_install - f_discount
                                
                                staff_rate = 0
                                conn = sqlite3.connect(DB_NAME)
                                c = conn.cursor()
                                if s_staff != "ادمین (بدون پورسانت)":
                                    c.execute("SELECT commission_rate FROM staff WHERE name=?", (s_staff,))
                                    res = c.fetchone()
                                    if res: staff_rate = res[0]
                                staff_comm = net_prof * (staff_rate / 100.0) if net_prof > 0 else 0
                                
                                c.execute("UPDATE products SET stock=? WHERE code=?", (new_stock, code_input))
                                c.execute('''INSERT INTO sales (product_code, name, quantity, sale_price, sale_date, timestamp, customer_name, customer_phone, car_model, install_fee, net_profit, staff_name, staff_commission, discount) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                                          (code_input, product[1], f_qty, product[4], now_str, now_dt, c_name, c_phone, c_car, f_install, net_prof, s_staff, staff_comm, f_discount))
                                conn.commit()
                                conn.close()
                                
                                st.session_state.last_invoice = {"date":now_str, "c_name":c_name or "نقدی", "c_phone":c_phone, "c_car":c_car, "p_name":product[1], "qty":f_qty, "price":product[4], "install":f_install, "discount":f_discount, "total":total_bill, "staff":s_staff}
                                st.success("فروش ثبت شد!")
                                st.rerun()
                            else:
                                st.error("موجودی کافی نیست!")
                else:
                    st.warning("کالایی یافت نشد.")

    with tab_service:
        st.info("ثبت خدمات و تعمیرات بدون کسر کالا از انبار")
        with st.form("service_form"):
            s_name = st.text_input("شرح خدمات (مثال: نصب سیستم صوتی)")
            s_fee = st.number_input("مبلغ اجرت (تومان)", min_value=0, step=50000)
            
            if st.session_state.user_role == "Admin":
                s_staff_srv = st.selectbox("👷‍♂️ ثبت به نام نصاب:", staff_options)
            else:
                s_staff_srv = st.session_state.user_name
                st.info(f"👷‍♂️ فاکتور به نام شما ({s_staff_srv}) ثبت می‌شود.")
            
            sc1, sc2 = st.columns(2)
            with sc1: s_cname = st.text_input("نام مشتری")
            with sc2: s_cphone = st.text_input("شماره موبایل")
            s_ccar = st.text_input("مدل خودرو")
            
            if st.form_submit_button("🔧 ثبت خدمات"):
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

    if st.session_state.last_invoice:
        inv = st.session_state.last_invoice
        st.markdown("---")
        st.subheader("🧾 فاکتور مشتری")
        dis_text = f"\n🎁 تخفیف اعمال شده: {inv['discount']:,} تومان" if inv['discount'] > 0 else ""
        inv_text = f"🧾 فاکتور فروشگاه\nتاریخ: {inv['date']}\n👤 مشتری: {inv['c_name']}\n🚗 خودرو: {inv['c_car']}\n👷‍♂️ مسئول: {inv['staff']}\n-------------------\n📦 شرح: {inv['p_name']}\n🔢 تعداد: {inv['qty']}\n💵 فی: {inv['price']:,} تومان\n🔧 اجرت: {inv['install']:,} تومان{dis_text}\n-------------------\n💰 جمع کل: {inv['total']:,} تومان\n✨ سپاس از اعتماد شما ✨"
        st.markdown(f"<div class='invoice-box'>{inv_text.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
        enc = urllib.parse.quote(inv_text)
        w_link = f"https://wa.me/98{inv['c_phone'][1:]}?text={enc}" if inv['c_phone'].startswith('09') else f"https://wa.me/?text={enc}"
        t_link = f"https://t.me/share/url?url={enc}"
        b1, b2, b3 = st.columns(3)
        with b1: st.markdown(f"<a href='{w_link}' target='_blank'><button style='width:100%; padding:10px; background-color:#25D366; color:white; border:none;'>🟢 ارسال واتس‌اپ</button></a>", unsafe_allow_html=True)
        with b2: st.markdown(f"<a href='{t_link}' target='_blank'><button style='width:100%; padding:10px; background-color:#0088cc; color:white; border:none;'>🔵 ارسال تلگرام</button></a>", unsafe_allow_html=True)
        with b3:
            if st.button("بستن فاکتور"):
                st.session_state.last_invoice = None
                st.rerun()

# ==========================================
# بخش 2: انبار
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
        st.download_button(label="📥 دانلود لیست انبار (فایل Excel)", data=excel_data, file_name=f"Inventory_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    if st.session_state.user_role == "Admin":
        st.markdown("---")
        out_df = df[df['موجودی'] == 0]
        if not out_df.empty:
            st.error(f"⚠️ {len(out_df)} کالا موجودی صفر دارند:")
            st.dataframe(out_df, use_container_width=True, hide_index=True)
            
        st.markdown("---")
        st.subheader("🛠️ ویرایش / حذف کالا (مختص ادمین)")
        e_mode = st.radio("روش انتخاب:", ("جستجوی نام/کد", "اسکن با دوربین"), horizontal=True)
        e_code = ""
        if e_mode == "جستجوی نام/کد":
            s_query = st.text_input("بخشی از نام یا کد را سرچ کنید:")
            if s_query:
                conn = sqlite3.connect(DB_NAME)
                m_df = pd.read_sql_query(f"SELECT code, name FROM products WHERE name LIKE '%{s_query}%' OR code LIKE '%{s_query}%'", conn)
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
                eb = st.number_input("خرید", value=int(p[3]))
                es = st.number_input("فروش", value=int(p[4]))
                est = st.number_input("موجودی", value=int(p[5]))
                if st.button("💾 ذخیره تغییرات"):
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("UPDATE products SET name=?, compatible_cars=?, category=?, purchase_price=?, sale_price=?, stock=? WHERE code=?", (en, ecar, ecat, eb, es, est, e_code))
                    conn.commit()
                    conn.close()
                    st.success("آپدیت شد!")
                    st.rerun()

# ==========================================
# بخش 3: انبارگردانی کور
# ==========================================
elif choice == "🔍 انبارگردانی فیزیکی":
    st.header("🔍 انبارگردانی کور (شمارش فیزیکی)")
    st.info("کالا را پیدا/اسکن کنید و فقط تعداد فیزیکی موجود در قفسه را وارد کنید.")
    
    b_scan_method = st.radio("روش انتخاب کالا:", ("اسکن با دوربین", "ورود دستی کد/بارکد", "جستجوی نام کالا"))
    b_code = ""
    
    if b_scan_method == "اسکن با دوربین":
        if HAS_SCANNER_PKG:
            scanned_b = qrcode_scanner(key='blind_scan')
            if scanned_b: b_code = scanned_b
        else:
            st.error("اسکنر نصب نیست.")
    elif b_scan_method == "ورود دستی کد/بارکد":
        b_code = st.text_input("کد یا بارکد کالا را وارد کنید:")
    elif b_scan_method == "جستجوی نام کالا":
        search_b_query = st.text_input("نام بخشی از کالا یا ماشین را جستجو کنید:")
        if search_b_query:
            conn = sqlite3.connect(DB_NAME)
            b_match_df = pd.read_sql_query(f"SELECT code, name, compatible_cars FROM products WHERE name LIKE '%{search_b_query}%' OR compatible_cars LIKE '%{search_b_query}%'", conn)
            conn.close()
            if not b_match_df.empty:
                opts = (b_match_df['name'] + " (مناسب: " + b_match_df['compatible_cars'] + ") - کد: " + b_match_df['code']).tolist()
                b_selected = st.selectbox("کالای مورد نظر را انتخاب کنید:", opts)
                b_code = b_selected.split("کد: ")[1].strip()
                
    if b_code:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT code, name, stock FROM products WHERE code=?", (b_code,))
        p = c.fetchone()
        conn.close()
        
        if p:
            st.subheader(f"📦 کالا: {p[1]}")
            with st.form("blind_form"):
                counted = st.number_input("تعدادی که به صورت فیزیکی در قفسه می‌بینید را وارد کنید:", min_value=0, step=1)
                if st.form_submit_button("✅ ثبت شمارش برای بررسی ادمین"):
                    now_dt = get_iran_time()
                    now_str = jdatetime.datetime.fromgregorian(datetime=now_dt).strftime('%Y/%m/%d - %H:%M')
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("INSERT INTO blind_inventory (product_code, product_name, counted_stock, expected_stock, staff_name, timestamp, status) VALUES (?,?,?,?,?,?,?)",
                              (p[0], p[1], counted, p[2], st.session_state.user_name, now_str, "بررسی نشده"))
                    conn.commit()
                    conn.close()
                    st.success("شمارش شما ثبت شد و برای تایید به پنل مدیریت ارسال گردید.")
        else:
            st.warning("⚠️ کالایی با این مشخصات یافت نشد.")

# ==========================================
# افزودن کالا (مختص ادمین)
# ==========================================
elif choice == "➕ افزودن کالا":
    st.header("➕ کالای جدید")
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
    with c1: pb = st.number_input("قیمت خرید", step=10000)
    with c2: ps = st.number_input("قیمت فروش", step=10000)
    pst = st.number_input("موجودی", min_value=0)
    
    if st.button("➕ ثبت کالا", type="primary"):
        if not pn: st.error("نام الزامی است.")
        else:
            fc = p_code.strip() if p_code.strip() else "AUTO-"+get_iran_time().strftime("%Y%m%d%H%M%S")
            try:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("INSERT INTO products VALUES (?,?,?,?,?,?,?)", (fc, pn, pcat, pb, ps, pst, pc))
                conn.commit()
                conn.close()
                st.session_state.scanned_add_code = ""
                st.success("ثبت شد!")
            except: st.error("کد تکراری است!")

# ==========================================
# داشبورد و گزارش‌ها
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
                d_prof = d_sales['net_profit'].sum() - d_exp_sum - d_sales['staff_commission'].sum()
                st.metric("درآمد کل صندوق", f"{d_sales['درآمد نهایی فاکتور'].sum():,.0f} T")
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
        with st.form("add_exp"):
            st.subheader("➕ ثبت هزینه جدید (اجاره، برق، و...)")
            ex_t = st.text_input("شرح هزینه")
            ex_a = st.number_input("مبلغ (تومان)", step=50000)
            if st.form_submit_button("ثبت خرِج‌کرد"):
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

elif choice == "🕵️‍♂️ گزارش انبارگردانی":
    st.header("🕵️‍♂️ بررسی گزارشات انبارگردانی شاگردان")
    conn = sqlite3.connect(DB_NAME)
    df_b = pd.read_sql_query("SELECT * FROM blind_inventory WHERE status='بررسی نشده'", conn)
    
    if not df_b.empty:
        df_b['اختلاف با سیستم'] = df_b['counted_stock'] - df_b['expected_stock']
        st.dataframe(df_b[['id', 'product_name', 'staff_name', 'expected_stock', 'counted_stock', 'اختلاف با سیستم', 'timestamp']], hide_index=True, use_container_width=True)
        
        with st.form("inventory_approval"):
            c1, c2 = st.columns(2)
            with c1: b_id = st.number_input("کد ردیف (id) برای اعمال تصمیم:", min_value=0)
            with c2: action = st.radio("تصمیم ادمین:", ("✅ تایید و اصلاح موجودی انبار", "❌ رد کردن (اشتباه شاگرد در شمارش)"))
            
            if st.form_submit_button("ثبت نهایی تصمیم"):
                c = conn.cursor()
                if action.startswith("✅"):
                    c.execute("SELECT product_code, counted_stock FROM blind_inventory WHERE id=?", (b_id,))
                    res = c.fetchone()
                    if res:
                        c.execute("UPDATE products SET stock=? WHERE code=?", (res[1], res[0]))
                        c.execute("UPDATE blind_inventory SET status='تایید شده' WHERE id=?", (b_id,))
                        conn.commit()
                        st.success("موجودی انبار با موفقیت اصلاح شد.")
                else:
                    c.execute("UPDATE blind_inventory SET status='رد شده' WHERE id=?", (b_id,))
                    conn.commit()
                    st.warning("شمارش شاگرد رد شد و موجودی تغییری نکرد.")
                conn.close()
                st.rerun()
    else:
        st.success("✅ هیچ انبارگردانی بررسی نشده‌ای در صف انتظار وجود ندارد.")
    conn.close()

elif choice == "📒 دفتر حساب (چک‌ها)":
    st.header("📒 دفتر طلب و بدهی")
    t1, t2 = st.tabs(["💵 طلب از مشتریان", "💳 بدهی و چک‌های ما"])
    def render_ledger(l_type, title, p_label):
        with st.form(f"f_{l_type}"):
            c1, c2 = st.columns(2)
            with c1: 
                name = st.text_input(p_label)
                amt = st.number_input("مبلغ (تومان)", step=100000)
            with c2:
                date = st.text_input("سررسید (مثال: 1403/06/10)")
                desc = st.text_input("بابت")
            if st.form_submit_button("ثبت"):
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
            st.dataframe(df, hide_index=True, use_container_width=True)
            
            ex_ledger = convert_df_to_excel(df)
            st.download_button(label=f"📥 دانلود لیست {title} (Excel)", data=ex_ledger, file_name=f"Ledger_{l_type}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"dl_{l_type}")
            
            did = st.number_input(f"برای حذف {title} کد را وارد کنید:", min_value=0, key=f"d_{l_type}")
            if st.button("✅ تسویه", key=f"b_{l_type}"):
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("DELETE FROM ledger WHERE id=?", (did,))
                conn.commit()
                conn.close()
                st.rerun()
    with t1: render_ledger("customer_debt", "طلب", "مشتری بدهکار")
    with t2: render_ledger("owner_debt", "بدهی", "شخص طلبکار")

elif choice == "👥 مدیریت پرسنل (شاگردان)":
    st.header("👥 مدیریت شاگردان و تعیین حقوق/پورسانت")
    
    with st.form("add_staff_form"):
        st.subheader("➕ افزودن شاگرد جدید")
        c1, c2 = st.columns(2)
        with c1:
            new_staff_name = st.text_input("نام شاگرد (مثال: علی رضایی)")
        with c2:
            new_staff_rate = st.number_input("درصد پورسانت از هر سود/اجرت (%)", min_value=0.0, max_value=100.0, value=20.0, step=1.0)
            
        if st.form_submit_button("ثبت مشخصات شاگرد"):
            if new_staff_name:
                try:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("INSERT INTO staff (name, commission_rate, timestamp) VALUES (?,?,?)", (new_staff_name, new_staff_rate, get_iran_time()))
                    conn.commit()
                    conn.close()
                    st.success(f"شاگرد جدید ({new_staff_name}) اضافه شد!")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("این نام قبلاً در سیستم ثبت شده است.")
            else:
                st.error("لطفاً نام شاگرد را وارد کنید.")
                
    st.markdown("---")
    st.subheader("📋 لیست شاگردان مغازه")
    conn = sqlite3.connect(DB_NAME)
    staff_df_disp = pd.read_sql_query("SELECT id as 'کد سیستم', name as 'نام شاگرد', commission_rate as 'درصد پورسانت (%)' FROM staff", conn)
    conn.close()
    
    if not staff_df_disp.empty:
        st.dataframe(staff_df_disp, hide_index=True, use_container_width=True)
        del_staff_id = st.number_input("برای حذف یک شاگرد (اخراج)، کد سیستم او را وارد کنید:", min_value=0)
        if st.button("🗑️ حذف شاگرد"):
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("DELETE FROM staff WHERE id=?", (del_staff_id,))
            conn.commit()
            conn.close()
            st.success("شاگرد با موفقیت از سیستم حذف شد.")
            st.rerun()
    else:
        st.warning("هنوز هیچ شاگردی ثبت نشده است.")
