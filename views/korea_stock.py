import streamlit as st

from services.krx_data import find_stocks, load_stock_universe, login_krx
from pykrx import stock

@st.cache_data(ttl=7200, show_spinner=False)
def fetch_pykrx_data(start_date: str, end_date: str, ticker: str):
    """
    pykrx API 호출을 캐싱하여 동일 조건 재조회 시 API 서버에 과부하를 주지 않습니다.
    데이터는 2시간(7200초) 동안 캐싱됩니다.
    """
    # 데이터 조회 전 항상 로그인 상태 확인 및 갱신 (캐싱된 함수 내부에서 필요시 호출)
    login_success = login_krx()
    
    df_ohlcv = stock.get_market_ohlcv_by_date(start_date, end_date, ticker)
    df_investor_val = stock.get_market_trading_value_by_date(start_date, end_date, ticker)
    df_investor_vol = stock.get_market_trading_volume_by_date(start_date, end_date, ticker)
    
    return login_success, df_ohlcv, df_investor_val, df_investor_vol

def render_korea_stock_page():
    st.subheader("외국인/기관 수급 및 평단가 추적")

    if "selected_stock" not in st.session_state:
        st.session_state.selected_stock = None

    universe, load_error, login_status = load_stock_universe()

    if login_status:
        st.caption(login_status)

    if load_error:
        st.error(load_error)
        return

    if not universe:
        st.warning("조회 가능한 종목 데이터가 없습니다.")
        return

    st.caption(f"총 {len(universe):,}개 종목")

    if st.session_state.selected_stock is None:
        with st.form("search_form"):
            keyword = st.text_input(
                "종목명 또는 종목코드 검색",
                placeholder="예: 삼성전자 또는 005930",
            )
            search_submitted = st.form_submit_button("검색")
            
        if search_submitted or keyword:
            matched = find_stocks(universe, keyword)

            st.markdown("### 검색 결과")
            result_box = st.container(border=True)

            with result_box:
                if not matched:
                    st.warning("검색 결과가 없습니다.")
                else:
                    for item in matched:
                        col1, col2, col3 = st.columns([3, 2, 1])
                        col1.write(item["name"])
                        col2.write(item["code"])
                        if col3.button(
                            "분석 보기",
                            key=f"open-{item['code']}",
                            use_container_width=True,
                        ):
                            st.session_state.selected_stock = item
                            st.rerun()
    else:
        selected = st.session_state.selected_stock
        left, right = st.columns([4, 1])
        left.markdown(f"### {selected['name']} ({selected['code']}) 분석")
        if right.button("검색으로", use_container_width=True):
            st.session_state.selected_stock = None
            st.rerun()

        from datetime import datetime, timedelta
        
        today = datetime.today()
        
        # 조회 버튼을 눌렀을 때만 데이터를 가져오도록 세션 상태 활용
        with st.form("date_period_form"):
            period = st.radio(
                "조회 기간 선택", 
                ["1개월", "6개월", "1년"], 
                horizontal=True, 
                index=1 # 기본값 6개월
            )
            fetch_submitted = st.form_submit_button("데이터 조회하기", type="primary")
            st.caption("api 과다 호출을 막기 위한 버튼입니다.")

        if fetch_submitted:
            st.session_state.data_fetched = True
            st.session_state.selected_period = period
            
        if st.session_state.get("data_fetched", False):
            active_period = st.session_state.get("selected_period", period)
            
            # 선택된 기간에 따른 시작일 계산
            if active_period == "1개월":
                days = 30
            elif active_period == "6개월":
                days = 180
            else:
                days = 365
                
            target_date = today - timedelta(days=days)
            
            end_date = today.strftime("%Y%m%d")
            start_date = target_date.strftime("%Y%m%d")
            ticker = selected['code']
            
            with st.spinner("주가 및 수급 데이터를 불러오는 중입니다..."):
                try:
                    # 1. 캐시된 함수를 통해 데이터 일괄 조회 (내부에서 로그인 처리)
                    login_success, df_ohlcv, df_investor_val, df_investor_vol = fetch_pykrx_data(start_date, end_date, ticker)
                    
                    if not login_success:
                        st.warning("KRX 로그인에 실패했습니다. 일부 데이터 조회가 제한될 수 있습니다.")

                    # --- [기관합계 로직] ---
                    # 순매수량이 0보다 큰(매집한) 날만 필터링
                    inst_buy_days_vol = df_investor_vol[df_investor_vol['기관합계'] > 0]['기관합계']
                    inst_buy_days_val = df_investor_val[df_investor_val['기관합계'] > 0]['기관합계']
                    
                    if not inst_buy_days_vol.empty:
                        inst_net_vol = inst_buy_days_vol.sum()
                        inst_net_val = inst_buy_days_val.sum()
                        inst_avg_price = inst_net_val / inst_net_vol
                    else:
                        inst_avg_price = None
                        inst_net_vol = 0 # 0주 매집

                    # --- [외국인 로직] ---
                    # 순매수량이 0보다 큰(매집한) 날만 필터링
                    foreign_buy_days_vol = df_investor_vol[df_investor_vol['외국인합계'] > 0]['외국인합계']
                    foreign_buy_days_val = df_investor_val[df_investor_val['외국인합계'] > 0]['외국인합계']
                    
                    if not foreign_buy_days_vol.empty:
                        foreign_net_vol = foreign_buy_days_vol.sum()
                        foreign_net_val = foreign_buy_days_val.sum()
                        foreign_avg_price = foreign_net_val / foreign_net_vol
                    else:
                        foreign_avg_price = None
                        foreign_net_vol = 0 # 0주 매집
                        
                    # --- [개인 로직] ---
                    retail_buy_days_vol = df_investor_vol[df_investor_vol['개인'] > 0]['개인']
                    retail_buy_days_val = df_investor_val[df_investor_val['개인'] > 0]['개인']
                    
                    if not retail_buy_days_vol.empty:
                        retail_net_vol = retail_buy_days_vol.sum()
                        retail_net_val = retail_buy_days_val.sum()
                        retail_avg_price = retail_net_val / retail_net_vol
                    else:
                        retail_avg_price = None
                        retail_net_vol = 0

                    # 전체 기간의 순합계 계산
                    total_inst_net_vol = df_investor_vol['기관합계'].sum()
                    total_foreign_net_vol = df_investor_vol['외국인합계'].sum()
                    total_retail_net_vol = df_investor_vol['개인'].sum()

                    # 수익률(수급 평단가 대비 현재 주가의 퍼센티지) 계산을 먼저 수행합니다.
                    if not df_ohlcv.empty:
                        current_price = df_ohlcv['종가'].iloc[-1]
                        inst_percentage = (current_price / inst_avg_price * 100 - 100) if inst_avg_price else 0
                        foreign_percentage = (current_price / foreign_avg_price * 100 - 100) if foreign_avg_price else 0
                        retail_percentage = (current_price / retail_avg_price * 100 - 100) if retail_avg_price else 0
                    else:
                        inst_percentage = foreign_percentage = retail_percentage = 0

                    # 1.5 투자자별 매집 상태 요약(Metric)을 차트 위로 이동
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        if retail_avg_price:
                            if total_retail_net_vol > 0:
                                st.metric(
                                    label="🧍 개인 매집 평단", 
                                    value=f"{int(retail_avg_price):,}원",
                                    delta=f"매집 중 ({'+' if retail_percentage >= 0 else ''}{retail_percentage:.2f}%)"
                                )
                                st.caption(f"순매수량: {retail_net_vol:,}주")
                            else:
                                st.metric(
                                    label="🧍 개인 수급 상태", 
                                    value="순매도(이탈) 중",
                                    delta="이탈 우위",
                                    delta_color="inverse"
                                )
                                st.write(f"최근 {period}간 팔고 나가는 중입니다.")
                        else:
                            st.metric(
                                label="🧍 개인 수급 상태", 
                                value="계산 불가",
                                delta="이탈 우위",
                                delta_color="inverse"
                            )
                            st.caption(f"최근 {period}간 전체적으로 팔고 나가는 중입니다.")

                    with col2:
                        if inst_avg_price:
                            if total_inst_net_vol > 0:
                                st.metric(
                                    label="🏢 기관 매집 평단", 
                                    value=f"{int(inst_avg_price):,}원",
                                    delta=f"매집 중 ({'+' if inst_percentage >= 0 else ''}{inst_percentage:.2f}%)"
                                )
                                st.caption(f"순매수량: {inst_net_vol:,}주")
                            else:
                                st.metric(
                                    label="🏢 기관 수급 상태", 
                                    value="순매도(이탈) 중",
                                    delta="이탈 우위",
                                    delta_color="inverse"
                                )
                                st.write(f"최근 {period}간 팔고 나가는 중입니다.")
                                st.write(f"단, 일시적 매수 유입 시 평균가는 {int(inst_avg_price):,}원입니다.")
                        else:
                            st.metric(
                                label="🏢 기관 수급 상태", 
                                value="계산 불가",
                                delta="이탈 우위",
                                delta_color="inverse"
                            )
                            st.caption(f"최근 {period}간 전체적으로 팔고 나가는 중입니다.")

                    with col3:
                        if foreign_avg_price:
                            if total_foreign_net_vol > 0:
                                st.metric(
                                    label="🌎 외인 매집 평단", 
                                    value=f"{int(foreign_avg_price):,}원",
                                    delta=f"매집 중 ({'+' if foreign_percentage >= 0 else ''}{foreign_percentage:.2f}%)"
                                )
                                st.caption(f"순매수량: {foreign_net_vol:,}주")
                            else:
                                st.metric(
                                    label="🌎 외인 수급 상태", 
                                    value="순매도(이탈) 중",
                                    delta="이탈 우위",
                                    delta_color="inverse"
                                )
                                st.write(f"최근 {period}간 팔고 나가는 중입니다.")
                                st.write(f"단, 일시적 매수 유입 시 평균가는 {int(foreign_avg_price):,}원입니다.")
                        else:
                            st.metric(
                                label="🌎 외인 수급 상태", 
                                value="계산 불가",
                                delta="이탈 우위",
                                delta_color="inverse"
                            )
                            st.caption(f"최근 {period}간 전체적으로 팔고 나가는 중입니다.")

                            
            
                    st.markdown(f"### 📈 최근 {active_period} 주가 추이 및 수급 평단가")
                    # st.caption(f"조회 기간: **{start_date} ~ {end_date}**")

                    # 2. 차트 그리기 (Plotly 사용)
                    if not df_ohlcv.empty:
                        import plotly.graph_objects as go
                        
                        fig = go.Figure()
                        # 종가 라인 차트
                        fig.add_trace(go.Scatter(
                            x=df_ohlcv.index, y=df_ohlcv['종가'], 
                            mode='lines', name='종가', 
                            line=dict(color='#ff9900', width=2)
                        ))

                        inst_percentage = (df_ohlcv['종가'].iloc[-1] / inst_avg_price * 100 - 100) if inst_avg_price else 0
                        foreign_percentage = (df_ohlcv['종가'].iloc[-1] / foreign_avg_price * 100 - 100) if foreign_avg_price else 0
                        retail_percentage = (df_ohlcv['종가'].iloc[-1] / retail_avg_price * 100 - 100) if retail_avg_price else 0

                        # 기관 평단가 가로선 추가 (매집 상태일 때만)
                        if inst_avg_price is not None and total_inst_net_vol > 0:
                            fig.add_hline(
                                y=inst_avg_price, line_dash="dash", line_color="#00cc66", 
                                annotation_text=f"🏢 기관 평단: {int(inst_avg_price):,}원 ({'+' if inst_percentage >= 0 else ''}{inst_percentage:.2f}%)", 
                                annotation_position="top left"
                            )
                            
                        # 외국인 평단가 가로선 추가 (매집 상태일 때만)
                        if foreign_avg_price is not None and total_foreign_net_vol > 0:
                            fig.add_hline(
                                y=foreign_avg_price, line_dash="dash", line_color="#3399ff", 
                                annotation_text=f"🌎 외인 평단: {int(foreign_avg_price):,}원 ({'+' if foreign_percentage >= 0 else ''}{foreign_percentage:.2f}%)", 
                                annotation_position="bottom right"
                            )
                            
                        # 개인 평단가 가로선 추가 (매집 상태일 때만)
                        if retail_avg_price is not None and total_retail_net_vol > 0:
                            fig.add_hline(
                                y=retail_avg_price, line_dash="dash", line_color="#ff3366", 
                                annotation_text=f"🧍 개인 평단: {int(retail_avg_price):,}원 ({'+' if retail_percentage >= 0 else ''}{retail_percentage:.2f}%)", 
                                annotation_position="bottom left"
                            )
                        
                        # 레이아웃 최적화 (마우스 휠 축소 시 빈공간 깨짐 방지 위해 x축 범위 고정)
                        fig.update_layout(
                            height=350,
                            margin=dict(l=0, r=0, t=10, b=0),
                            xaxis=dict(
                                range=[df_ohlcv.index.min(), df_ohlcv.index.max()],
                                fixedrange=False # 확대는 가능하게 허용
                            ),
                            yaxis_title="주가 (원)",
                            hovermode="x unified",
                            showlegend=False
                        )
                        
                        st.plotly_chart(fig, use_container_width=True)
                        
                        # 3. 추가 차트: 투자자별(기관/외국인/개인) 누적 순매수량 동시 표시
                        st.markdown("### 📊 투자자별 누적 순매수량 추이")
                        
                        df_cum_inst = df_investor_vol['기관합계'].cumsum()
                        df_cum_foreign = df_investor_vol['외국인합계'].cumsum()
                        df_cum_retail = df_investor_vol['개인'].cumsum()
                        
                        fig_cum = go.Figure()
                        
                        # 개인 선 추가
                        fig_cum.add_trace(go.Scatter(
                            x=df_cum_retail.index, y=df_cum_retail, 
                            mode='lines', name='개인 누적순매수', 
                            line=dict(color="#fafafa", width=3),
                            hovertemplate='<b>개인</b> 누적순매수: %{y:,.0f}주<extra></extra>'
                        ))
                        
                        # 기관 선 추가
                        fig_cum.add_trace(go.Scatter(
                            x=df_cum_inst.index, y=df_cum_inst, 
                            mode='lines', name='기관 누적순매수',
                            line=dict(color="#3363ff", width=3),
                            hovertemplate='<b>기관</b> 누적순매수: %{y:,.0f}주<extra></extra>'
                        ))
                        
                        # 외국인 선 추가
                        fig_cum.add_trace(go.Scatter(
                            x=df_cum_foreign.index, y=df_cum_foreign, 
                            mode='lines', name='외국인 누적순매수', 
                            line=dict(color="#fc2727", width=3),
                            hovertemplate='<b>외국인</b> 누적순매수: %{y:,.0f}주<extra></extra>'
                        ))
                        
                        fig_cum.update_layout(
                            height=300,
                            margin=dict(l=0, r=0, t=10, b=0),
                            xaxis=dict(
                                range=[df_cum_inst.index.min(), df_cum_inst.index.max()],
                                fixedrange=True,
                                showgrid=False
                            ),
                            yaxis=dict(
                                fixedrange=True,
                                showgrid=False
                            ),
                            yaxis_title="누적 수량 (주)",
                            hovermode="x unified",
                            showlegend=True,
                            legend=dict(
                                orientation="h",
                                yanchor="bottom",
                                y=1.02,
                                xanchor="right",
                                x=1
                            )
                        )
                        
                        st.plotly_chart(fig_cum, use_container_width=True)
                        
                    else:
                        st.warning("선택한 기간의 주가 데이터가 존재하지 않습니다.")

                except Exception as e:
                    st.error("투자자별 데이터를 불러오는 데 실패했습니다.")
                    st.exception(e)
