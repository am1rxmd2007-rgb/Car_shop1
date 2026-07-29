import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import jdatetime
import pytz
import urllib.parse

# ایمپورت اسکنر حرفه‌ای و خودکار بارکد
try:
    from streamlit_qrcode_scanner import qrcode_scanner
    HAS_SCANNER_PKG = True
except ImportError:
    HAS_SCANNER_PKG = False

# ==========================================
# تنظیمات صفحه (عریض برای دسکتاپ و موبایل)
# ==========================================
st.set_page_config(page_title="مدیریت انبار و فروشگاه", page_icon="🚗", layout="wide")

# CSS امن و اصلاح‌شده (بدون باگ به هم ریختگی کلمات)
st.markdown("""
<style>
    .stMarkdown, p, h1, h2, h3, h4, label {
        direction: rtl;
        text-align: right;
        font-family: 'Tahoma', sans-serif !important;
    }
    .stButton>button {
        width: 100%;
        border-radius: 8px;
    }
    .invoice-box {
        border: 2px dashed #4CAF50;
        padding: 20px;
        border-radius: 10px;
        background-color: #f9f9f9;
        color: #333;
        margin-top: 15px;
        direction: rtl;
        text-align: right;
    }
</style>
""", unsafe_allow_html=True)

def get_iran_time():
    iran_tz = pytz.timezone('Asia/Tehran')
    return datetime.now(iran_tz)

# ==========================================
# توابع دیتابیس SQLite
# ==========================================
DB_NAME = "inventory.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # جدول محصولات
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (code TEXT PRIMARY KEY, name TEXT, category TEXT,
                  purchase_price REAL, sale_price REAL, stock INTEGER)''')
    
    # ارتقاء جدول محصولات برای اضافه شدن ماشین سازگار (بدون پاک شدن اطلاعات قبلی)
    c.execute("PRAGMA table_info(products)")
    cols = [col[1] for col in c.fetchall()]
    if 'compatible_cars' not in cols:
        c.execute("ALTER TABLE products ADD COLUMN compatible_cars TEXT DEFAULT 'عمومی'")

    # جدول فروش
    c.execute('''CREATE TABLE IF NOT EXISTS sales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  product_code TEXT, name TEXT, quantity INTEGER,
                  sale_price REAL, sale_date TEXT, timestamp DATETIME)''')
                  
    # ارتقاء جدول فروش برای اطلاعات مشتری، اجرت و سود (بدون پاک شدن اطلاعات قبلی)
    c.execute("PRAGMA table_info(sales)")
    sales_cols = [col[1] for col in c.fetchall()]
    if 'customer_name' not in sales_cols:
        c.execute("ALTER TABLE sales ADD COLUMN customer_name TEXT DEFAULT ''")
        c.execute("ALTER TABLE sales ADD COLUMN customer_phone TEXT DEFAULT ''")
        c.execute("ALTER TABLE sales ADD COLUMN car_model TEXT DEFAULT ''")
        c.execute("ALTER TABLE sales ADD COLUMN install_fee REAL DEFAULT 0")
        c.execute("ALTER TABLE sales ADD COLUMN net_profit REAL DEFAULT 0")

    # جدول جدید: دفتر حساب دفتری و چک
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
# مدیریت وضعیت سیستم (Session State)
# ==========================================
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "last_invoice" not in st.session_state:
    st.session_state.last_invoice = None
if "auto_code" not in st.session_state:
    st.session_state.auto_code = ""

# ==========================================
# منوی کناری (سایدبار) و بخش ورود ادمین
# ==========================================
st.sidebar.title("🚗 سیستم مدیریت فروشگاه")
st.sidebar.markdown("---")

menu = ["🛒 ثبت فروش / بررسی کالا", "📦 مدیریت انبار", "➕ افزودن کالای جدید", "📊 گزارش‌ها", "📒 دفتر حساب (چک و اقساط)"]
choice = st.sidebar.radio("منوی اصلی:", menu)

st.sidebar.markdown("---")
st.sidebar.subheader("🔐 بخش مدیریت (ادمین)")
if not st.session_state.is_admin:
    admin_pass = st.sidebar.text_input("رمز عبور ادمین را وارد کنید:", type="password", key="sidebar_admin_pass")
    if st.sidebar.button("ورود به ادمین"):
        if admin_pass == "2613":
            st.session_state.is_admin = True
            st.sidebar.success("با موفقیت به عنوان ادمین وارد شدید!")
            st.rerun()
        else:
            st.sidebar.error("رمز عبور اشتباه است!")
else:
    st.sidebar.success("شما ادمین هستید ✅")
    
    # دکمه ریست کلی سیستم (مخصوص ادمین)
    st.sidebar.markdown("---")
    st.sidebar.warning("⚠️ ناحیه خطرناک")
    if st.sidebar.button("🗑️ پاک کردن کل داده‌ها و ریست سیستم"):
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("DROP TABLE IF EXISTS products")
        c.execute("DROP TABLE IF EXISTS sales")
        c.execute("DROP TABLE IF EXISTS ledger")
        conn.commit()
        conn.close()
        init_db()
        st.sidebar.success("سیستم با موفقیت پاک و ریست شد!")
        st.rerun()

    if st.sidebar.button("خروج از حساب ادمین"):
        st.session_state.is_admin = False
        st.rerun()

# هشدار کمبود موجودی در سایدبار
low_stock_df = get_low_stock_products()
if not low_stock_df.empty:
    st.sidebar.markdown("---")
    st.sidebar.error("⚠️ هشدار کمبود موجودی:")
    for _, row in low_stock_df.iterrows():
        st.sidebar.warning(f"کالای '{row['name']}' فقط {row['stock']} عدد")

# ==========================================
# بخش 1: ثبت فروش و بررسی کالا (عمومی برای همه)
# ==========================================
if choice == "🛒 ثبت فروش / بررسی کالا":
    st.header("🛒 ثبت فروش و صدور فاکتور مشتری")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.info("🔹 روش ورود کالا: از طریق بارکدخوان فیزیکی، اسکنر دوربین یا جستجوی نام کالا.")
        scan_method = st.radio("انتخاب روش:", ("کیبورد / بارکدخوان فیزیکی", "دوربین (اسکنر خودکار)", "جستجوی نام کالا"))
        
        code_input = ""
        
        if scan_method == "کیبورد / بارکدخوان فیزیکی":
            code_input = st.text_input("کد کالا را اینجا اسکن یا وارد کنید:", key="barcode_input")
            
        elif scan_method == "دوربین (اسکنر خودکار)":
            if HAS_SCANNER_PKG:
                st.markdown("📷 **دوربین فعال است. بارکد را مقابل دوربین بگیرید:**")
                scanned_code = qrcode_scanner(key='pro_scanner')
                if scanned_code:
                    code_input = scanned_code
                    st.success(f"✅ اسکن موفق: {code_input}")
            else:
                st.error("کتابخانه اسکنر نصب نیست.")
                
        elif scan_method == "جستجوی نام کالا":
            search_sale_query = st.text_input("نام بخشی از کالا را برای فروش وارد کنید:")
            if search_sale_query:
                conn = sqlite3.connect(DB_NAME)
                match_df = pd.read_sql_query(f"SELECT code, name, compatible_cars FROM products WHERE name LIKE '%{search_sale_query}%' OR compatible_cars LIKE '%{search_sale_query}%'", conn)
                conn.close()
                if not match_df.empty:
                    opts = (match_df['name'] + " (مناسب: " + match_df['compatible_cars'] + ") - کد: " + match_df['code']).tolist()
                    selected_name = st.selectbox("کالای مورد نظر را انتخاب کنید:", opts)
                    code_input = selected_name.split("کد: ")[1].strip()
                else:
                    st.warning("کالایی با این نام پیدا نشد.")

    with col2:
        if code_input:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT code, name, category, purchase_price, sale_price, stock, compatible_cars FROM products WHERE code=?", (code_input,))
            product = c.fetchone()
            conn.close()

            if product:
                st.subheader(f"📦 مشخصات دستگاه/کالا: {product[1]}")
                st.markdown(f"**دسته‌بندی:** {product[2]}")
                st.markdown(f"**مناسب برای خودروی:** {product[6]}")
                
                stock_color = "red" if product[5] < 3 else "green"
                st.markdown(f"**قیمت فروش:** {product[4]:,.0f} تومان")
                
                # نمایش قیمت خرید فقط برای ادمین
                if st.session_state.is_admin:
                    st.markdown(f"**قیمت خرید (محرمانه):** <span style='color:orange;'>{product[3]:,.0f} تومان</span>", unsafe_allow_html=True)
                
                st.markdown(f"**موجودی انبار:** <span style='color:{stock_color}; font-size:20px; font-weight:bold;'>{product[5]}</span> عدد", unsafe_allow_html=True)

                st.markdown("---")
                with st.form("sale_form"):
                    st.markdown("📝 **اطلاعات فروش و باشگاه مشتریان**")
                    sale_qty = st.number_input("تعداد فروش", min_value=1, max_value=product[5] if product[5] > 0 else 1, value=1)
                    install_fee = st.number_input("اجرت نصب (تومان) - اختیاری", min_value=0, step=10000, value=0)
                    
                    cc1, cc2, cc3 = st.columns(3)
                    with cc1: c_name = st.text_input("نام مشتری (اختیاری)")
                    with cc2: c_phone = st.text_input("شماره موبایل (اختیاری)")
                    with cc3: c_car = st.text_input("مدل ماشین مشتری")

                    submit_sale = st.form_submit_button("✅ ثبت نهایی فروش و کسر از انبار")

                    if submit_sale:
                        if product[5] >= sale_qty:
                            new_stock = product[5] - sale_qty
                            now_dt = get_iran_time()
                            now_str = jdatetime.datetime.fromgregorian(datetime=now_dt).strftime('%Y/%m/%d - %H:%M:%S')
                            
                            net_profit = ((product[4] - product[3]) * sale_qty) + install_fee
                            total_bill = (product[4] * sale_qty) + install_fee
                            
                            conn = sqlite3.connect(DB_NAME)
                            c = conn.cursor()
                            c.execute("UPDATE products SET stock=? WHERE code=?", (new_stock, code_input))
                            c.execute('''INSERT INTO sales 
                                      (product_code, name, quantity, sale_price, sale_date, timestamp, 
                                       customer_name, customer_phone, car_model, install_fee, net_profit) 
                                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                      (code_input, product[1], sale_qty, product[4], now_str, now_dt,
                                       c_name, c_phone, c_car, install_fee, net_profit))
                            conn.commit()
                            conn.close()
                            
                            st.session_state.last_invoice = {
                                "date": now_str, "c_name": c_name or "مشتری نقدی",
                                "c_phone": c_phone, "c_car": c_car, "p_name": product[1],
                                "qty": sale_qty, "price": product[4], "install": install_fee, "total": total_bill
                            }
                            st.success(f"فروش با موفقیت ثبت شد!")
                            st.rerun()
                        else:
                            st.error("موجودی کالا برای این تعداد فروش کافی نیست!")
            else:
                st.warning("⚠️ کالایی با این کد در سیستم ثبت نشده است.")

    # نمایش فاکتور دیجیتال آخرین فروش و دکمه ارسال
    if st.session_state.last_invoice:
        inv = st.session_state.last_invoice
        st.markdown("---")
        st.subheader("🧾 فاکتور دیجیتال مشتری")
        
        invoice_text = f"""🧾 فاکتور فروشگاه
تاریخ: {inv['date']}
👤 مشتری: {inv['c_name']}
🚗 خودرو: {inv['c_car']}
-------------------
📦 کالا: {inv['p_name']}
🔢 تعداد: {inv['qty']}
💵 قیمت واحد: {inv['price']:,} تومان
🔧 اجرت نصب: {inv['install']:,} تومان
-------------------
💰 جمع کل فاکتور: {inv['total']:,} تومان
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
# بخش 2: مدیریت انبار (لیست کامل، اجناس ناموجود و ابزار ادمین)
# ==========================================
elif choice == "📦 مدیریت انبار":
    st.header("📦 انبار مرکزی فروشگاه")
    
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT code as 'کد کالا', name as 'نام دستگاه/کالا', compatible_cars as 'خودروهای سازگار', category as 'دسته‌بندی', purchase_price as 'قیمت خرید', sale_price as 'قیمت فروش', stock as 'موجودی' FROM products", conn)
    conn.close()

    # مخفی کردن قیمت خرید برای افراد غیر ادمین
    if not st.session_state.is_admin:
        df = df.drop(columns=['قیمت خرید'])

    # ---- بخش اول: لیست کامل تمام کالاها با تمامی اطلاعات و جستجوی سریع ----
    st.subheader("📋 لیست کامل تمام کالاها")
    
    search_col1, search_col2 = st.columns([2, 1])
    with search_col1:
        search = st.text_input("🔍 جستجوی سریع (نام، ماشین، دسته یا کد):")
    with search_col2:
        scan_in_inventory = st.checkbox("فعال‌سازی اسکنر برای جستجو")

    query_code = ""
    if scan_in_inventory and HAS_SCANNER_PKG:
        st.info("بارکد کالا را برای یافتن در انبار اسکن کنید:")
        scanned_inv = qrcode_scanner(key='inventory_search_scanner')
        if scanned_inv:
            query_code = scanned_inv
            st.success(f"کد اسکن شده: {query_code}")

    display_df = df.copy()
    if search:
        mask = display_df.apply(lambda row: row.astype(str).str.contains(search, case=False).any(), axis=1)
        display_df = display_df[mask]
    elif query_code:
        display_df = display_df[display_df['کد کالا'] == query_code]

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ---- بخش دوم: اجناس ناموجود (موجودی صفر) دقیقاً در زیر بخش اول ----
    st.subheader("🔴 اجناس ناموجود (موجودی صفر)")
    out_of_stock_df = df[df['موجودی'] == 0]
    if not out_of_stock_df.empty:
        st.error(f"⚠️ تعداد {len(out_of_stock_df)} کالا موجودی‌شان تمام شده و صفر است:")
        st.dataframe(out_of_stock_df, use_container_width=True, hide_index=True)
    else:
        st.success("✅ عالی! هیچ کالایی با موجودی صفر (ناموجود) در انبار وجود ندارد.")

    st.markdown("---")
    
    # ---- بخش سوم: مدیریت، جستجو، ویرایش و حذف (فقط ادمین) ----
    if st.session_state.is_admin:
        st.subheader("🛠️ ویرایش یا حذف کالا (مخصوص ادمین)")
        
        manage_mode = st.radio("روش انتخاب کالا:", ("جستجوی نام یا کد", "ورود دستی کد", "اسکن با دوربین (اسکنر)"), key="manage_mode")
        edit_code = ""
        
        if manage_mode == "جستجوی نام یا کد":
            search_edit_query = st.text_input("بخشی از نام یا کد کالا را برای ویرایش/حذف جستجو کنید:", key="search_edit_query_input")
            if search_edit_query:
                conn = sqlite3.connect(DB_NAME)
                match_df = pd.read_sql_query(f"SELECT code, name FROM products WHERE name LIKE '%{search_edit_query}%' OR code LIKE '%{search_edit_query}%'", conn)
                conn.close()
                if not match_df.empty:
                    options = (match_df['code'] + " - " + match_df['name']).tolist()
                    selected_option = st.selectbox("کالای مورد نظر را از لیست انتخاب کنید:", options, key="select_edit_product")
                    if selected_option:
                        edit_code = selected_option.split(" - ")[0]
                else:
                    st.warning("کالایی با این مشخصات پیدا نشد.")
                    
        elif manage_mode == "اسکن با دوربین (اسکنر)":
            if HAS_SCANNER_PKG:
                st.info("بارکد کالا را برای ویرایش/حذف اسکن کنید:")
                scanned_edit = qrcode_scanner(key='manage_scanner_widget')
                if scanned_edit:
                    edit_code = scanned_edit
                    st.success(f"کد اسکن شد: {edit_code}")
            else:
                st.error("کتابخانه اسکنر نصب نیست.")
        else:
            edit_code = st.text_input("کد کالای مورد نظر را وارد کنید:", key="manual_edit_input")
        
        if edit_code:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT code, name, category, purchase_price, sale_price, stock, compatible_cars FROM products WHERE code=?", (edit_code,))
            prod = c.fetchone()
            conn.close()

            if prod:
                st.info(f"در حال ویرایش کالا: {prod[1]}")
                e_name = st.text_input("نام دستگاه/کالا", prod[1], key="e_name")
                e_car = st.text_input("خودروهای سازگار", prod[6], key="e_car")
                e_cat = st.text_input("دسته‌بندی", prod[2], key="e_cat")
                e_buy = st.number_input("قیمت خرید", value=int(prod[3]), step=1000, key="e_buy")
                e_sell = st.number_input("قیمت فروش", value=int(prod[4]), step=1000, key="e_sell")
                e_stock = st.number_input("موجودی", value=int(prod[5]), step=1, key="e_stock")

                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    if st.button("💾 ذخیره تغییرات", type="primary"):
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        c.execute("UPDATE products SET name=?, category=?, purchase_price=?, sale_price=?, stock=?, compatible_cars=? WHERE code=?",
                                  (e_name, e_cat, e_buy, e_sell, e_stock, e_car, edit_code))
                        conn.commit()
                        conn.close()
                        st.success("اطلاعات کالا با موفقیت به‌روزرسانی شد.")
                        st.rerun()
                with col_c2:
                    if st.button("🗑️ حذف کالا", type="secondary"):
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        c.execute("DELETE FROM products WHERE code=?", (edit_code,))
                        conn.commit()
                        conn.close()
                        st.warning("کالا از انبار حذف شد.")
                        st.rerun()
            else:
                st.warning("⚠️ کالایی با این کد در انبار یافت نشد.")
    else:
        st.info("🔒 برای ویرایش یا حذف کالا، لطفاً از منوی سمت چپ (سایدبار) با رمز ادمین وارد شوید.")

# ==========================================
# بخش 3: افزودن کالای جدید (مخصوص ادمین - بدون نیاز اجباری به بارکد)
# ==========================================
elif choice == "➕ افزودن کالای جدید":
    if not st.session_state.is_admin:
        st.error("🔒 دسترسی محدود! این بخش فقط مخصوص ادمین است.")
    else:
        st.header("➕ تعریف کالای جدید در انبار")
        
        add_mode = st.radio("روش ورود کد کالا:", ("ورود دستی یا بدون بارکد", "اسکن با دوربین (اسکنر)"), key="add_mode")
        
        if add_mode == "اسکن با دوربین (اسکنر)":
            if HAS_SCANNER_PKG:
                st.info("بارکد جدید را مقابل دوربین بگیرید:")
                scanned = qrcode_scanner(key='add_scanner_widget')
                if scanned:
                    st.session_state.auto_code = scanned
                    st.success(f"بارکد با موفقیت اسکن شد: {scanned}")
            else:
                st.error("کتابخانه اسکنر نصب نیست.")
        
        default_val = st.session_state.auto_code if add_mode == "اسکن با دوربین (اسکنر)" else ""
        
        p_code = st.text_input("کد / بارکد کالا (اختیاری - اگر خالی باشد خودکار ساخته می‌شود)", value=default_val, key="p_code_input")
        p_name = st.text_input("نام دستگاه / کالا *", key="p_name_input")
        p_car = st.text_input("مناسب برای خودروی (مثال: 206، پارس، عمومی):", "عمومی")
        p_cat = st.selectbox("دسته‌بندی", ["هدلایت و لامپ", "روکش و کفپوش", "مانیتور و سیستم صوتی", "دزدگیر و ردیاب", "تزئینات و خوشبوکننده", "سایر"], key="p_cat_input")
        
        col1, col2 = st.columns(2)
        with col1:
            p_buy = st.number_input("قیمت خرید (تومان)", min_value=0, step=1000, key="p_buy_input")
            st.markdown(f"<p style='color: #555; font-size: 13px; margin-top: -15px;'>مبلغ: <b>{p_buy:,.0f}</b> تومان</p>", unsafe_allow_html=True)
            
            p_sell = st.number_input("قیمت فروش (تومان)", min_value=0, step=1000, key="p_sell_input")
            st.markdown(f"<p style='color: #555; font-size: 13px; margin-top: -15px;'>مبلغ: <b>{p_sell:,.0f}</b> تومان</p>", unsafe_allow_html=True)
            
        with col2:
            p_stock = st.number_input("موجودی اولیه (تعداد)", min_value=0, step=1, key="p_stock_input")

        if st.button("➕ ثبت نهایی کالا در انبار", type="primary"):
            if not p_name.strip():
                st.error("نام کالا الزامی است.")
            else:
                if not p_code.strip():
                    p_code = "AUTO-" + get_iran_time().strftime("%Y%m%d%H%M%S")
                try:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("INSERT INTO products (code, name, category, purchase_price, sale_price, stock, compatible_cars) VALUES (?, ?, ?, ?, ?, ?, ?)",
                              (p_code, p_name, p_cat, p_buy, p_sell, p_stock, p_car))
                    conn.commit()
                    conn.close()
                    st.success(f"کالای '{p_name}' با کد ({p_code}) با موفقیت در انبار ثبت شد.")
                    st.session_state.auto_code = ""
                except sqlite3.IntegrityError:
                    st.error("این کد کالا قبلاً در سیستم ثبت شده است! لطفاً کد دیگری وارد کنید.")

# ==========================================
# بخش 4: گزارش‌ها (محاسبه سود خالص)
# ==========================================
elif choice == "📊 گزارش‌ها":
    if not st.session_state.is_admin:
        st.error("🔒 دسترسی محدود! این بخش فقط مخصوص ادمین است.")
    else:
        st.header("📊 گزارش‌های فروش و مالی")
        
        tab_daily, tab_monthly, tab_all = st.tabs(["📅 گزارش روزانه (۲۴ ساعت)", "📆 گزارش ماهانه (۳۱ روز)", "♾️ گزارش همیشگی"])
        
        conn = sqlite3.connect(DB_NAME)
        full_df = pd.read_sql_query("SELECT id as 'کد فاکتور', product_code as 'کد کالا', name as 'نام کالا', customer_name as 'مشتری', quantity as 'تعداد', sale_price as 'قیمت واحد', install_fee as 'اجرت نصب', net_profit as 'سود خالص', sale_date as 'تاریخ و ساعت', timestamp FROM sales", conn)
        conn.close()

        if not full_df.empty:
            full_df['timestamp'] = pd.to_datetime(full_df['timestamp'])
            now_dt = get_iran_time().replace(tzinfo=None)
            full_df['timestamp'] = full_df['timestamp'].dt.tz_localize(None)
            
            daily_df = full_df[full_df['timestamp'] >= (now_dt - timedelta(days=1))].copy()
            monthly_df = full_df[full_df['timestamp'] >= (now_dt - timedelta(days=31))].copy()
            
            display_cols = ['کد فاکتور', 'نام کالا', 'مشتری', 'تعداد', 'قیمت واحد', 'اجرت نصب', 'سود خالص', 'تاریخ و ساعت']
            
            with tab_daily:
                st.subheader("فروش ۲۴ ساعت گذشته")
                if not daily_df.empty:
                    daily_sale = (daily_df['تعداد'] * daily_df['قیمت واحد']).sum() + daily_df['اجرت نصب'].sum()
                    daily_profit = daily_df['سود خالص'].sum()
                    st.success(f"💰 جمع کل درآمد (با اجرت): {daily_sale:,.0f} تومان | 📈 سود خالص شما: {daily_profit:,.0f} تومان | 📦 تعداد: {daily_df['تعداد'].sum()} عدد")
                    st.dataframe(daily_df[display_cols], use_container_width=True, hide_index=True)
                else:
                    st.info("در ۲۴ ساعت گذشته فروشی ثبت نشده است.")
                    
            with tab_monthly:
                st.subheader("فروش ۳۱ روز گذشته")
                if not monthly_df.empty:
                    m_sale = (monthly_df['تعداد'] * monthly_df['قیمت واحد']).sum() + monthly_df['اجرت نصب'].sum()
                    m_profit = monthly_df['سود خالص'].sum()
                    st.success(f"💰 جمع کل درآمد: {m_sale:,.0f} تومان | 📈 سود خالص ماه: {m_profit:,.0f} تومان | 📦 تعداد: {monthly_df['تعداد'].sum()} عدد")
                    st.dataframe(monthly_df[display_cols], use_container_width=True, hide_index=True)
                else:
                    st.info("در ۳۱ روز گذشته فروشی ثبت نشده است.")
                    
            with tab_all:
                st.subheader("تاریخچه کامل و همیشگی فروش‌ها")
                a_sale = (full_df['تعداد'] * full_df['قیمت واحد']).sum() + full_df['اجرت نصب'].sum()
                a_profit = full_df['سود خالص'].sum()
                st.success(f"💰 کل درآمد تاریخی: {a_sale:,.0f} تومان | 📈 کل سود خالص تاریخی: {a_profit:,.0f} تومان")
                st.dataframe(full_df[display_cols], use_container_width=True, hide_index=True)
        else:
            st.info("تا کنون هیچ فروشی در سیستم ثبت نشده است.")

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
            df = pd.read_sql_query(f"SELECT id as 'شماره ردیف', person_name as '{person_label}', amount as 'مبلغ', due_date as 'تاریخ سررسید', description as 'بابت', status as 'وضعیت' FROM ledger WHERE record_type='{l_type}'", conn)
            conn.close()
            
            if not df.empty:
                st.dataframe(df, hide_index=True, use_container_width=True)
                
                clr_id = st.number_input(f"برای تسویه/پاک کردن {title}، شماره ردیف مربوطه را وارد کنید:", min_value=0, key=f"clr_{l_type}")
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
