import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

# ==========================================
# تنظیمات صفحه و راست‌چین کردن (RTL + Mobile Fix)
# ==========================================
st.set_page_config(page_title="مدیریت انبار و فروشگاه", page_icon="🚗", layout="centered")

# CSS اختصاصی برای حل مشکل حروف عمودی، بهبود سایدبار و فونت فارسی
st.markdown("""
<style>
    @import url('https://v1.fontapi.ir/css/Vazir');
    
    * {
        direction: rtl !important;
        text-align: right !important;
        font-family: 'Vazir', 'Tahoma', sans-serif !important;
    }
    
    /* اصلاح سایدبار در موبایل و جلوگیری از عمودی شدن کلمات */
    [data-testid="stSidebar"] {
        min-width: 280px !important;
        max-width: 320px !important;
    }
    [data-testid="stSidebarNav"] span, [data-testid="stWidgetLabel"] {
        white-space: nowrap !important;
        word-break: normal !important;
    }
    
    /* اصلاح فرم‌ها و جدول‌ها */
    .stDataFrame {
        direction: rtl !important;
    }
    
    /* کادر اسکنر دوربین */
    #reader {
        width: 100% !important;
        max-width: 400px;
        margin: 10px auto;
        border-radius: 10px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# توابع مربوط به دیتابیس (SQLite)
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
                  sale_price REAL, sale_date TEXT)''')
    conn.commit()
    conn.close()

def get_low_stock_products():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT name, stock FROM products WHERE stock < 3", conn)
    conn.close()
    return df

init_db()

# ==========================================
# سایدبار و منوی ناوبری
# ==========================================
st.sidebar.title("🚗 مدیریت فروشگاه")
st.sidebar.markdown("---")
menu = ["🛒 ثبت فروش / اسکن", "📦 مدیریت انبار", "➕ افزودن کالای جدید", "📊 گزارش‌ها"]
choice = st.sidebar.radio("منوی اصلی:", menu)

low_stock_df = get_low_stock_products()
if not low_stock_df.empty:
    st.sidebar.markdown("---")
    st.sidebar.error("⚠️ هشدار کمبود موجودی:")
    for _, row in low_stock_df.iterrows():
        st.sidebar.warning(f"کالای '{row['name']}' فقط {row['stock']} عدد")

# ==========================================
# بخش ۱: ثبت فروش و اسکن هوشمند (فقط دوربین پشت)
# ==========================================
if choice == "🛒 ثبت فروش / اسکن":
    st.header("🛒 ثبت فروش و اسکن کالا")
    
    tab1, tab2 = st.tabs(["📷 اسکنر دوربین پشت", "🔢 ورود دستی کد"])
    
    code_input = ""

    with tab1:
        st.info("💡 دوربین پشت گوشی به صورت خودکار فعال می‌شود.")
        
        # اسکنر زنده با اجبار به استفاده از دوربین پشت (facingMode: environment)
        html_code = """
        <div id="reader"></div>
        <script src="https://unpkg.com/html5-qrcode"></script>
        <script>
            function onScanSuccess(decodedText, decodedResult) {
                const inputElement = window.parent.document.querySelector('input[aria-label="کد خوانده شده"]');
                if (inputElement) {
                    inputElement.value = decodedText;
                    inputElement.dispatchEvent(new Event('input', { bubbles: true }));
                }
            }
            let html5QrcodeScanner = new Html5QrcodeScanner(
                "reader", 
                { 
                    fps: 15, 
                    qrbox: {width: 250, height: 150},
                    videoConstraints: { facingMode: { exact: "environment" } }
                }, 
                false
            );
            html5QrcodeScanner.render(onScanSuccess);
        </script>
        """
        st.components.v1.html(html_code, height=330)
        scanned_val = st.text_input("کد خوانده شده", key="scanned_code_input", placeholder="کد اسکن شده اینجا قرار می‌گیرد...")
        if scanned_val:
            code_input = scanned_val

    with tab2:
        manual_val = st.text_input("کد یا بارکد کالا را دستی وارد کنید:", placeholder="مثلاً: 123456789")
        if manual_val:
            code_input = manual_val

    if code_input:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT * FROM products WHERE code=?", (code_input,))
        product = c.fetchone()
        conn.close()

        if product:
            st.markdown("---")
            st.subheader("📌 مشخصات کالا")
            st.info(f"**نام کالا:** {product[1]} | **دسته‌بندی:** {product[2]}")
            
            stock_color = "red" if product[5] < 3 else "green"
            st.markdown(f"**قیمت فروش:** {product[4]:,.0f} تومان | **موجودی:** <span style='color:{stock_color}; font-weight:bold;'>{product[5]}</span> عدد", unsafe_allow_html=True)

            with st.form("sale_form"):
                sale_qty = st.number_input("تعداد فروش", min_value=1, max_value=product[5] if product[5] > 0 else 1, value=1)
                submit_sale = st.form_submit_button("✅ ثبت نهایی فروش")

                if submit_sale:
                    if product[5] >= sale_qty:
                        new_stock = product[5] - sale_qty
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        c.execute("UPDATE products SET stock=? WHERE code=?", (new_stock, code_input))
                        c.execute("INSERT INTO sales (product_code, name, quantity, sale_price, sale_date) VALUES (?, ?, ?, ?, ?)",
                                  (code_input, product[1], sale_qty, product[4], now))
                        conn.commit()
                        conn.close()
                        
                        st.balloons()
                        st.success(f"فروش {sale_qty} عدد '{product[1]}' با موفقیت ثبت شد!")
                        st.rerun() 
                    else:
                        st.error("موجودی کالا کافی نیست!")
        else:
            st.warning("⚠️ کالایی با این کد در انبار یافت نشد.")

# ==========================================
# بخش ۲: مدیریت انبار
# ==========================================
elif choice == "📦 مدیریت انبار":
    st.header("📦 لیست و ویرایش محصولات")
    
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT code as 'کد کالا', name as 'نام کالا', category as 'دسته‌بندی', purchase_price as 'قیمت خرید', sale_price as 'قیمت فروش', stock as 'موجودی' FROM products", conn)
    conn.close()

    search = st.text_input("🔍 جستجو بر اساس نام یا کد کالا:")
    if search:
        df = df[(df['نام کالا'].str.contains(search, na=False)) | (df['کد کالا'].str.contains(search, na=False))]

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("✏️ ویرایش یا حذف کالا")
    edit_code = st.text_input("برای ویرایش یا حذف، **کد کالا** را وارد کنید:")
    
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
                e_buy = st.number_input("قیمت خرید (تومان)", value=int(prod[3]), step=1000)
                e_sell = st.number_input("قیمت فروش (تومان)", value=int(prod[4]), step=1000)
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
                    st.success("تغییرات ذخیره شد!")
                    st.rerun()

                if delete_btn:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("DELETE FROM products WHERE code=?", (edit_code,))
                    conn.commit()
                    conn.close()
                    st.warning("کالا حذف گردید.")
                    st.rerun()

# ==========================================
# بخش ۳: افزودن کالای جدید
# ==========================================
elif choice == "➕ افزودن کالای جدید":
    st.header("➕ تعریف کالای جدید")
    
    with st.form("add_product_form", clear_on_submit=True):
        p_code = st.text_input("کد / بارکد کالا (الزامی) *")
        p_name = st.text_input("نام کالا (الزامی) *")
        p_cat = st.selectbox("دسته‌بندی", ["هدلایت و لامپ", "روکش و کفپوش", "مانیتور و سیستم صوتی", "دزدگیر و ردیاب", "تزئینات و خوشبوکننده", "سایر"])
        
        p_buy = st.number_input("قیمت خرید (تومان)", min_value=0, step=10000)
        p_sell = st.number_input("قیمت فروش (تومان)", min_value=0, step=10000)
        p_stock = st.number_input("موجودی اولیه (تعداد)", min_value=1, step=1)

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
                    st.success(f"کالای '{p_name}' اضافه شد!")
                except sqlite3.IntegrityError:
                    st.error("خطا: این کد کالا قبلاً ثبت شده است.")

# ==========================================
# بخش ۴: گزارش‌ها
# ==========================================
elif choice == "📊 گزارش‌ها":
    st.header("📊 گزارش فروش و سود مالی")
    
    conn = sqlite3.connect(DB_NAME)
    sales_df = pd.read_sql_query("SELECT id as 'کد فاکتور', product_code as 'کد کالا', name as 'نام کالا', quantity as 'تعداد', sale_price as 'قیمت فروش واحد', sale_date as 'تاریخ و زمان' FROM sales ORDER BY id DESC", conn)
    conn.close()

    if not sales_df.empty:
        sales_df['جمع کل (تومان)'] = sales_df['تعداد'] * sales_df['قیمت فروش واحد']
        st.dataframe(sales_df, use_container_width=True, hide_index=True)

        total_sales = sales_df['جمع کل (تومان)'].sum()
        total_items = sales_df['تعداد'].sum()
        
        st.markdown("---")
        st.success(f"💰 **جمع کل درآمد:** {total_sales:,.0f} تومان")
        st.info(f"📦 **تعداد کل اجناس فروخته‌شده:** {total_items} عدد")
    else:
        st.info("هنوز فروشی ثبت نشده است.")
