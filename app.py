import streamlit as st
import pandas as pd
import math
import re
import io

# --- 1. 頁面設定 (手機版優化) ---
st.set_page_config(page_title="萬能揀貨分流系統", page_icon="📦", layout="centered")

hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- 設定廠長解鎖密碼 (可在這裡修改) ---
MANAGER_PASSWORD = "0000"

# --- 2. 智慧欄位辨識 ---
def find_columns(df):
    cols = [str(c).strip() for c in df.columns]
    mapping = {
        'id': ['商品原廠編號', '料品編號', '廠商料號', '品號', '商品編號', '商品ID', 'Item No', '貨號'],
        'name': ['料品名稱', '商品名稱', '品名', '銷售項目', '品項名稱', '規格', '單品詳細'],
        'qty': ['採購數量', '預計進倉量', '預計入庫數量', '數量', '揀貨數量', '借貨數量', '訂購數量', '採購總量']
    }
    found = {}
    for key, keywords in mapping.items():
        for k in keywords:
            if k in cols:
                found[key] = df.columns[cols.index(k)]
                break
    return found

# --- 重量與斤數核心計算函數 ---
def calculate_weight_summary(df_items):
    if df_items.empty:
        return pd.DataFrame()
    
    def extract_weight(name):
        match = re.search(r'(\d+(\.\d+)?)[\s]*(公克|G|g)', str(name), re.IGNORECASE)
        return float(match.group(1)) if match else 1.0

    df_items['單位重量'] = df_items['料品名稱'].apply(extract_weight)
    df_items['數量'] = pd.to_numeric(df_items['數量'], errors='coerce').fillna(0)
    df_items['總重量（公克）'] = df_items['數量'] * df_items['單位重量']

    summary = df_items.groupby(['料品編號', '料品名稱'])['總重量（公克）'].sum().reset_index()
    summary['計算結果（斤）'] = summary['總重量（公克）'].apply(lambda x: math.ceil(x / 600))
    return summary.sort_values(by='料品編號')

# --- 3. App 標題與權限管理介面 ---
st.title("📦 每日揀貨分流系統")

# 在側邊欄或頂部加入身分驗證
st.sidebar.header("🔑 權限登入")
user_role = st.sidebar.radio("請選擇您的身分：", ["一般員工", "廠長 (管理總覽)"])

is_manager = False
if user_role == "廠長 (管理總覽)":
    password_input = st.sidebar.text_input("請輸入廠長管理密碼：", type="password")
    if password_input == MANAGER_PASSWORD:
        st.sidebar.success("🔓 廠長權限已解鎖！")
        is_manager = True
    elif password_input != "":
        st.sidebar.error("❌ 密碼錯誤，請重新輸入。")

# 依據身分顯示不同的控制項
role_choice = ""
custom_prefix = ""
include_v = True

if not is_manager:
    st.markdown("### 👤 員工專區")
    role_choice = st.radio(
        "請選取您今日負責的類別：",
        ["🥜 堅果區 (SC 開頭)", "🍇 果乾/蜜餞區 (G 或 F 開頭)", "🥦 蔬果脆片區 (J 開頭)", "🔍 自訂搜尋料號"]
    )
    if role_choice == "🔍 自訂搜尋料號":
        custom_prefix = st.text_input("請輸入您負責的料號開頭 (例如：H 或 C)：").strip().upper()
    include_v = st.checkbox("✅ 同時幫我統整出『V- 開頭』的商品數量 (成品/組合包)", value=True)
else:
    st.markdown("### 👨‍💼 廠長管理總控面板")
    st.info("💡 您目前擁有最高權限，系統將自動分析並拆分所有人員的揀貨總量。")

# 統一的多檔案上傳按鈕
st.write("---")
uploaded_files = st.file_uploader("📂 點此選擇今日報表 (可一次選多個檔案)", type=['csv', 'xlsx', 'xls'], accept_multiple_files=True)

if uploaded_files:
    all_dfs = []
    
    with st.spinner('⏳ 正在智慧讀取並合併檔案中...'):
        for file in uploaded_files:
            filename = file.name
            try:
                if filename.lower().endswith('.xlsx'):
                    df = pd.read_excel(file)
                else:
                    try:
                        df = pd.read_csv(file, sep=None, engine='python', encoding='utf-8')
                    except:
                        try:
                            df = pd.read_csv(file, sep=None, engine='python', encoding='cp950')
                        except:
                            df = pd.read_excel(file)
                
                col_map = find_columns(df)
                if len(col_map) == 3:
                    df = df.rename(columns={col_map['id']: '料品編號', col_map['name']: '料品名稱', col_map['qty']: '數量'})
                    df = df[['料品編號', '料品名稱', '數量']]
                    all_dfs.append(df)
            except Exception as e:
                st.error(f"❌ 讀取 {filename} 時發生錯誤: {e}")

    # --- 4. 運算處理分流邏輯 ---
    if all_dfs:
        df_combined = pd.concat(all_dfs, ignore_index=True)
        df_combined['料品編號'] = df_combined['料品編號'].astype(str).str.strip()
        
        # --- 【情境 A：一般員工檢視畫面】 ---
        if not is_manager:
            # 依員工選取進行過濾
            if role_choice == "🥜 堅果區 (SC 開頭)":
                target_df = df_combined[(df_combined['料品編號'].str.upper().str.startswith('SC')) & (df_combined['料品編號'].str.upper() != 'SC016-1')]
            elif role_choice == "🍇 果乾/蜜餞區 (G 或 F 開頭)":
                target_df = df_combined[df_combined['料品編號'].str.upper().str.startswith(('G', 'F'))]
            elif role_choice == "🥦 蔬果脆片區 (J 開頭)":
                target_df = df_combined[df_combined['料品編號'].str.upper().str.startswith('J')]
            elif role_choice == "🔍 自訂搜尋料號":
                target_df = df_combined[df_combined['料品編號'].str.upper().str.startswith(custom_prefix)] if custom_prefix else pd.DataFrame()
            
            # 計算員工主類別
            summary_sorted = calculate_weight_summary(target_df.copy())
            
            # 計算 V- 成品
            v_summary_sorted = pd.DataFrame()
            if include_v:
                v_df = df_combined[df_combined['料品編號'].str.upper().str.startswith('V-')].copy()
                if not v_df.empty:
                    v_df['數量'] = pd.to_numeric(v_df['數量'], errors='coerce').fillna(0)
                    v_summary_sorted = v_df.groupby(['料品編號', '料品名稱'])['數量'].sum().reset_index().rename(columns={'數量': '總需求數量'}).sort_values(by='料品編號')

            # 渲染員工畫面
            st.success("✅ 您的專屬個人報表已生成！")
            if not summary_sorted.empty:
                st.subheader(f"📊 您負責的物料撿貨表")
                st.dataframe(summary_sorted, use_container_width=True)
            if include_v and not v_summary_sorted.empty:
                st.subheader(f"📦 V- 開頭商品數量表")
                st.dataframe(v_summary_sorted, use_container_width=True)
                
            # 提供員工專屬 Excel 下載
            if not summary_sorted.empty or not v_summary_sorted.empty:
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    if not summary_sorted.empty: summary_sorted.to_excel(writer, index=False, sheet_name='我的物料揀貨表')
                    if not v_summary_sorted.empty: v_summary_sorted.to_excel(writer, index=False, sheet_name='V-成品數量表')
                st.download_button(label="📥 下載個人工作 Excel 檔", data=output.getvalue(), file_name="我的個人揀貨單.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        # --- 【情境 B：廠長全視角畫面】 ---
        else:
            st.success("✅ 已同步分析全廠各區最新工作總量！")
            
            # 各區資料分流計算
            df_sc = df_combined[(df_combined['料品編號'].str.upper().str.startswith('SC')) & (df_combined['料品編號'].str.upper() != 'SC016-1')]
            df_gf = df_combined[df_combined['料品編號'].str.upper().str.startswith(('G', 'F'))]
            df_j = df_combined[df_combined['料品編號'].str.upper().str.startswith('J')]
            df_v = df_combined[df_combined['料品編號'].str.upper().str.startswith('V-')]
            
            sum_sc = calculate_weight_summary(df_sc.copy())
            sum_gf = calculate_weight_summary(df_gf.copy())
            sum_j = calculate_weight_summary(df_j.copy())
            
            sum_v = pd.DataFrame()
            if not df_v.empty:
                df_v['數量'] = pd.to_numeric(df_v['數量'], errors='coerce').fillna(0)
                sum_v = df_v.groupby(['料品編號', '料品名稱'])['數量'].sum().reset_index().rename(columns={'數量': '總數量'}).sort_values(by='料品編號')

            # 廠長專用：手機多頁籤切換檢視器
            tab1, tab2, tab3, tab4 = st.tabs(["🥜 堅果區總量", "🍇 果乾/蜜餞區總量", "🥦 蔬果脆片區總量", "📦 V-成品總量"])
            
            with tab1:
                st.markdown("#### 🥜 堅果人員工作量預覽")
                if not sum_sc.empty: st.dataframe(sum_sc, use_container_width=True)
                else: st.write("目前無堅果資料")
            with tab2:
                st.markdown("#### 🍇 果乾人員工作量預覽")
                if not sum_gf.empty: st.dataframe(sum_gf, use_container_width=True)
                else: st.write("目前無果乾資料")
            with tab3:
                st.markdown("#### 🥦 蔬果脆片人員工作量預覽")
                if not sum_j.empty: st.dataframe(sum_j, use_container_width=True)
                else: st.write("目前無蔬果脆片資料")
            with tab4:
                st.markdown("#### 📦 V-成品(組合包)打包量預覽")
                if not sum_v.empty: st.dataframe(sum_v, use_container_width=True)
                else: st.write("目前無 V- 商品資料")

            # 廠長專用：一鍵下載全廠整合大報表 (包含所有頁籤)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                if not sum_sc.empty: sum_sc.to_excel(writer, index=False, sheet_name='堅果區')
                if not sum_gf.empty: sum_gf.to_excel(writer, index=False, sheet_name='果乾蜜餞區')
                if not sum_j.empty: sum_j.to_excel(writer, index=False, sheet_name='蔬果脆片區')
                if not sum_v.empty: sum_v.to_excel(writer, index=False, sheet_name='V-成品商品')
            
            st.write("---")
            st.subheader("📥 廠長專用管理大表下載")
            st.download_button(label="📥 下載全廠人員排班管理總表 (Excel)", data=output.getvalue(), file_name="全廠揀貨排班總管理表.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
