import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import jdatetime

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

# CSS امن و بدون باگ برای راست‌چین کردن متن‌ها
st.markdown("""
<style>
    .stMarkdown, p, h1, h2, h3, h4, label {
        direction: rtl;
        text-align: right;
        font-family: 'Tahoma', sans-serif !important;
    }
    .stButton>button {
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# توابع دیتابیس SQLite
# ==========================================
DB_NAME = "inventory.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (code TEXT PRIMARY KEY, name TEXT, category TEXT,
                  purchase_price REAL, sale_price REAL, stock INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  product_code TEXT, name TEXT, quantity INTEGER,
                  sale_price REAL, sale_date TEXT, timestamp DATETIME)''')
    conn.commit()
    conn.close()

def get_low_stock_products():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT name, stock FROM products WHERE stock < 3", conn)
    conn.close()
    return df

init_db()

# ==========================================
# مدیریت وضعیت ادمین (Session State)
# ==========================================
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

# ==========================================
# منوی کناری (سایدبار) و بخش ورود ادمین
# ==========================================
st.sidebar.title("🚗 سیستم مدیریت فروشگاه")
st.sidebar.markdown("---")

menu = ["🛒 ثبت فروش / بررسی کالا", "📦 مدیریت انبار", "➕ افزودن کالای جدید", "📊 گزارش‌ها"]
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
    st.header("🛒 ثبت فروش و بررسی کالا")
    
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
                match_df = pd.read_sql_query(f"SELECT code, name FROM products WHERE name LIKE '%{search_sale_query}%'", conn)
                conn.close()
                if not match_df.empty:
                    selected_name = st.selectbox("کالای مورد نظر را انتخاب کنید:", match_df['name'].tolist())
                    code_input = match_df[match_df['name'] == selected_name]['code'].values[0]
                else:
                    st.warning("کالایی با این نام پیدا نشد.")

    with col2:
        if code_input:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT * FROM products WHERE code=?", (code_input,))
            product = c.fetchone()
            conn.close()

            if product:
                st.subheader(f"📦 مشخصات دستگاه/کالا: {product[1]}")
                st.markdown(f"**دسته‌بندی:** {product[2]}")
                
                stock_color = "red" if product[5] < 3 else "green"
                st.markdown(f"**قیمت فروش:** {product[4]:,.0f} تومان")
                st.markdown(f"**موجودی انبار:** <span style='color:{stock_color}; font-size:20px; font-weight:bold;'>{product[5]}</span> عدد", unsafe_allow_html=True)

                st.markdown("---")
                with st.form("sale_form"):
                    sale_qty = st.number_input("تعداد فروش", min_value=1, max_value=product[5] if product[5] > 0 else 1, value=1)
                    submit_sale = st.form_submit_button("✅ ثبت نهایی فروش و کسر از انبار")

                    if submit_sale:
                        if product[5] >= sale_qty:
                            new_stock = product[5] - sale_qty
                            now_dt = datetime.now()
                            now_str = jdatetime.datetime.fromgregorian(datetime=now_dt).strftime('%Y/%m/%d - %H:%M:%S')
                            
                            conn = sqlite3.connect(DB_NAME)
                            c = conn.cursor()
                            c.execute("UPDATE products SET stock=? WHERE code=?", (new_stock, code_input))
                            c.execute("INSERT INTO sales (product_code, name, quantity, sale_price, sale_date, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                                      (code_input, product[1], sale_qty, product[4], now_str, now_dt))
                            conn.commit()
                            conn.close()
                            
                            st.success(f"فروش {sale_qty} عدد از '{product[1]}' با موفقیت ثبت شد!")
                            st.rerun()
                        else:
                            st.error("موجودی کالا برای این تعداد فروش کافی نیست!")
            else:
                st.warning("⚠️ کالایی با این کد در سیستم ثبت نشده است.")

# ==========================================
# بخش 2: مدیریت انبار (لیست کامل، اجناس ناموجود و ابزار ادمین)
# ==========================================
elif choice == "📦 مدیریت انبار":
    st.header("📦 انبار مرکزی فروشگاه")
    
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT code as 'کد کالا', name as 'نام دستگاه/کالا', category as 'دسته‌بندی', purchase_price as 'قیمت خرید', sale_price as 'قیمت فروش', stock as 'موجودی' FROM products", conn)
    conn.close()

    # ---- بخش اول: لیست کامل تمام کالاها با تمامی اطلاعات و جستجوی سریع ----
    st.subheader("📋 لیست کامل تمام کالاها با تمام اطلاعات")
    
    search_col1, search_col2 = st.columns([2, 1])
    with search_col1:
        search = st.text_input("🔍 جستجوی سریع (نام یا کد کالا):")
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
        display_df = display_df[(display_df['نام دستگاه/کالا'].str.contains(search, na=False, case=False)) | (display_df['کد کالا'].str.contains(search, na=False, case=False))]
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
            c.execute("SELECT * FROM products WHERE code=?", (edit_code,))
            prod = c.fetchone()
            conn.close()

            if prod:
                st.info(f"در حال ویرایش کالا: {prod[1]}")
                e_name = st.text_input("نام دستگاه/کالا", prod[1], key="e_name")
                e_cat = st.text_input("دسته‌بندی", prod[2], key="e_cat")
                e_buy = st.number_input("قیمت خرید", value=int(prod[3]), step=1000, key="e_buy")
                e_sell = st.number_input("قیمت فروش", value=int(prod[4]), step=1000, key="e_sell")
                e_stock = st.number_input("موجودی", value=int(prod[5]), step=1, key="e_stock")

                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    if st.button("💾 ذخیره تغییرات", type="primary"):
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        c.execute("UPDATE products SET name=?, category=?, purchase_price=?, sale_price=?, stock=? WHERE code=?",
                                  (e_name, e_cat, e_buy, e_sell, e_stock, edit_code))
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
        st.error("🔒 دسترسی محدود! این بخش فقط مخصوص ادمین است. لطفاً از منوی سمت چپ (سایدبار) با رمز عبور ادمین وارد شوید.")
    else:
        st.header("➕ تعریف کالای جدید در انبار")
        
        add_mode = st.radio("روش ورود کد کالا:", ("ورود دستی یا بدون بارکد", "اسکن با دوربین (اسکنر)"), key="add_mode")
        
        if "scanned_add_code" not in st.session_state:
            st.session_state.scanned_add_code = ""

        if add_mode == "اسکن با دوربین (اسکنر)":
            if HAS_SCANNER_PKG:
                st.info("بارکد جدید را مقابل دوربین بگیرید:")
                scanned = qrcode_scanner(key='add_scanner_widget')
                if scanned:
                    st.session_state.scanned_add_code = scanned
                    st.success(f"بارکد با موفقیت اسکن شد: {scanned}")
            else:
                st.error("کتابخانه اسکنر نصب نیست.")
        
        default_val = st.session_state.scanned_add_code if add_mode == "اسکن با دوربین (اسکنر)" else ""
        
        p_code = st.text_input("کد / بارکد کالا (اختیاری - اگر خالی باشد خودکار ساخته می‌شود)", value=default_val, key="p_code_input")
        p_name = st.text_input("نام دستگاه / کالا *", key="p_name_input")
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
                    p_code = "AUTO-" + datetime.now().strftime("%Y%m%d%H%M%S")
                try:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)",
                              (p_code, p_name, p_cat, p_buy, p_sell, p_stock))
                    conn.commit()
                    conn.close()
                    st.success(f"کالای '{p_name}' با کد ({p_code}) با موفقیت در انبار ثبت شد.")
                    st.session_state.scanned_add_code = ""
                except sqlite3.IntegrityError:
                    st.error("این کد کالا قبلاً در سیستم ثبت شده است! لطفاً کد دیگری وارد کنید.")

# ==========================================
# بخش 4: گزارش‌ها (مخصوص ادمین با تفکیک روزانه، ماهانه و همیشگی)
# ==========================================
elif choice == "📊 گزارش‌ها":
    if not st.session_state.is_admin:
        st.error("🔒 دسترسی محدود! این بخش فقط مخصوص ادمین است. لطفاً از منوی سمت چپ (سایدبار) با رمز ادمین وارد شوید.")
    else:
        st.header("📊 گزارش‌های فروش و مالی")
        
        tab_daily, tab_monthly, tab_all = st.tabs(["📅 گزارش روزانه (۲۴ ساعت)", "📆 گزارش ماهانه (۳۱ روز)", "♾️ گزارش همیشگی"])
        
        conn = sqlite3.connect(DB_NAME)
        full_df = pd.read_sql_query("SELECT id as 'کد فاکتور', product_code as 'کد کالا', name as 'نام دستگاه / کالا', quantity as 'تعداد', sale_price as 'قیمت واحد (تومان)', sale_date as 'تاریخ و ساعت دقیق', timestamp FROM sales", conn)
        conn.close()

        if not full_df.empty:
            full_df['timestamp'] = pd.to_datetime(full_df['timestamp'])
            now_time = datetime.now()
            
            daily_df = full_df[full_df['timestamp'] >= (now_time - timedelta(days=1))].copy()
            monthly_df = full_df[full_df['timestamp'] >= (now_time - timedelta(days=31))].copy()
            
            display_cols = ['کد فاکتور', 'کد کالا', 'نام دستگاه / کالا', 'تعداد', 'قیمت واحد (تومان)', 'تاریخ و ساعت دقیق']
            
            with tab_daily:
                st.subheader("فروش ۲۴ ساعت گذشته")
                if not daily_df.empty:
                    daily_df['جمع کل (تومان)'] = daily_df['تعداد'] * daily_df['قیمت واحد (تومان)']
                    st.success(f"💰 درآمد ۲۴ ساعت: {daily_df['جمع کل (تومان)'].sum():,.0f} تومان | 📦 تعداد: {daily_df['تعداد'].sum()} عدد")
                    st.dataframe(daily_df[display_cols + ['جمع کل (تومان)']], use_container_width=True, hide_index=True)
                else:
                    st.info("در ۲۴ ساعت گذشته فروشی ثبت نشده است.")
                    
            with tab_monthly:
                st.subheader("فروش ۳۱ روز گذشته")
                if not monthly_df.empty:
                    monthly_df['جمع کل (تومان)'] = monthly_df['تعداد'] * monthly_df['قیمت واحد (تومان)']
                    st.success(f"💰 درآمد ۳۱ روز: {monthly_df['جمع کل (تومان)'].sum():,.0f} تومان | 📦 تعداد: {monthly_df['تعداد'].sum()} عدد")
                    st.dataframe(monthly_df[display_cols + ['جمع کل (تومان)']], use_container_width=True, hide_index=True)
                else:
                    st.info("در ۳۱ روز گذشته فروشی ثبت نشده است.")
                    
            with tab_all:
                st.subheader("تاریخچه کامل و همیشگی فروش‌ها")
                full_df['جمع کل (تومان)'] = full_df['تعداد'] * full_df['قیمت واحد (تومان)']
                st.success(f"💰 کل درآمد تاریخی: {full_df['جمع کل (تومان)'].sum():,.0f} تومان | 📦 مجموع کل: {full_df['تعداد'].sum()} عدد")
                st.dataframe(full_df[display_cols + ['جمع کل (تومان)']], use_container_width=True, hide_index=True)
        else:
            st.info("تا کنون هیچ فروشی در سیستم ثبت نشده است.")
