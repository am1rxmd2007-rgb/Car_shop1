import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
from PIL import Image

# تلاش برای ایمپورت کتابخانه بارکدخوان (در صورت عدم نصب، برنامه متوقف نمی‌شود)
try:
    from pyzbar.pyzbar import decode
    HAS_PYZBAR = True
except ImportError:
    HAS_PYZBAR = False

# ==========================================
# تنظیمات صفحه و راست‌چین کردن (RTL)
# ==========================================
st.set_page_config(page_title="مدیریت انبار و فروشگاه", page_icon="🚗", layout="centered")

# تزریق CSS برای راست‌چین کردن کامل و بهبود فونت در موبایل
st.markdown("""
<style>
    .stApp, .stMarkdown, p, div, input, select, label {
        direction: rtl;
        text-align: right;
        font-family: 'Vazirmatn', 'Tahoma', sans-serif !important;
    }
    /* تنظیمات جدول برای موبایل */
    .dataframe {
        font-size: 14px !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# توابع مربوط به دیتابیس (SQLite)
# ==========================================
DB_NAME = "inventory.db"

def init_db():
    """ساخت جداول دیتابیس در صورت عدم وجود"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # جدول محصولات
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (code TEXT PRIMARY KEY, name TEXT, category TEXT,
                  purchase_price REAL, sale_price REAL, stock INTEGER)''')
    # جدول فروش‌ها
    c.execute('''CREATE TABLE IF NOT EXISTS sales
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  product_code TEXT, name TEXT, quantity INTEGER,
                  sale_price REAL, sale_date TEXT)''')
    conn.commit()
    conn.close()

def get_low_stock_products():
    """دریافت کالاهایی که موجودی آن‌ها کمتر از 3 است"""
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT name, stock FROM products WHERE stock < 3", conn)
    conn.close()
    return df

# راه‌اندازی اولیه دیتابیس
init_db()

# ==========================================
# سایدبار و منوی ناوبری
# ==========================================
st.sidebar.title("🚗 سیستم مدیریت فروشگاه")
st.sidebar.markdown("---")
menu = ["🛒 ثبت فروش / اسکن", "📦 مدیریت انبار", "➕ افزودن کالای جدید", "📊 گزارش‌ها"]
choice = st.sidebar.radio("منوی اصلی:", menu)

# نمایش هشدار کمبود موجودی در منوی کناری (همیشه در دسترس)
low_stock_df = get_low_stock_products()
if not low_stock_df.empty:
    st.sidebar.markdown("---")
    st.sidebar.error("⚠️ هشدار کمبود موجودی:")
    for _, row in low_stock_df.iterrows():
        st.sidebar.warning(f"کالای '{row['name']}' فقط {row['stock']} عدد")

# ==========================================
# بخش 1: ثبت فروش و اسکن
# ==========================================
if choice == "🛒 ثبت فروش / اسکن":
    st.header("ثبت فروش و بررسی کالا")
    
    # انتخاب روش ورود کد کالا
    scan_method = st.radio("روش ورود کد کالا:", ("ورود دستی", "دوربین گوشی (اسکنر)"))
    code_input = ""

    if scan_method == "دوربین گوشی (اسکنر)":
        if HAS_PYZBAR:
            img_file_buffer = st.camera_input("از بارکد یا QR Code کالا عکس بگیرید")
            if img_file_buffer is not None:
                image = Image.open(img_file_buffer)
                decoded = decode(image)
                if decoded:
                    code_input = decoded[0].data.decode("utf-8")
                    st.success(f"✅ بارکد خوانده شد: {code_input}")
                else:
                    st.error("❌ بارکدی در تصویر پیدا نشد. لطفاً دوباره عکس بگیرید.")
        else:
            st.error("کتابخانه pyzbar نصب نیست. در حال حاضر فقط ورود دستی امکان‌پذیر است.")

    if scan_method == "ورود دستی" or not code_input:
        code_input = st.text_input("کد یا بارکد کالا را وارد کنید:", placeholder="مثلاً: 123456789")

    # اگر کدی (از طریق دوربین یا دستی) وارد شده باشد
    if code_input:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT * FROM products WHERE code=?", (code_input,))
        product = c.fetchone()
        conn.close()

        if product:
            st.markdown("---")
            st.subheader("مشخصات کالا")
            st.info(f"**نام کالا:** {product[1]} | **دسته‌بندی:** {product[2]}")
            
            # نمایش رنگی موجودی
            stock_color = "red" if product[5] < 3 else "green"
            st.markdown(f"**قیمت فروش:** {product[4]:,.0f} تومان | **موجودی:** <span style='color:{stock_color}; font-weight:bold;'>{product[5]}</span> عدد", unsafe_allow_html=True)

            # فرم ثبت فروش
            with st.form("sale_form"):
                sale_qty = st.number_input("تعداد فروش", min_value=1, max_value=product[5] if product[5] > 0 else 1, value=1)
                submit_sale = st.form_submit_button("✅ ثبت نهایی فروش")

                if submit_sale:
                    if product[5] >= sale_qty:
                        # کسر از موجودی
                        new_stock = product[5] - sale_qty
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        c.execute("UPDATE products SET stock=? WHERE code=?", (new_stock, code_input))
                        # ثبت در گزارش فروش
                        c.execute("INSERT INTO sales (product_code, name, quantity, sale_price, sale_date) VALUES (?, ?, ?, ?, ?)",
                                  (code_input, product[1], sale_qty, product[4], now))
                        conn.commit()
                        conn.close()
                        
                        st.success(f"فروش {sale_qty} عدد '{product[1]}' با موفقیت ثبت شد و از انبار کسر گردید!")
                        # ریفرش کردن صفحه برای آپدیت شدن موجودی در UI
                        st.rerun() 
                    else:
                        st.error("موجودی کالا برای این تعداد فروش کافی نیست!")
        else:
            st.warning("کالایی با این کد در انبار یافت نشد!")

# ==========================================
# بخش 2: مدیریت انبار
# ==========================================
elif choice == "📦 مدیریت انبار":
    st.header("لیست و ویرایش محصولات")
    
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT code as 'کد کالا', name as 'نام کالا', category as 'دسته‌بندی', purchase_price as 'قیمت خرید', sale_price as 'قیمت فروش', stock as 'موجودی' FROM products", conn)
    conn.close()

    # نوار جستجو
    search = st.text_input("🔍 جستجو بر اساس نام یا کد کالا:")
    if search:
        df = df[(df['نام کالا'].str.contains(search, na=False)) | (df['کد کالا'].str.contains(search, na=False))]

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("ویرایش یا حذف کالا")
    edit_code = st.text_input("برای ویرایش یا حذف، **کد کالا** را اینجا وارد کنید:")
    
    if edit_code:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT * FROM products WHERE code=?", (edit_code,))
        prod = c.fetchone()
        conn.close()

        if prod:
            with st.form("edit_form"):
                e_name = st.text_input("نام کالا", prod[1])
                e_cat = st.text_input("دسته‌بندی", prod[2])
                e_buy = st.number_input("قیمت خرید", value=int(prod[3]), step=1000)
                e_sell = st.number_input("قیمت فروش", value=int(prod[4]), step=1000)
                e_stock = st.number_input("موجودی", value=int(prod[5]), step=1)

                col1, col2 = st.columns(2)
                with col1:
                    update_btn = st.form_submit_button("💾 ذخیره تغییرات")
                with col2:
                    delete_btn = st.form_submit_button("🗑️ حذف کالا")

                if update_btn:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("UPDATE products SET name=?, category=?, purchase_price=?, sale_price=?, stock=? WHERE code=?",
                              (e_name, e_cat, e_buy, e_sell, e_stock, edit_code))
                    conn.commit()
                    conn.close()
                    st.success("اطلاعات کالا با موفقیت به‌روزرسانی شد!")
                    st.rerun()

                if delete_btn:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("DELETE FROM products WHERE code=?", (edit_code,))
                    conn.commit()
                    conn.close()
                    st.warning("کالا از انبار حذف شد!")
                    st.rerun()
        else:
            st.warning("کالایی با این کد برای ویرایش یافت نشد.")

# ==========================================
# بخش 3: افزودن کالای جدید
# ==========================================
elif choice == "➕ افزودن کالای جدید":
    st.header("تعریف کالای جدید در انبار")
    
    with st.form("add_product_form", clear_on_submit=True):
        p_code = st.text_input("کد / بارکد کالا (الزامی) *", help="میتوانید کد روی جعبه را به صورت دستی وارد کنید")
        p_name = st.text_input("نام کالا (الزامی) *")
        p_cat = st.selectbox("دسته‌بندی", ["هدلایت و لامپ", "روکش و کفپوش", "مانیتور و سیستم صوتی", "دزدگیر و ردیاب", "تزئینات و خوشبوکننده", "سایر"])
        
        p_buy = st.number_input("قیمت خرید (تومان)", min_value=0, step=10000)
        p_sell = st.number_input("قیمت فروش (تومان)", min_value=0, step=10000)
        p_stock = st.number_input("موجودی اولیه (تعداد)", min_value=0, step=1)

        submitted = st.form_submit_button("➕ ثبت کالا در انبار")
        
        if submitted:
            if p_code.strip() == "" or p_name.strip() == "":
                st.error("وارد کردن کد و نام کالا الزامی است.")
            else:
                try:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)",
                              (p_code, p_name, p_cat, p_buy, p_sell, p_stock))
                    conn.commit()
                    conn.close()
                    st.success(f"کالای '{p_name}' با موفقیت به انبار اضافه شد!")
                except sqlite3.IntegrityError:
                    st.error("خطا: کالایی با این کد از قبل در سیستم وجود دارد!")

# ==========================================
# بخش 4: گزارش‌ها
# ==========================================
elif choice == "📊 گزارش‌ها":
    st.header("گزارش فروش و مانیتورینگ مالی")
    
    conn = sqlite3.connect(DB_NAME)
    sales_df = pd.read_sql_query("SELECT id as 'کد فاکتور', product_code as 'کد کالا', name as 'نام کالا', quantity as 'تعداد', sale_price as 'قیمت فروش واحد', sale_date as 'تاریخ و زمان' FROM sales ORDER BY id DESC", conn)
    conn.close()

    if not sales_df.empty:
        # محاسبه جمع کل هر ردیف
        sales_df['جمع کل فاکتور (تومان)'] = sales_df['تعداد'] * sales_df['قیمت فروش واحد']
        st.dataframe(sales_df, use_container_width=True, hide_index=True)

        total_sales = sales_df['جمع کل فاکتور (تومان)'].sum()
        total_items = sales_df['تعداد'].sum()
        
        st.markdown("---")
        st.success(f"💰 **جمع کل درآمد فروش:** {total_sales:,.0f} تومان")
        st.info(f"📦 **مجموع کالاهای فروخته شده:** {total_items} عدد")
    else:
        st.info("تا کنون هیچ فروشی در سیستم ثبت نشده است.")
