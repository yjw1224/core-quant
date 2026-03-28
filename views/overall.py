import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
import pandas as pd

# 세션 상태 초기화 (페이지 리로드 시 유지)
if 'is_crisis_count' not in st.session_state:
    st.session_state.is_crisis_count = 0

start_date = "2000-01-01"

def get_vix_data():
    """데이터만 가져오고 판단만 함 (화면 출력 X)"""
    vix = yf.download("^VIX", start=start_date)
    
    # 멀티인덱스 방어 코드 (droplevel 1 또는 0은 yfinance 버전에 따라 다름)
    if isinstance(vix.columns, pd.MultiIndex):
        vix.columns = vix.columns.get_level_values(0)
        
    last_price = vix['Close'].iloc[-1]
    return vix, last_price

def render_vix_chart(vix):
    """차트 렌더링만 담당"""
    vix_plot = vix.reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=vix_plot['Date'], y=vix_plot['Close'], mode='lines', name='S&P 500 VIX',
                             line=dict(color="#0281D6", width=1)))
    fig.add_hline(y=30, line_dash="dot", line_color="#FF4646", line_width=2)
    fig.update_layout(xaxis=dict(title='날짜', type="date"), yaxis=dict(title='VIX', showgrid=False))
    st.plotly_chart(fig, use_container_width=True)

FCI_LIST = [
    {"name": "S&P 500 VIX", "description": "VIX 지수가 30을 넘어서면 시장의 불안정성이 큽니다.", "key": "vix", "condition_text": "≥ 30"},
    {"name": "High Yield Bond Spread", "description": "스프레드가 넓어지면 위험 회피 성향이 강해집니다.", "key": "hy_spread", "condition_text": "≥ 3.5%"},
    {"name": "Financial Condition Index (FCI)", "description": "FCI가 양수일 경우 시장 유동성이 낮아짐을 의미합니다.", "key": "fci", "condition_text": "≥ 0"},
    {"name": "SLOOS", "description": "대출 조건을 강화했다는 응답이 25%를 넘으면 위험합니다.", "key": "sloos", "condition_text": "≥ 25%"},
]

FCI_PERCENTAGE_DESCRIPTION = [
    {"percentage": 0.25, "description": "안정", "color": "#00CC96"},
    {"percentage": 0.5, "description": "주의", "color": "#FFA15A"},
    {"percentage": 0.75, "description": "위험", "color": "#EF553B"},
    {"percentage": 1.0, "description": "경기 침체", "color": "#7D0000"},
]

def render_crisis_gauge(current_count, total_count):
    # 구간별 색상 설정
    colors = ['#00CC96', '#FFA15A', '#EF553B', '#7D0000'] # 안전, 주의, 위험, 침체
    status_labels = ["안정", "주의", "위험", "경기 침체"]
    
    # 현재 상태 텍스트 추출
    idx = min(int(current_count), total_count - 1)
    status_text = status_labels[idx]

    fig = go.Figure()

    BAR_HEIGHT = 0.3

    # 1. 배경 색상 바 (4개 구간)
    for i in range(total_count):
        fig.add_shape(
            type="rect",
            x0=i, x1=i+1, y0=0.5 - BAR_HEIGHT/2, y1=0.5 + BAR_HEIGHT/2,
            fillcolor=colors[i],
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
            text=f"현재 시장 상태: <b>{status_text}</b>",
            x=0.5, y=0.9, xanchor='center', font=dict(size=20)
        ),
        xaxis=dict(
            range=[0, total_count],
            showgrid=False, zeroline=False, showticklabels=True,
            tickvals=[0.5, 1.5, 2.5, 3.5],
            ticktext=["안정", "주의", "위험", "침체"],
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
    vix_df, last_vix = get_vix_data()

    IS_CRISIS = [
        {"condition": last_vix > 30, "data": last_vix},
        {"condition": False, "data": 0},  # High Yield Bond Spread (준비 중)
        {"condition": False, "data": 0},  # Financial Condition Index (준비 중)
        {"condition": False, "data": 0},  # SLOOS (준비 중)
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
        else:
            st.warning(f"{fci['name']} 데이터는 현재 준비 중입니다.")