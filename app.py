import streamlit as st
import pandas as pd
import json
import os
import jdatetime
from streamlit_js_eval import streamlit_js_eval

# تنظیمات صفحه
st.set_page_config(page_title="مدیریت فروشگاه", page_icon="🚗", layout="centered")

# کد CSS برای اصلاح فونت، حذف بهم‌ریختگی حروف عمودی و بهینه‌سازی موبایل
st.markdown("""
    <style>
    @import url('https://v1.fontapi.ir/css/Vazir');
    * {
        font-family: 'Vazir', sans-serif !important;
        direction: rtl;
    }
    /* جلوگیری از شکستن کلمات در سایبار و ظاهر عمودی */
    [data-testid="stSidebar"] {
        min-width: 250px !important;
        max-width: 300px !important;
    }
    [data-testid="stSidebarNav"] span {
        white-space: nowrap !important;
    }
    .stApp {
        text-align: right;
    }
    /* استایل بخش اسکنر */
    #reader {
        width: 100% !important;
        max-width: 400px;
        margin: auto;
    }
    </style>
""", unsafe_allow_html=True)

# فایل ذخیره داده‌ها
DATA_FILE = "products.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

products = load_data()

st.title("🚗 سیستم مدیریت فروشگاه")

# منوی اصلی
menu = st.sidebar.radio("منوی اصلی", ["🛒 ثبت فروش / اسکن", "📦 مدیریت انبار", "➕ افزودن کالا"])

if menu == "🛒 ثبت فروش / اسکن":
    st.subheader("ثبت فروش و بررسی کالا")
    
    tab1, tab2 = st.tabs(["🔢 ورود دستی کد", "📷 اسکنر دوربین (سریع)"])
    
    scanned_code = ""
    
    with tab1:
        manual_code = st.text_input("کد یا بارکد کالا را وارد کنید:")
        if manual_code:
            scanned_code = manual_code
            
    with tab2:
        st.info("دوربین را روی بارکد بگیرید (حتی بارکد روی شیشه و انحنا)")
        # اسکنر قدرتمند هوشمند مبتنی بر HTML5 که روی شیشه و بارکدهای براق عالی کار می‌کند
        html_code = """
        <script src="https://unpkg.com/html5-qrcode"></script>
        <div id="reader"></div>
        <script>
            function onScanSuccess(decodedText, decodedResult) {
                window.parent.postMessage({type: 'streamlit:setComponentValue', value: decodedText}, '*');
            }
            let html5QrcodeScanner = new Html5QrcodeScanner(
                "reader", { fps: 15, qrbox: {width: 250, height: 150} }, false);
            html5QrcodeScanner.render(onScanSuccess);
        </script>
        """
        st.components.v1.html(html_code, height=320)
    
    if scanned_code:
        product = next((p for p in products if p['code'] == scanned_code), None)
        if product:
            st.success(f"کالا پیدا شد: **{product['name']}**")
            st.write(f"💵 **قیمت:** {product['price']:,} تومان")
            st.write(f"📊 **موجودی:** {product['stock']} عدد")
            
            if product['stock'] > 0:
                if st.button("✅ ثبت نهایی فروش (کاهش موجودی)"):
                    product['stock'] -= 1
                    save_data(products)
                    st.balloons()
                    st.success("فروش با موفقیت ثبت شد و از انبار کسر گردید!")
            else:
                st.error("❌ موجودی این کالا در انبار تمام شده است!")
        else:
            st.warning("⚠️ کالایی با این بارکد یافت نشد.")

elif menu == "📦 مدیریت انبار":
    st.subheader("موجودی کل انبار")
    if products:
        df = pd.DataFrame(products)
        df.columns = ["کد کالا", "نام کالا", "قیمت (تومان)", "موجودی"]
        st.dataframe(df, use_container_style=True)
    else:
        st.info("هیچ کالایی ثبت نشده است.")

elif menu == "➕ افزودن کالا":
    st.subheader("افزودن کالای جدید به انبار")
    name = st.text_input("نام کالا (مثلاً: روکش صندلی پژو)")
    code = st.text_input("کد یا بارکد کالا (می‌توانید اسکن کنید یا دستی بزنید)")
    price = st.number_input("قیمت فروش (تومان)", min_value=0, step=1000)
    stock = st.number_input("تعداد موجودی اولیه", min_value=1, step=1)
    
    if st.button("➕ ثبت در انبار"):
        if name and code:
            products.append({"code": code, "name": name, "price": price, "stock": stock})
            save_data(products)
            st.success(f"کالای **{name}** با موفقیت اضافه شد!")
        else:

            st.error("لطفاً تمام فیلدها را پر کنید.")
