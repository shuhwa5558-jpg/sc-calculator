import streamlit as st
import pandas as pd
import math
import re
import io

# --- 1. 頁面設定 (手機版優化) ---
st.set_page_config(page_title="萬能揀貨分析儀", page_icon="📦", layout="centered")

# 隱藏右下角的浮水印與選單，讓它更像原生 App
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

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

# --- 3. App 標題與介面 ---
st.title("📦 SC 揀貨分析儀")
st.markdown("請上傳各平台報表，系統將自動合併並計算 SC 揀貨量。")

# 多檔案上傳按鈕 (手機上會叫出檔案總管)
uploaded_files = st.file_uploader("📂 點此選擇檔案 (可一次選多個)", type=['csv', 'xlsx', 'xls'], accept_multiple_files=True)

if uploaded_files:
    all_dfs = []
    
    # 顯示載入動畫
    with st.spinner('⏳ 正在智慧辨識與合併檔案中...'):
        for file in uploaded_files:
            filename = file.name
            try:
                # 讀取檔案
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
                
                # 辨識欄位
                col_map = find_columns(df)
                if len(col_map) == 3:
                    df = df.rename(columns={col_map['id']: '料品編號', col_map['name']: '料品名稱', col_map['qty']: '數量'})
                    df = df[['料品編號', '料品名稱', '數量']]
                    all_dfs.append(df)
                else:
                    st.warning(f"⚠️ 檔案 {filename} 找不到對應欄位，已略過。")
            except Exception as e:
                st.error(f"❌ 讀取 {filename} 時發生錯誤: {e}")

    # --- 4. 運算邏輯 ---
    if all_dfs:
        st.success(f"✅ 成功讀取 {len(all_dfs)} 份檔案，處理完成！")
        
        df_combined = pd.concat(all_dfs, ignore_index=True)
        df_combined['料品編號'] = df_combined['料品編號'].astype(str).str.strip()
        
        sc_items = df_combined[
            (df_combined['料品編號'].str.upper().str.startswith('SC')) & 
            (df_combined['料品編號'].str.upper() != 'SC016-1')
        ].copy()
        
        if sc_items.empty:
            st.warning("⚠️ 合併後的資料中，找不到符合條件的 SC 產品。")
        else:
            def extract_weight(name):
                match = re.search(r'(\d+(\.\d+)?)[\s]*(公克|G|g)', str(name), re.IGNORECASE)
                return float(match.group(1)) if match else 1.0

            sc_items['單位重量'] = sc_items['料品名稱'].apply(extract_weight)
            sc_items['數量'] = pd.to_numeric(sc_items['數量'], errors='coerce').fillna(0)
            sc_items['總重量（公克）'] = sc_items['數量'] * sc_items['單位重量']

            summary = sc_items.groupby(['料品編號', '料品名稱'])['總重量（公克）'].sum().reset_index()
            summary['計算結果（斤）'] = summary['總重量（公克）'].apply(lambda x: math.ceil(x / 600))
            summary_sorted = summary.sort_values(by='料品編號')

            # --- 5. 顯示結果與下載 ---
            st.subheader(f"📊 分析結果 (共 {len(summary_sorted)} 筆)")
            
            # 在手機上會顯示為可以左右滑動的漂亮表格
            st.dataframe(summary_sorted, use_container_width=True)

            # 將結果存入記憶體並提供下載
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                summary_sorted.to_excel(writer, index=False, sheet_name='合併結果')
            excel_data = output.getvalue()

            st.download_button(
                label="📥 下載 Excel 報表",
                data=excel_data,
                file_name="SC多檔合併計算結果.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
