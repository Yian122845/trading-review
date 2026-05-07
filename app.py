import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# --- 1. 基礎配置 ---
# 請將下方連結替換為你 Google 試算表發佈的 CSV 網址
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSskCEczxpD2rJc1k3W8ozcMZTmuOrfhweqBEXz2UHSptZIPmaLb1p3zQkvEOBxJJHKq4eafglsNpL4/pub?output=csv"

st.set_page_config(page_title="PA 策略根源量化系統", layout="wide")
st.title("🛡️ 價格行為 (PA) 實戰與風險效率分析儀表板")

@st.cache_data(ttl=60) 
def load_data():
    # 使用 usecols=[0,1,2,3] 強制只讀取前四欄，避開右側幽靈數據導致的錯誤
    data = pd.read_csv(SHEET_URL, usecols=[0, 1, 2, 3], on_bad_lines='skip')
    
    # 強制重命名欄位，確保後續邏輯對齊
    data.columns = ['Date', 'Profit', 'Signal', 'MAE']
    
    # 數據清洗：處理日期、將 Profit 與 MAE 轉為數字，無法轉換的設為 0
    data['Date'] = pd.to_datetime(data['Date'], format='mixed')
    data['Profit'] = pd.to_numeric(data['Profit'], errors='coerce').fillna(0)
    data['MAE'] = pd.to_numeric(data['MAE'], errors='coerce').fillna(0)
    
    # 過濾掉 Profit 為 0 且 Date 為空的無效行
    data = data.dropna(subset=['Date'])
    return data

# --- 2. 主程式邏輯 ---
try:
    df = load_data()

    # --- A. 核心指標計算 ---
    total_trades = len(df)
    wins = df[df['Profit'] > 0]
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
    avg_win = wins['Profit'].mean() if not wins.empty else 0
    avg_loss = abs(df[df['Profit'] < 0]['Profit'].mean()) if not df[df['Profit'] < 0].empty else 1
    payoff_ratio = avg_win / avg_loss
    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)

    # 1. 頂部核心數據顯示
    st.subheader("📌 核心績效數據")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("總勝率", f"{win_rate:.1f} %")
    m2.metric("日盈虧比 (Payoff)", f"{payoff_ratio:.2f}")
    m3.metric("每筆期待值 (E)", f"$ {expectancy:,.0f}")
    m4.metric("累積總損益", f"$ {df['Profit'].sum():,.0f}")

    # 2. 資產曲線與回撤圖表 (每日匯總邏輯)
    st.divider()
    daily_df = df.groupby('Date')['Profit'].sum().reset_index().sort_values('Date')
    daily_df['Equity'] = daily_df['Profit'].cumsum()
    daily_df['Max_Equity'] = daily_df['Equity'].cummax()
    daily_df['Drawdown'] = daily_df['Equity'] - daily_df['Max_Equity']

    c1, c2 = st.columns(2)
    with c1:
        st.write("📈 累積損益曲線 (Daily Equity)")
        st.line_chart(daily_df.set_index('Date')['Equity'])
    with c2:
        st.write("📉 風險回撤分析 (Drawdown)")
        st.area_chart(daily_df.set_index('Date')['Drawdown'], color="#ff4b4b")

    # 3. 策略標籤效能分析 (Signal)
    st.divider()
    st.subheader("🎯 策略標籤效能拆解")
    # 過濾掉 Signal 為空的行再進行統計
    strat_df = df[df['Signal'].notna() & (df['Signal'] != "")]
    if not strat_df.empty:
        strat_stats = strat_df.groupby('Signal')['Profit'].agg(['sum', 'count', 'mean']).reset_index()
        strat_stats.columns = ['策略標籤', '總損益', '交易次數', '平均獲利']
        
        sc1, sc2 = st.columns([3, 2])
        with sc1:
            fig_strat = px.bar(strat_stats, x='策略標籤', y='總損益', color='策略標籤', 
                               title="各策略總貢獻度", text_auto='.2s')
            st.plotly_chart(fig_strat, use_container_width=True)
        with sc2:
            st.write("各策略明細數據")
            st.dataframe(strat_stats, hide_index=True, use_container_width=True)
    else:
        st.info("尚未在試算表中填寫 Signal 標籤，暫無分析數據。")

    # 4. 風險效率分析 (Profit vs. MAE) + 效能邊界線 (CML 概念)
    st.divider()
    st.subheader("🕵️ 風險效率分析 (交易 CML 線)")
    
    # 準備畫圖數據：將 MAE 轉為絕對值作為風險單位
    df['MAE_abs'] = df['MAE'].abs()
    
    fig_mae = px.scatter(df, x='MAE_abs', y='Profit', color='Signal', 
                         hover_data=['Date'],
                         labels={'MAE_abs': '承擔的風險 (|MAE|)', 'Profit': '最終損益 (Profit)'},
                         title="報酬 vs. 風險散佈圖")

    # 計算圖表最大範圍，用來畫斜率線
    max_risk = df['MAE_abs'].max() if len(df) > 0 else 1000
    max_profit = df['Profit'].max() if len(df) > 0 else 1000
    max_limit = max(max_risk, max_profit)
    
    # 畫出 1:1 效率線 (代表賺的跟賠的一樣多)
    fig_mae.add_trace(go.Scatter(x=[0, max_limit], y=[0, max_limit], 
                                 mode='lines', name='1:1 損益平衡線',
                                 line=dict(color='gray', dash='dash')))
    
    # 畫出 1:2 優質交易線 (PA 核心目標：小風險換大報酬)
    fig_mae.add_trace(go.Scatter(x=[0, max_limit], y=[0, max_limit*2], 
                                 mode='lines', name='1:2 優質交易線',
                                 line=dict(color='green', dash='dot')))

    fig_mae.update_layout(xaxis_title="過程中的最大浮虧 (|MAE|)", yaxis_title="平倉最終損益 (Profit)")
    st.plotly_chart(fig_mae, use_container_width=True)
    
    st.info("💡 **解讀建議**：落在『優質交易線』左上方的點，代表你進場後幾乎沒受什麼痛苦（MAE 小）就換到了大幅利潤（Profit 大）。")

except Exception as e:
    st.error(f"系統運行錯誤：{e}")
    st.write("提示：請確保 CSV 連結正確，且試算表包含 Date, Profit, Signal, MAE 這四個欄位。")