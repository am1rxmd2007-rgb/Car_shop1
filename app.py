import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import jdatetime
import pytz
import urllib.parse

# ایمپورت اسکنر حرفه‌ای
try:
    from streamlit_qrcode_scanner import qrcode_scanner
    HAS_SCANNER_PKG = True
except ImportError:
    HAS_SCANNER_PKG = False

# ==========================================
# تنظیمات صفحه و زمان ایران
# ==========================================
st.set_page_config(page_title="سیستم جامع فروشگاه", page_icon="🚗", layout="wide")

# CSS اصلاح شده (بدون باگ به هم ریختگی کلمات)
st.markdown("""
<style>
    .stMarkdown, p, h1, h2, h3, h4, label { direction: rtl; text-align: right; font-family: 'Tahoma', sans-serif !important; }
    .stButton>button { width: 100%; border-radius: 8px; }
    .invoice-box { border: 2px dashed #4CAF50; padding: 20px; border-radius: 10px; background-color: #f9f9f9; color: #333; margin-top: 15px; direction: rtl; text-align: right; }
</style>
""", unsafe_allow_html=True)

def get_iran_time():
    iran_tz = pytz.timezone('Asia/Tehran')
    return datetime.now(iran_tz)

# ==========================================
# توابع و آپدیت دیتابیس (بدون حذف اطلاعات قبلی)
# ==========================================
DB_NAME = "inventory.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # جدول کالاها
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (code TEXT PRIMARY KEY, name TEXT, category TEXT,
                  purchase_price REAL, sale_price REAL, stock INTEGER)''')
    # اضافه کردن فیلد خودرو سازگار در صورت عدم وجود
    c.execute("PRAGMA table_info(products)")
    cols = [col[1] for col in c.fetchall()]
    if 'compatible_cars' not in cols:
        c.execute("ALTER TABLE products ADD COLUMN compatible_cars TEXT DEFAULT 'عمومی'")

    # جدول فروش
    c.execute('''CREATE TABLE IF NOT EXISTS sales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, product_code TEXT, name TEXT, 
                  quantity INTEGER, sale_price REAL, sale_date TEXT, timestamp DATETIME)''')
    # ارتقاء جدول فروش برای باشگاه مشتریان و اجرت
    c.execute("PRAGMA table_info(sales)")
    sales_cols = [col[1] for col in c.fetchall()]
    if 'customer_name' not in sales_cols:
        c.execute("ALTER TABLE sales ADD COLUMN customer_name TEXT DEFAULT ''")
        c.execute("ALTER TABLE sales ADD COLUMN customer_phone TEXT DEFAULT ''")
        c.execute("ALTER TABLE sales ADD COLUMN car_model TEXT DEFAULT ''")
        c.execute("ALTER TABLE sales ADD COLUMN install_fee REAL DEFAULT 0")
        c.execute("ALTER TABLE sales ADD COLUMN net_profit REAL DEFAULT 0")

    # جدول جدید: دفتر حساب (چک و اقساط)
    c.execute('''CREATE TABLE IF NOT EXISTS ledger
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, record_type TEXT, person_name TEXT, 
                  amount REAL, due_date TEXT, description TEXT, status TEXT, timestamp DATETIME)''')
    
    conn.commit()
    conn.close()

def get_low_stock_products():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT name, stock FROM products WHERE stock < 3", conn)
    conn.close()
    return df

init_db()

# ==========================================
# مدیریت وضعیت سیستم
# ==========================================
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "last_invoice" not in st.session_state:
    st.session_state.last_invoice = None

# ==========================================
# منوی کناری (سایدبار) و بخش ورود ادمین
# ==========================================
st.sidebar.title("🚗 مدیریت فروشگاه اسپرت")
st.sidebar.markdown("---")

menu = ["🛒 ثبت فروش و صدور فاکتور", "📦 مدیریت انبار", "➕ افزودن کالای جدید", "📊 گزارش‌های مالی", "📒 دفتر حساب (چک و اقساط)"]
choice = st.sidebar.radio("منوی اصلی:", menu)

st.sidebar.markdown("---")
st.sidebar.subheader("🔐 بخش مدیریت (ادمین)")
if not st.session_state.is_admin:
    admin_pass = st.sidebar.text_input("رمز عبور ادمین:", type="password", key="sidebar_admin_pass")
    if st.sidebar.button("ورود به ادمین"):
        if admin_pass == "2613":
            st.session_state.is_admin = True
            st.sidebar.success("شما ادمین هستید ✅")
            st.rerun()
        else:
            st.sidebar.error("رمز اشتباه است!")
else:
    st.sidebar.success("دسترسی ادمین: فعال 🔓")
    if st.sidebar.button("خروج از حساب ادمین"):
        st.session_state.is_admin = False
        st.rerun()

low_stock_df = get_low_stock_products()
if not low_stock_df.empty:
    st.sidebar.markdown("---")
    st.sidebar.error("⚠️ هشدار موجودی:")
    for _, row in low_stock_df.iterrows():
        st.sidebar.warning(f"کالای '{row['name']}' ({row['stock']} عدد)")

# ==========================================
# بخش 1: ثبت فروش، اجرت نصب و صدور فاکتور دیجیتال
# ==========================================
if choice == "🛒 ثبت فروش و صدور فاکتور":
    st.header("🛒 ثبت فروش و صدور فاکتور مشتری")
    
    col1, col2 = st.columns([1.2, 2])
    
    with col1:
        st.info("انتخاب کالا (بارکد یا نام)")
        scan_method = st.radio("روش جستجو:", ("اسکنر دوربین", "ورود دستی / بارکدخوان", "جستجوی نام/مدل ماشین"))
        code_input = ""
        
        if scan_method == "ورود دستی / بارکدخوان":
            code_input = st.text_input("کد کالا را وارد/اسکن کنید:", key="barcode_input")
        elif scan_method == "اسکنر دوربین":
            if HAS_SCANNER_PKG:
                scanned_code = qrcode_scanner(key='pro_scanner')
                if scanned_code:
                    code_input = scanned_code
            else:
                st.error("اسکنر نصب نیست.")
        elif scan_method == "جستجوی نام/مدل ماشین":
            search_q = st.text_input("نام کالا یا مدل ماشین (مثلاً 206) را جستجو کنید:")
            if search_q:
                conn = sqlite3.connect(DB_NAME)
                match_df = pd.read_sql_query(f"SELECT code, name, compatible_cars FROM products WHERE name LIKE '%{search_q}%' OR compatible_cars LIKE '%{search_q}%'", conn)
                conn.close()
                if not match_df.empty:
                    opts = (match_df['name'] + " (مناسب: " + match_df['compatible_cars'] + ") - کد: " + match_df['code']).tolist()
                    sel = st.selectbox("کالا را انتخاب کنید:", opts)
                    code_input = sel.split("کد: ")[1].strip()

    with col2:
        if code_input:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT * FROM products WHERE code=?", (code_input,))
            product = c.fetchone()
            conn.close()

            if product:
                # product: 0:code, 1:name, 2:cat, 3:buy, 4:sell, 5:stock, 6:cars
                st.subheader(f"📦 {product[1]}")
                st.markdown(f"**مناسب برای:** {product[6]}")
                st.markdown(f"**قیمت فروش:** {product[4]:,.0f} تومان")
                if st.session_state.is_admin:
                    st.markdown(f"**قیمت خرید:** {product[3]:,.0f} تومان (فقط ادمین)")
                st.markdown(f"**موجودی انبار:** {product[5]} عدد")
                
                st.markdown("---")
                with st.form("sale_form"):
                    st.markdown("**اطلاعات فروش و مشتری (باشگاه مشتریان)**")
                    f_qty = st.number_input("تعداد", min_value=1, max_value=product[5] if product[5]>0 else 1, value=1)
                    f_install = st.number_input("اجرت نصب (تومان) - اختیاری", min_value=0, step=10000, value=0)
                    
                    cc1, cc2, cc3 = st.columns(3)
                    with cc1: c_name = st.text_input("نام مشتری (اختیاری)")
                    with cc2: c_phone = st.text_input("شماره موبایل")
                    with cc3: c_car = st.text_input("مدل ماشین مشتری")
                    
                    submit_sale = st.form_submit_button("✅ ثبت نهایی و صدور فاکتور")

                    if submit_sale:
                        if product[5] >= f_qty:
                            new_stock = product[5] - f_qty
                            now_dt = get_iran_time()
                            now_str = jdatetime.datetime.fromgregorian(datetime=now_dt).strftime('%Y/%m/%d - %H:%M')
                            
                            net_profit = ((product[4] - product[3]) * f_qty) + f_install
                            total_bill = (product[4] * f_qty) + f_install
                            
                            conn = sqlite3.connect(DB_NAME)
                            c = conn.cursor()
                            c.execute("UPDATE products SET stock=? WHERE code=?", (new_stock, code_input))
                            c.execute('''INSERT INTO sales 
                                      (product_code, name, quantity, sale_price, sale_date, timestamp, 
                                       customer_name, customer_phone, car_model, install_fee, net_profit) 
                                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                      (code_input, product[1], f_qty, product[4], now_str, now_dt,
                                       c_name, c_phone, c_car, f_install, net_profit))
                            conn.commit()
                            conn.close()
                            
                            st.session_state.last_invoice = {
                                "date": now_str, "c_name": c_name or "مشتری نقدی",
                                "c_phone": c_phone, "c_car": c_car, "p_name": product[1],
                                "qty": f_qty, "price": product[4], "install": f_install, "total": total_bill
                            }
                            st.success("فروش با موفقیت ثبت شد!")
                            st.rerun()
                        else:
                            st.error("موجودی کافی نیست!")
            else:
                st.warning("کالایی یافت نشد.")

    # نمایش فاکتور دیجیتال آخرین فروش
    if st.session_state.last_invoice:
        inv = st.session_state.last_invoice
        st.markdown("---")
        st.subheader("🧾 فاکتور دیجیتال مشتری")
        
        invoice_text = f"""🧾 فاکتور فروشگاه اسپرت
تاریخ: {inv['date']}
👤 مشتری: {inv['c_name']}
🚗 خودرو: {inv['c_car']}
-------------------
📦 دستگاه/کالا: {inv['p_name']}
🔢 تعداد: {inv['qty']}
💵 قیمت واحد: {inv['price']:,} تومان
🔧 اجرت نصب: {inv['install']:,} تومان
-------------------
💰 مبلغ کل پرداختی: {inv['total']:,} تومان
✨ از خرید شما سپاسگزاریم ✨"""

        st.markdown(f"<div class='invoice-box'>{invoice_text.replace(chr(10), '<br>')}</div>", unsafe_allow_html=True)
        
        encoded_text = urllib.parse.quote(invoice_text)
        b1, b2, b3 = st.columns(3)
        
        wa_link = f"https://wa.me/98{inv['c_phone'][1:]}?text={encoded_text}" if inv['c_phone'].startswith('09') else f"https://wa.me/?text={encoded_text}"
        tg_link = f"https://t.me/share/url?url={encoded_text}"
        
        with b1:
            st.markdown(f"<a href='{wa_link}' target='_blank'><button style='width:100%; padding:10px; background-color:#25D366; color:white; border:none; border-radius:5px;'>🟢 ارسال در واتس‌اپ</button></a>", unsafe_allow_html=True)
        with b2:
            st.markdown(f"<a href='{tg_link}' target='_blank'><button style='width:100%; padding:10px; background-color:#0088cc; color:white; border:none; border-radius:5px;'>🔵 ارسال در تلگرام / ایتا</button></a>", unsafe_allow_html=True)
        with b3:
            if st.button("بستن فاکتور"):
                st.session_state.last_invoice = None
                st.rerun()

# ==========================================
# بخش 2: مدیریت انبار (سانسور قیمت خرید)
# ==========================================
elif choice == "📦 مدیریت انبار":
    st.header("📦 مدیریت انبار مرکزی")
    
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT code, name, compatible_cars, category, purchase_price, sale_price, stock FROM products", conn)
    conn.close()

    # تغییر نام ستون‌ها برای نمایش
    rename_cols = {
        'code': 'کد کالا', 'name': 'نام کالا', 'compatible_cars': 'خودروهای سازگار',
        'category': 'دسته‌بندی', 'sale_price': 'قیمت فروش', 'stock': 'موجودی'
    }
    
    if st.session_state.is_admin:
        rename_cols['purchase_price'] = 'قیمت خرید (محرمانه)'
    else:
        df = df.drop(columns=['purchase_price']) # مخفی کردن قیمت خرید برای همه غیر از ادمین

    df = df.rename(columns=rename_cols)
    
    search = st.text_input("🔍 جستجو در کل انبار (نام، خودرو، دسته):")
    if search:
        mask = df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
        display_df = df[mask]
    else:
        display_df = df

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    if st.session_state.is_admin:
        st.markdown("---")
        st.subheader("🛠️ ویرایش / حذف کالا")
        edit_code = st.text_input("کد کالا برای ویرایش را وارد/اسکن کنید:")
        if edit_code:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT * FROM products WHERE code=?", (edit_code,))
            prod = c.fetchone()
            conn.close()

            if prod:
                e_name = st.text_input("نام کالا", prod[1])
                e_car = st.text_input("خودروهای سازگار", prod[6] if len(prod)>6 else "عمومی")
                e_buy = st.number_input("قیمت خرید", value=int(prod[3]), step=10000)
                e_sell = st.number_input("قیمت فروش", value=int(prod[4]), step=10000)
                e_stock = st.number_input("موجودی", value=int(prod[5]))
                
                c1, c2 = st.columns(2)
                if c1.button("💾 ذخیره تغییرات", type="primary"):
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("UPDATE products SET name=?, compatible_cars=?, purchase_price=?, sale_price=?, stock=? WHERE code=?",
                              (e_name, e_car, e_buy, e_sell, e_stock, edit_code))
                    conn.commit()
                    conn.close()
                    st.success("ویرایش شد!")
                    st.rerun()
                if c2.button("🗑️ حذف کالا"):
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("DELETE FROM products WHERE code=?", (edit_code,))
                    conn.commit()
                    conn.close()
                    st.warning("حذف شد!")
                    st.rerun()

# ==========================================
# بخش 3: افزودن کالا (جای‌گذاری خودکار اسکنر)
# ==========================================
elif choice == "➕ افزودن کالای جدید":
    if not st.session_state.is_admin:
        st.error("🔒 فقط ادمین مجاز به افزودن کالا است.")
    else:
        st.header("➕ تعریف کالای جدید")
        
        # مدیریت هوشمند اسکنر
        if "auto_code" not in st.session_state:
            st.session_state.auto_code = ""

        if HAS_SCANNER_PKG:
            st.info("بارکد را مقابل دوربین بگیرید تا خودکار در فرم پر شود:")
            scanned = qrcode_scanner(key='add_scanner')
            if scanned:
                st.session_state.auto_code = scanned

        p_code = st.text_input("کد کالا / بارکد:", value=st.session_state.auto_code)
        p_name = st.text_input("نام دستگاه / کالا *")
        p_car = st.text_input("مناسب برای خودروی (مثال: 206، پارس، عمومی):", "عمومی")
        p_cat = st.selectbox("دسته‌بندی", ["هدلایت و لامپ", "روکش و کفپوش", "سیستم صوتی", "دزدگیر و ردیاب", "سایر"])
        
        col1, col2, col3 = st.columns(3)
        with col1: p_buy = st.number_input("قیمت خرید", min_value=0, step=10000)
        with col2: p_sell = st.number_input("قیمت فروش", min_value=0, step=10000)
        with col3: p_stock = st.number_input("موجودی", min_value=0, step=1)

        if st.button("➕ ثبت در انبار", type="primary"):
            if not p_name:
                st.error("نام کالا الزامی است!")
            else:
                final_code = p_code.strip() if p_code.strip() else "AUTO-" + get_iran_time().strftime("%Y%m%d%H%M%S")
                try:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("INSERT INTO products (code, name, category, purchase_price, sale_price, stock, compatible_cars) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (final_code, p_name, p_cat, p_buy, p_sell, p_stock, p_car))
                    conn.commit()
                    conn.close()
                    st.success("✅ ثبت شد!")
                    st.session_state.auto_code = "" # ریست کردن اسکنر
                except sqlite3.IntegrityError:
                    st.error("این کد تکراری است.")

# ==========================================
# بخش 4: گزارش‌ها (محاسبه سود خالص)
# ==========================================
elif choice == "📊 گزارش‌های مالی":
    if not st.session_state.is_admin:
        st.error("🔒 فقط ادمین مجاز به مشاهده گزارش مالی است.")
    else:
        st.header("📊 گزارش مالی و سود خالص")
        
        conn = sqlite3.connect(DB_NAME)
        full_df = pd.read_sql_query("SELECT * FROM sales", conn)
        conn.close()

        if not full_df.empty:
            full_df['timestamp'] = pd.to_datetime(full_df['timestamp'])
            now_dt = get_iran_time().replace(tzinfo=None)
            
            # رفع مشکل تایم‌زون پانداز
            full_df['timestamp'] = full_df['timestamp'].dt.tz_localize(None)
            
            daily_df = full_df[full_df['timestamp'] >= (now_dt - timedelta(days=1))]
            monthly_df = full_df[full_df['timestamp'] >= (now_dt - timedelta(days=31))]
            
            t1, t2 = st.tabs(["📅 فروش ۲۴ ساعت گذشته", "📆 فروش یک ماه گذشته"])
            
            with t1:
                if not daily_df.empty:
                    daily_sale = (daily_df['quantity'] * daily_df['sale_price']).sum() + daily_df['install_fee'].sum()
                    daily_profit = daily_df['net_profit'].sum()
                    st.success(f"💳 جمع کل فروش: {daily_sale:,.0f} تومان  |  📈 سود خالص شما: {daily_profit:,.0f} تومان")
                    st.dataframe(daily_df[['sale_date', 'name', 'customer_name', 'quantity', 'install_fee', 'net_profit']], hide_index=True)
            with t2:
                if not monthly_df.empty:
                    m_sale = (monthly_df['quantity'] * monthly_df['sale_price']).sum() + monthly_df['install_fee'].sum()
                    m_profit = monthly_df['net_profit'].sum()
                    st.success(f"💳 کل فروش ماه: {m_sale:,.0f} تومان  |  📈 سود خالص ماه: {m_profit:,.0f} تومان")
                    st.dataframe(monthly_df[['sale_date', 'name', 'customer_name', 'quantity', 'install_fee', 'net_profit']], hide_index=True)
        else:
            st.info("فروشی ثبت نشده است.")

# ==========================================
# بخش 5: دفتر حساب (چک و اقساط)
# ==========================================
elif choice == "📒 دفتر حساب (چک و اقساط)":
    if not st.session_state.is_admin:
        st.error("🔒 فقط ادمین (صاحب مغازه) به دفتر حساب دسترسی دارد.")
    else:
        st.header("📒 دفتر حساب دفتری و چک‌ها")
        
        tb1, tb2 = st.tabs(["💵 مطالبات (طلب از مشتریان)", "💳 بدهی‌ها (چک‌های مغازه به بازار)"])
        
        def render_ledger(l_type, title, person_label):
            with st.form(f"form_{l_type}"):
                st.subheader(f"➕ ثبت {title} جدید")
                c1, c2 = st.columns(2)
                with c1: 
                    name = st.text_input(person_label)
                    amt = st.number_input("مبلغ (تومان)", min_value=0, step=100000)
                with c2:
                    date = st.text_input("تاریخ سررسید / چک (مثال: 1403/05/20)")
                    desc = st.text_input("بابت / توضیحات اضافی")
                if st.form_submit_button("ثبت در دفتر"):
                    if name and amt > 0:
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        now_str = jdatetime.datetime.fromgregorian(datetime=get_iran_time()).strftime('%Y/%m/%d')
                        c.execute("INSERT INTO ledger (record_type, person_name, amount, due_date, description, status, timestamp) VALUES (?,?,?,?,?,?,?)",
                                  (l_type, name, amt, date, desc, "معلق", now_str))
                        conn.commit()
                        conn.close()
                        st.success("با موفقیت ثبت شد!")
                        st.rerun()
            
            st.markdown("---")
            conn = sqlite3.connect(DB_NAME)
            df = pd.read_sql_query(f"SELECT id, person_name as '{person_label}', amount as 'مبلغ', due_date as 'تاریخ سررسید', description as 'بابت', status as 'وضعیت' FROM ledger WHERE record_type='{l_type}'", conn)
            conn.close()
            
            if not df.empty:
                st.dataframe(df, hide_index=True, use_container_width=True)
                
                clr_id = st.number_input(f"برای تسویه/پاک کردن {title}، شماره ردیف (id) را وارد کنید:", min_value=0, key=f"clr_{l_type}")
                if st.button("✅ تسویه و حذف از دفتر", key=f"btn_{l_type}"):
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("DELETE FROM ledger WHERE id=?", (clr_id,))
                    conn.commit()
                    conn.close()
                    st.success("ردیف با موفقیت تسویه و پاک شد.")
                    st.rerun()
            else:
                st.info("موردی ثبت نشده است.")

        with tb1:
            render_ledger("customer_debt", "طلب از مشتری", "نام مشتری بدهکار")
        with tb2:
            render_ledger("owner_debt", "بدهی / چک پرداختی", "نام شخص/شرکت طلبکار")
