def render_us_stock_page():
    import streamlit as st
    
    st.subheader("미국주식 분석")
    st.write("미국주식 관련 데이터와 분석 결과를 여기에 표시합니다.")
    
    #yfinance를 사용하여 TSLA의 순매수 거래대금 (거래량 * 종가 * (가격이 올랐으면 1, 내렸으면 -1))를 일별로 계산, 그래프로 시각화.

    import yfinance as yf
    import pandas as pd
    import numpy as np
    import plotly.graph_objects as go

    ticker = st.text_input("분석할 미국주식 티커를 입력하세요 (예: TSLA)", value="TSLA").upper()
    SEQUENCE_LENGTH = 5
    CORRELATION_THRESHOLD = 0.4

    # TSLA 데이터 다운로드
    tsla = yf.download(ticker, start="2024-01-01")

    # [중요] Multi-Index 컬럼인 경우 단일 인덱스로 평탄화 (최신 yfinance 대응)
    if isinstance(tsla.columns, pd.MultiIndex):
        tsla.columns = tsla.columns.get_level_values(0)

    tsla['Direction'] = np.where(tsla['Close'] > tsla['Close'].shift(1), 1, -1)

    # 순매수 거래대금 추정 (거래대금 * 방향)
    tsla['NetMoneyFlow'] = tsla['Volume'] * tsla['Close'] * tsla['Direction']

    # 누적 순매수 거래대금 (이게 핵심!)
    tsla['CumNetMoneyFlow'] = tsla['NetMoneyFlow'].cumsum()

    # 누적 순매수 거래대금과 종가 사이의 상관관계 계산
    correlation = tsla['Close'].rolling(20).corr(tsla['CumNetMoneyFlow'])

    divergence_mask = correlation <= CORRELATION_THRESHOLD

    def calculate_vpci(data, short_period=5, long_period=20):
        """
        VPCI 계산 함수
        VPC (Volume Price Confirmation) = VWMA(Long) - SMA(Long)
        VPR (Volume Price Ratio) = VWMA(Short) / SMA(Short)
        VM (Volume Multiplier) = SMA(Volume, Short) / SMA(Volume, Long)
        VPCI = VPC * VPR * VM
        """
        # 1. 이동평균 (SMA) 및 거래량 가중 이동평균 (VWMA) 계산
        # VWMA = Sum(Price * Volume) / Sum(Volume)
        pv = data['Close'] * data['Volume']
        
        sma_short = data['Close'].rolling(window=short_period).mean()
        sma_long = data['Close'].rolling(window=long_period).mean()
        
        vwma_short = pv.rolling(window=short_period).sum() / data['Volume'].rolling(window=short_period).sum()
        vwma_long = pv.rolling(window=long_period).sum() / data['Volume'].rolling(window=long_period).sum()
        
        # 2. VPC, VPR, VM 계산
        vpc = vwma_long - sma_long
        vpr = vwma_short / sma_short
        vm = data['Volume'].rolling(window=short_period).mean() / data['Volume'].rolling(window=long_period).mean()
        
        # 3. 최종 VPCI
        vpci = vpc * vpr * vm
        return vpci
    
    # 1. VPCI 기본값 계산 (기존 함수 활용)
    tsla['VPCI_Raw'] = calculate_vpci(tsla)

    # 2. VPCI의 20일 이동평균과 표준편차 계산
    window = 20
    tsla['VPCI_Mean'] = tsla['VPCI_Raw'].rolling(window=window).mean()
    tsla['VPCI_Std'] = tsla['VPCI_Raw'].rolling(window=window).std()

    # 3. Z-Score 계산: (현재값 - 평균) / 표준편차
    # 0으로 나누는 에러를 방지하기 위해 아주 작은 값(1e-9)을 더해줍니다.
    tsla['VPCI_ZScore'] = (tsla['VPCI_Raw'] - tsla['VPCI_Mean']) / (tsla['VPCI_Std'] + 1e-9)
    
    # 그래프 시각화
    fig_tsla = go.Figure()

    # 배경에 상관관계 0.4 이하 구간 표시 (Highlight)
    # SEQUENCE_LENGTH 일 이상 연속된 구간을 찾아 VSpan(세로 영역)으로 추가
    for i in range(1, len(divergence_mask)):
        if divergence_mask.iloc[i] and not divergence_mask.iloc[i-1]:  # 구간 시작
            start_date = divergence_mask.index[i]
        elif not divergence_mask.iloc[i] and divergence_mask.iloc[i-1]:  # 구간 끝
            end_date = divergence_mask.index[i]
            if (end_date - start_date).days >= SEQUENCE_LENGTH:  # SEQUENCE_LENGTH 일 이상인 경우에만 표시
                fig_tsla.add_vrect(
                    x0=start_date, 
                    x1=end_date,
                    fillcolor="rgba(255, 0, 0, 0.2)", # 연한 빨간색
                    layer="below", 
                    line_width=0,
                    name="Divergence"
                )

    # 배경에 vpci z-score가 -2 이하로 진입하기 시작하는 부분을 종가 차트에 점으로 표시
    for i in range(1, len(tsla)):
        if tsla['VPCI_ZScore'].iloc[i] <= -2.0 and tsla['VPCI_ZScore'].iloc[i-1] > -2.0:
            fig_tsla.add_trace(go.Scatter(
                x=[tsla.index[i]], 
                y=[tsla['Close'].iloc[i]], 
                mode='markers',
                marker=dict(color="#e45b00", size=10, symbol='circle-dot'),
                yaxis='y2',
                name='VPCI ZScore -2 하향 돌파',
                showlegend=False
            ))

        if tsla['VPCI_ZScore'].iloc[i] >= -2.0 and tsla['VPCI_ZScore'].iloc[i-1] < -2.0:
            fig_tsla.add_trace(go.Scatter(
                x=[tsla.index[i]], 
                y=[tsla['Close'].iloc[i]], 
                mode='markers',
                marker=dict(color="#00d87e", size=10, symbol='circle-dot'),
                yaxis='y2',
                name='VPCI ZScore -2 상향 돌파',
                showlegend=False
            ))

    fig_tsla.add_trace(go.Scatter(x=tsla.index, y=tsla['CumNetMoneyFlow'].rolling(window=5).mean(), mode='lines', name=f'{ticker} 누적 순매수 거래대금',
                                  line=dict(color="#e7eb00", width=2)))
    fig_tsla.add_trace(go.Scatter(x=tsla.index, y=tsla['Close'], mode='lines', name=f'{ticker} 종가', yaxis='y2',
                                  line=dict(color="#b2cdff", width=1)))
    fig_tsla.update_layout(
        title=f'{ticker} 누적 순매수 거래대금 추이',
        xaxis_title='날짜',
        yaxis_title='누적 순매수 거래대금',
        yaxis=dict(title='누적 순매수 거래대금', showgrid=False),
        yaxis2=dict(title='종가', overlaying='y', side='right', showgrid=False)
    )
    fig_tsla.update_layout(title=f'{ticker} 누적 순매수 거래대금 추이', xaxis_title='날짜', yaxis_title='누적 순매수 거래대금')
    st.plotly_chart(fig_tsla, use_container_width=True)

    fig_vpci = go.Figure()
    fig_vpci.add_trace(go.Scatter(x=tsla.index, y=tsla['VPCI_ZScore'], mode='lines', name=f'{ticker} VPCI (Z-Score)',
                                  line=dict(color="#f59d9a", width=2)))
    fig_vpci.update_layout(title=f'{ticker} VPCI Z-SCORE', xaxis_title='날짜', yaxis_title='VPCI')
    fig_vpci.add_hline(y=-2.0, line_dash="dash", line_color="orange", row=2, col=1)
    fig_vpci.add_hline(y=2.0, line_dash="dash", line_color="green", row=2, col=1,)
    st.plotly_chart(fig_vpci, use_container_width=True)