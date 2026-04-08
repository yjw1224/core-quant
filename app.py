import streamlit as st

from views.korea_stock import render_korea_stock_page
from views.us_stock import render_us_stock_page
from views.overall import render_overall_page
from views.crypto import render_crypto_page
from views.macro import render_macro_page

MENU_OVERALL = "전체"
MENU_KOREA_STOCK = "국내주식"
MENU_CRYPTO = "크립토"
MENU_MACRO = "매크로"
MENU_US_STOCK = "미국주식"

# 페이지 설정 (브라우저 탭에 표시될 이름)
st.set_page_config(page_title="CORE : The Quant Universe", layout="wide")

# 사이드바 로고 및 메뉴
with st.sidebar:
    st.title("CORE")
    st.caption("The Central Node of Quant Data")
    
    menu = st.radio(
        "분석할 자산을 선택하세요",
        (MENU_OVERALL, MENU_KOREA_STOCK, MENU_US_STOCK, MENU_CRYPTO, MENU_MACRO)
    )

st.title(f"🚀 {menu}")

if menu == MENU_OVERALL:
    render_overall_page()

elif menu == MENU_KOREA_STOCK:
    render_korea_stock_page()
    
elif menu == MENU_CRYPTO:
    render_crypto_page()
    
elif menu == MENU_MACRO:
    render_macro_page()

elif menu == MENU_US_STOCK:
    render_us_stock_page()

st.info("하루 2시간의 몰입, 데이터로 시장의 핵심(CORE)을 읽습니다.")
