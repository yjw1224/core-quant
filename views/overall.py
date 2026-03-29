import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd
from fredapi import Fred
from dotenv import load_dotenv
import os

# 세션 상태 초기화 (페이지 리로드 시 유지)
if 'is_crisis_count' not in st.session_state:
    st.session_state.is_crisis_count = 0

start_date = "2000-01-01"
CHART_LINE_COLOR = "#2980B9"
CHART_HORIZONTAL_LINE_COLOR = "#E67E22"

@st.cache_data(ttl=3600)
def get_all_data():
    """데이터만 가져오고 판단만 함 (화면 출력 X)"""
    load_dotenv(override=True)


    vix = yf.download("^VIX", start=start_date)
    
    # 멀티인덱스 방어 코드 (droplevel 1 또는 0은 yfinance 버전에 따라 다름)
    if isinstance(vix.columns, pd.MultiIndex):
        vix.columns = vix.columns.get_level_values(0)
        
    last_price = vix['Close'].iloc[-1]

    fred = Fred(api_key=os.getenv("FRED_API_KEY"))
    high_yield_spread = fred.get_series('BAMLH0A0HYM2', observation_start=start_date) # 데이터 가져오기
    last_hy_spread = high_yield_spread[-1]

    nfci_data = fred.get_series('NFCI', observation_start=start_date)
    last_nfci = nfci_data[-1]

    sloos_data = fred.get_series('DRTSCILM', observation_start=start_date)
    last_sloos = sloos_data[-1]

    # get OECD_CLI_DATA from OECD_CLI_INDEX.csv

    try:
        oecd_cli_data = pd.read_csv('OECD_CLI_INDEX.csv', encoding='utf-8')
    except UnicodeDecodeError:
        oecd_cli_data = pd.read_csv('OECD_CLI_INDEX.csv', encoding='cp949')

    # 2. 'Jan-95' 날짜 형식 강제 변환 (가장 중요!)
    # %b는 월 이름 약어(Jan), %y는 두 자리 연도(95)를 의미합니다.
    oecd_cli_data['TIME_PERIOD'] = pd.to_datetime(oecd_cli_data['TIME_PERIOD'], format='%b-%y')

    # 3. 피벗 테이블 생성 (index 설정을 여기서 한 번에 해결)
    df_pivot = oecd_cli_data.pivot(index='TIME_PERIOD', columns='REF_AREA', values='OBS_VALUE')

    # 4. 날짜 순서대로 정렬 (전월 대비 계산을 위해 필수)
    df_pivot = df_pivot.sort_index()

    # 5. 전월 대비 상승 국가 비율(MoM Diffusion Index) 계산
    # 실제 데이터가 존재하는 국가 수로 나눠주는 것이 더 정확합니다.
    mom_up = (df_pivot.diff(1) > 0).astype(int)
    cli_di_mom = (mom_up.sum(axis=1) / df_pivot.count(axis=1)) * 100

    # 결과 데이터프레임 정리
    diffusion_df = pd.DataFrame({'CLI_DI_MoM': cli_di_mom})

    return vix, last_price, high_yield_spread, last_hy_spread, nfci_data, last_nfci, sloos_data, last_sloos, diffusion_df[1:], diffusion_df['CLI_DI_MoM'].iloc[-1]


def get_all_data_from_session():
    """세션 내에서는 API 응답을 재사용해 불필요한 재호출을 줄입니다."""
    if 'overall_data_cache' not in st.session_state:
        st.session_state.overall_data_cache = get_all_data()
    return st.session_state.overall_data_cache

def render_vix_chart(vix):
    """차트 렌더링만 담당"""
    vix_plot = vix.reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=vix_plot['Date'], y=vix_plot['Close'], mode='lines', name='S&P 500 VIX',
                             line=dict(color=CHART_LINE_COLOR, width=1)))
    fig.add_hline(y=30, line_dash="dot", line_color=CHART_HORIZONTAL_LINE_COLOR, line_width=2)
    fig.update_layout(xaxis=dict(title='날짜', type="date"), yaxis=dict(title='VIX', showgrid=False))
    st.plotly_chart(fig, use_container_width=True)

def render_high_yield_spread_chart(high_yield_spread_data):
    spread_plot = high_yield_spread_data.reset_index()
    spread_plot.columns = ['Date', 'Spread']
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=spread_plot['Date'], y=spread_plot['Spread'], mode='lines', name='High Yield Bond Spread',
                             line=dict(color=CHART_LINE_COLOR, width=1)))
    fig.add_hline(y=5, line_dash="dot", line_color=CHART_HORIZONTAL_LINE_COLOR, line_width=2)
    fig.update_layout(xaxis=dict(title='날짜', type="date"), yaxis=dict(title='Spread (%)', showgrid=False))
    st.plotly_chart(fig, use_container_width=True)

def render_nfci_chart(nfci_data):
    # 데이터 정리 (하이일드 함수와 동일한 로직)
    fci_plot = nfci_data.reset_index()
    fci_plot.columns = ['Date', 'FCI']
    
    fig = go.Figure()
    
    # NFCI 지표 선 생성
    fig.add_trace(go.Scatter(
        x=fci_plot['Date'], 
        y=fci_plot['FCI'], 
        mode='lines', 
        name='National Financial Conditions Index',
        line=dict(color=CHART_LINE_COLOR, width=1)
    ))
    
    # 기준선 설정: NFCI는 0을 기준으로 위(위축/위험), 아래(완화/안정)를 판단합니다
    fig.add_hline(
        y=0, 
        line_dash="dot", 
        line_color=CHART_HORIZONTAL_LINE_COLOR, 
        line_width=2
    )
    
    # 레이아웃 설정
    fig.update_layout(
        xaxis=dict(title='날짜', type="date"), 
        yaxis=dict(title='Index Value (Avg=0)', showgrid=False),
        hovermode="x unified"
    )
    
    st.plotly_chart(fig, use_container_width=True)

def render_sloos_chart(sloos_data):
    sloos_plot = sloos_data.reset_index()
    sloos_plot.columns = ['Date', 'SLOOS']
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sloos_plot['Date'], y=sloos_plot['SLOOS'], mode='lines', name='SLOOS',
                             line=dict(color=CHART_LINE_COLOR, width=1)))
    fig.add_hline(y=25, line_dash="dot", line_color=CHART_HORIZONTAL_LINE_COLOR, line_width=2)
    fig.update_layout(xaxis=dict(title='날짜', type="date"), yaxis=dict(title='SLOOS (%)', showgrid=False))
    st.plotly_chart(fig, use_container_width=True)

def render_cli_diffusion_chart(oecd_cli_data):
    cli_plot = oecd_cli_data.reset_index()
    cli_plot.columns = ['Date', 'CLI_DI_MoM']
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=cli_plot['Date'], y=cli_plot['CLI_DI_MoM'], mode='lines', name='OECD CLI Diffusion Index',
                             line=dict(color=CHART_LINE_COLOR, width=1)))
    fig.add_hline(y=50, line_dash="dot", line_color=CHART_HORIZONTAL_LINE_COLOR, line_width=2)
    fig.update_layout(xaxis=dict(title='날짜', type="date"), yaxis=dict(title='Diffusion Index (%)', showgrid=False))
    st.plotly_chart(fig, use_container_width=True)

FCI_LIST = [
    {"name": "S&P 500 VIX", "description": "VIX 지수는 S&P 500 옵션의 내재 변동성을 측정한 지표입니다. VIX 지수가 30을 넘어서면 시장의 불안정성이 매우 커졌음을 의미합니다.", "key": "vix", "condition_text": "≥ 30"},
    {"name": "High Yield Bond Spread", "description": "고수익 회사채 스프레드입니다. 이 수치가 높아지면 투자자들이 위험 회피 성향이 강해집니다.", "key": "hy_spread", "condition_text": "≥ 5"},
    {"name": "Financial Condition Index (FCI)", "description": "금융조건지수(FCI)는 시카고 연준이 발표하는 지표로, 주식·채권·자산 가격 등 100여 개가 넘는 금융 변수를 종합해 현재 시장에서 '돈이 얼마나 원활하게 돌고 있는지'를 측정합니다. 역사적 평균인 0을 기준으로, 지수가 0보다 커질수록 시장의 자금 조달 여건이 빡빡해지고 대출 문턱이 높아지는 \'위축 상태\'임을 뜻합니다. 통상적으로 지수가 0.0을 상향 돌파하기 시작하면 시장에 경고등이 켜진 것으로 보며, 0.5에서 1.0 이상으로 급격히 치솟으면 과거 금융위기나 팬데믹 때와 같은 실질적인 경제 위기가 진행 중임을 시사합니다.",
      "key": "fci", "condition_text": "≥ 0"},
    {"name": "SLOOS", "description": "SLOOS는 은행들이 대출 문턱을 얼마나 높였는지 보여주는 지표로, 수치가 플러스(+)일수록 대출 조건이 까다로워지는 유동성 위축을 의미합니다. 통상 20~25%를 넘어서면 경기 둔화의 전조 증상으로 판단하며, 40%를 돌파할 경우 역사적으로 예외 없는 경기 침체가 발생했습니다.",
     "key": "sloos", "condition_text": "≥ 25"},
    {"name": "OECD CLI Diffusion Index", "description": "OECD CLI 확산지수(Diffusion Index)는 경기 선행지수의 상승 또는 하락 방향성을 수치화하여 경기 전환점을 포착하는 지표입니다. 지수가 50을 상향 돌파하면 경기 회복의 신호로 보며, 반대로 50을 하회하기 시작하면 본격적인 경기 하강 국면에 진입한 것으로 판단합니다. 특히 지수가 20~30 수준까지 급락할 경우 실물 경제의 침체 가능성이 매우 높은 위험 구간으로 해석됩니다.",
     "key": "oecd_cli", "condition_text": "≤ 50"},
]

FCI_PERCENTAGE_DESCRIPTION = [
    {"percentage": 0.25, "description": "안정", "color": "#00CC96"},
    {"percentage": 0.5, "description": "주의", "color": "#FFA15A"},
    {"percentage": 0.75, "description": "위험", "color": "#EF553B"},
    {"percentage": 1.0, "description": "경기 침체", "color": "#7D0000"},
]

def render_crisis_gauge(current_count, total_count):
    # 구간별 색상 설정
    colors = ['#00CC96', '#7D0000']

    fig = go.Figure()

    BAR_HEIGHT = 0.25

    # 1. 배경 색상 바 (4개 구간)
    fig.add_shape(
        type="rect",
        x0=0, x1=total_count, y0=0.5 - BAR_HEIGHT/2, y1=0.5 + BAR_HEIGHT/2,
        fillcolor='#666666',
        line=dict(width=0),
        layer="below"
    )

    # 2. 현재 위치 표시 (동그라미 포인터)
    fig.add_trace(go.Scatter(
        x=[current_count],
        y=[0.5],
        mode='markers+text',
        marker=dict(size=25, color="#dfdfdf", symbol="circle"),
        name="현재 상태"
    ))

    # 3. 레이아웃 설정 (축 숨기기 및 디자인)
    fig.update_layout(
        # make title left-align
        title=dict(
            text="현재 경제 위기 지표 카운트",
            x=0.5, y=0.9, xanchor='center', font=dict(size=20)
        ),
        xaxis=dict(
            range=[0, total_count],
            showgrid=False, zeroline=False, showticklabels=True,
            tickvals=[0.3, total_count - 0.3],
            ticktext=["← 안정", "침체 →"],
            fixedrange=True
        ),
        yaxis=dict(
            range=[0, 1.5],
            showgrid=False, zeroline=False, showticklabels=False,
            fixedrange=True
        ),
        height=180,
        margin=dict(l=20, r=20, t=80, b=20),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        showlegend=False
    )

    st.plotly_chart(fig, use_container_width=True)

def render_overall_page():
    
    # --- 1. 로직 처리 (화면 그리기 전에 데이터 먼저 계산) ---
    vix_df, last_vix, high_yield_spread_data, last_hy_spread, nfci_data, last_nfci, sloos_data, last_sloos, cli_diffuion_data, last_cli_diffusion = get_all_data_from_session()

    IS_CRISIS = [
        {"condition": last_vix >= 30, "data": last_vix},
        {"condition": last_hy_spread >= 5, "data": last_hy_spread},  # High Yield Bond Spread
        {"condition": last_nfci >= 0, "data": last_nfci},  # Financial Condition Index
        {"condition": last_sloos >= 25, "data": last_sloos},  # SLOOS
        {"condition": last_cli_diffusion <= 50, "data": last_cli_diffusion},  # OECD CLI Diffusion Index
    ]
    
    # 위기 카운트 초기화 후 계산
    current_crisis = 0
    for IS_CRISIS_FLAG in IS_CRISIS:
        if IS_CRISIS_FLAG["condition"]:
            current_crisis += 1
    # 다른 지표들도 이곳에서 계산하여 current_crisis에 더함
    
    st.session_state.is_crisis_count = current_crisis
    
    # --- 2. 상단 메트릭 표시 ---
    total_fci = len(FCI_LIST)
    ratio = st.session_state.is_crisis_count / total_fci
    
    # 상태 설명 매칭
    # status_idx = min(int(ratio * len(FCI_PERCENTAGE_DESCRIPTION)), len(FCI_PERCENTAGE_DESCRIPTION)-1)
    # FCI_NOW = FCI_PERCENTAGE_DESCRIPTION[status_idx]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.write("Financial Crisis Indicator")
        st.header(f"{st.session_state.is_crisis_count} / {total_fci}", help="경제 위기 지표들 중 현재 몇 개가 위기 신호를 보내고 있는지 나타냅니다.")
        render_crisis_gauge(st.session_state.is_crisis_count, total_fci)

    # --- 3. 상세 지표 리스트 표시 ---
    for fci in FCI_LIST:
        i = FCI_LIST.index(fci)
        st.markdown(f"### {fci['name']}", help=fci['description'])

        st.markdown(
        f"""
        <div style="
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            border-bottom: 1px solid #30363d; 
            padding-bottom: 8px;
            display: flex;
            align-items: baseline;
            gap: 10px;
        ">
            <span style="
                font-size: 32px; 
                font-weight: 600; 
                color: #f0f6fc;
            ">
                {IS_CRISIS[i]['data']:.2f}
            </span>
            <span style="
                font-size: 16px; 
                font-weight: 400; 
                color: #8b949e;
            ">
                {fci['condition_text']}
            </span>
            <span style="
                font-size: 16px; 
                font-weight: 400; 
                color: {"#ef553b" if IS_CRISIS[i]['condition'] else "#00cc96"};
                ">
                <b>{"위험" if IS_CRISIS[i]['condition'] else "안전"}</b>
            </span>
        </div>
        """,
        unsafe_allow_html=True
        )
        if fci['key'] == "vix":
            render_vix_chart(vix_df)
        elif fci['key'] == "hy_spread":
            render_high_yield_spread_chart(high_yield_spread_data)
        elif fci['key'] == "fci":
            render_nfci_chart(nfci_data)
        elif fci['key'] == "sloos":
            render_sloos_chart(sloos_data)
        elif fci['key'] == "oecd_cli":
            render_cli_diffusion_chart(cli_diffuion_data)
        else:
            st.warning(f"{fci['name']} 데이터는 현재 준비 중입니다.")