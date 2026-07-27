import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime

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
# منوی کناری (سایدبار)
# ==========================================
st.sidebar.title("🚗 سیستم مدیریت فروشگاه")
st.sidebar.markdown("---")
menu = ["🛒 ثبت فروش / بررسی کالا", "📦 مدیریت انبار", "➕ افزودن کالای جدید", "📊 گزارش‌ها"]
choice = st.sidebar.radio("منوی اصلی:", menu)

low_stock_df = get_low_stock_products()
if not low_stock_df.empty:
    st.sidebar.markdown("---")
    st.sidebar.error("⚠️ هشدار کمبود موجودی:")
    for _, row in low_stock_df.iterrows():
        st.sidebar.warning(f"کالای '{row['name']}' فقط {row['stock']} عدد")

# ==========================================
# بخش 1: ثبت فروش و بررسی کالا
# ==========================================
if choice == "🛒 ثبت فروش / بررسی کالا":
    st.header("🛒 ثبت فروش و بررسی کالا")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.info("🔹 راهنما: می‌توانید از بارکدخوان فیزیکی یا اسکنر خودکار دوربین استفاده کنید.")
        scan_method = st.radio("روش ورود کد:", ("کیبورد / بارکدخوان فیزیکی", "دوربین (اسکنر خودکار حرفه‌ای)"))
        
        code_input = ""
        
        if scan_method == "کیبورد / بارکدخوان فیزیکی":
            code_input = st.text_input("کد کالا را اینجا اسکن یا وارد کنید:", key="barcode_input")
            
        elif scan_method == "دوربین (اسکنر خودکار حرفه‌ای)":
            if HAS_SCANNER_PKG:
                st.markdown("📷 **دوربین فعال است. بارکد را مقابل دوربین بگیرید (به محض تشخیص، خودکار تایید می‌شود):**")
                # اسکنر خودکار فوق‌العاده قوی
                scanned_code = qrcode_scanner(key='pro_scanner')
                if scanned_code:
                    code_input = scanned_code
                    st.success(f"✅ اسکن موفق: {code_input}")
            else:
                st.error("کتابخانه اسکنر نصب نیست. لطفاً requirements.txt را بررسی کنید.")

    with col2:
        if code_input:
            conn = sqlite3.connect(DB_NAME)
            c = conn.cursor()
            c.execute("SELECT * FROM products WHERE code=?", (code_input,))
            product = c.fetchone()
            conn.close()

            if product:
                st.subheader(f"📦 مشخصات: {product[1]}")
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
                            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            
                            conn = sqlite3.connect(DB_NAME)
                            c = conn.cursor()
                            c.execute("UPDATE products SET stock=? WHERE code=?", (new_stock, code_input))
                            c.execute("INSERT INTO sales (product_code, name, quantity, sale_price, sale_date) VALUES (?, ?, ?, ?, ?)",
                                      (code_input, product[1], sale_qty, product[4], now))
                            conn.commit()
                            conn.close()
                            
                            st.success(f"فروش {sale_qty} عدد با موفقیت ثبت شد!")
                            st.rerun()
                        else:
                            st.error("موجودی کالا برای این تعداد فروش کافی نیست!")
            else:
                st.warning("⚠️ کالایی با این کد در سیستم ثبت نشده است.")

# ==========================================
# بخش 2: مدیریت انبار
# ==========================================
elif choice == "📦 مدیریت انبار":
    st.header("📦 لیست و مدیریت محصولات")
    
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query("SELECT code as 'کد کالا', name as 'نام کالا', category as 'دسته‌بندی', purchase_price as 'قیمت خرید', sale_price as 'قیمت فروش', stock as 'موجودی' FROM products", conn)
    conn.close()

    search = st.text_input("🔍 جستجوی سریع (نام یا کد):")
    if search:
        df = df[(df['نام کالا'].str.contains(search, na=False)) | (df['کد کالا'].str.contains(search, na=False))]

    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("ویرایش یا حذف کالا")
    col1, col2 = st.columns([1, 2])
    with col1:
        edit_code = st.text_input("کد کالای مورد نظر را وارد کنید:")
    
    if edit_code:
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT * FROM products WHERE code=?", (edit_code,))
        prod = c.fetchone()
        conn.close()

        if prod:
            with col2:
                with st.form("edit_form"):
                    e_name = st.text_input("نام کالا", prod[1])
                    e_cat = st.text_input("دسته‌بندی", prod[2])
                    e_buy = st.number_input("قیمت خرید", value=int(prod[3]), step=1000)
                    e_sell = st.number_input("قیمت فروش", value=int(prod[4]), step=1000)
                    e_stock = st.number_input("موجودی", value=int(prod[5]), step=1)

                    ecol1, ecol2 = st.columns(2)
                    with ecol1:
                        update_btn = st.form_submit_button("💾 ذخیره تغییرات")
                    with ecol2:
                        delete_btn = st.form_submit_button("🗑️ حذف کالا")

                    if update_btn:
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        c.execute("UPDATE products SET name=?, category=?, purchase_price=?, sale_price=?, stock=? WHERE code=?",
                                  (e_name, e_cat, e_buy, e_sell, e_stock, edit_code))
                        conn.commit()
                        conn.close()
                        st.success("به‌روزرسانی انجام شد.")
                        st.rerun()

                    if delete_btn:
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        c.execute("DELETE FROM products WHERE code=?", (edit_code,))
                        conn.commit()
                        conn.close()
                        st.warning("کالا حذف شد.")
                        st.rerun()
        else:
            with col2:
                st.warning("کالایی یافت نشد.")

# ==========================================
# بخش 3: افزودن کالای جدید
# ==========================================
elif choice == "➕ افزودن کالای جدید":
    st.header("➕ تعریف کالای جدید")
    
    with st.form("add_product_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            p_code = st.text_input("کد / بارکد کالا *")
            p_name = st.text_input("نام کالا *")
            p_cat = st.selectbox("دسته‌بندی", ["هدلایت و لامپ", "روکش و کفپوش", "مانیتور و سیستم صوتی", "دزدگیر و ردیاب", "تزئینات و خوشبوکننده", "سایر"])
        
        with col2:
            p_buy = st.number_input("قیمت خرید (تومان)", min_value=0, step=10000)
            p_sell = st.number_input("قیمت فروش (تومان)", min_value=0, step=10000)
            p_stock = st.number_input("موجودی اولیه (تعداد)", min_value=0, step=1)

        submitted = st.form_submit_button("ثبت در انبار")
        
        if submitted:
            if p_code.strip() == "" or p_name.strip() == "":
                st.error("کد و نام کالا الزامی است.")
            else:
                try:
                    conn = sqlite3.connect(DB_NAME)
                    c = conn.cursor()
                    c.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?)",
                              (p_code, p_name, p_cat, p_buy, p_sell, p_stock))
                    conn.commit()
                    conn.close()
                    st.success(f"کالای '{p_name}' ثبت شد.")
                except sqlite3.IntegrityError:
                    st.error("این کد کالا قبلاً ثبت شده است!")

# ==========================================
# بخش 4: گزارش‌ها
# ==========================================
elif choice == "📊 گزارش‌ها":
    st.header("📊 گزارش فروش مالی")
    
    conn = sqlite3.connect(DB_NAME)
    sales_df = pd.read_sql_query("SELECT id as 'کد فاکتور', product_code as 'کد کالا', name as 'نام کالا', quantity as 'تعداد', sale_price as 'قیمت فروش', sale_date as 'تاریخ و زمان' FROM sales ORDER BY id DESC", conn)
    conn.close()

    if not sales_df.empty:
        sales_df['جمع کل (تومان)'] = sales_df['تعداد'] * sales_df['قیمت فروش']
        
        col1, col2 = st.columns(2)
        total_sales = sales_df['جمع کل (تومان)'].sum()
        total_items = sales_df['تعداد'].sum()
        
        col1.success(f"💰 جمع درآمد: {total_sales:,.0f} تومان")
        col2.info(f"📦 تعداد کل اقلام فروخته شده: {total_items} عدد")
        
        st.dataframe(sales_df, use_container_width=True, hide_index=True)
    else:
        st.info("هیچ فاکتوری ثبت نشده است.")
