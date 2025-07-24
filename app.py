import streamlit as st
import pandas as pd
import pdfplumber
import re
import os
from datetime import datetime
import io
from openpyxl import Workbook, load_workbook
import plotly.express as px
import plotly.graph_objects as go

# ページ設定
st.set_page_config(page_title="地方銀行財務データ抽出", layout="wide")

# データベース管理関数
def initialize_database(db_path="data/securities_database.xlsx"):
    """データベースを初期化する"""
    # dataディレクトリが存在しない場合は作成
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    if not os.path.exists(db_path):
        # 新規データベースを作成
        wb = Workbook()
        ws = wb.active
        ws.title = "証券データ"
        
        # ヘッダーを設定
        headers = ['年月', '国債', '地方債', '短期社債', '社債', '株式', '外国証券', 'その他の証券', '更新日時']
        for col, header in enumerate(headers, 1):
            ws.cell(row=1, column=col, value=header)
        
        wb.save(db_path)
        st.info(f"新しいデータベースを作成しました: {db_path}")
    
    return db_path

def save_to_database(data, db_path="data/securities_database.xlsx"):
    """データをExcelデータベースに保存する"""
    try:
        # データベースを初期化
        initialize_database(db_path)
        
        # Excelファイルを読み込み
        wb = load_workbook(db_path)
        ws = wb.active
        
        # 現在の日時を追加
        data_with_timestamp = data.copy()
        data_with_timestamp['更新日時'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 既存データから同じ年月のレコードを探す
        existing_row = None
        for row in range(2, ws.max_row + 1):
            if ws.cell(row=row, column=1).value == data['年月']:
                existing_row = row
                break
        
        # データを書き込む列の順序
        columns = ['年月', '国債', '地方債', '短期社債', '社債', '株式', '外国証券', 'その他の証券', '更新日時']
        
        if existing_row:
            # 既存レコードを更新
            for col, column_name in enumerate(columns, 1):
                ws.cell(row=existing_row, column=col, value=data_with_timestamp[column_name])
            action = "updated"
        else:
            # 新規レコードを追加
            new_row = ws.max_row + 1
            for col, column_name in enumerate(columns, 1):
                ws.cell(row=new_row, column=col, value=data_with_timestamp[column_name])
            action = "added"
        
        # データを年月順でソートしてから保存
        # まずデータをDataFrameに変換
        data_for_sorting = []
        for row in range(2, ws.max_row + 1):
            row_data = []
            for col in range(1, len(columns) + 1):
                cell_value = ws.cell(row=row, column=col).value
                row_data.append(cell_value)
            if any(cell is not None for cell in row_data):  # 空行でない場合のみ追加
                data_for_sorting.append(row_data)
        
        # DataFrameを作成してソート
        if data_for_sorting:
            df_sort = pd.DataFrame(data_for_sorting, columns=columns)
            # 年月列でソート（昇順：古いデータから新しいデータへ）
            df_sort = df_sort.sort_values('年月', ascending=True)
            
            # ワークシートをクリア（ヘッダー以外）
            for row in range(ws.max_row, 1, -1):
                ws.delete_rows(row)
            
            # ソートされたデータを書き戻し
            for idx, (_, row_data) in enumerate(df_sort.iterrows(), start=2):
                for col, column_name in enumerate(columns, 1):
                    ws.cell(row=idx, column=col, value=row_data[column_name])
        
        # Excelファイルを保存
        wb.save(db_path)
        
        return True, action
    
    except Exception as e:
        return False, str(e)

def load_database(db_path="data/securities_database.xlsx"):
    """データベースからデータを読み込む"""
    try:
        if os.path.exists(db_path):
            df = pd.read_excel(db_path)
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"データベースの読み込みエラー: {str(e)}")
        return pd.DataFrame()

def extract_securities_from_pdf(pdf_file):
    """PDFから証券データを抽出する"""
    try:
        # pdfplumberでPDFを開く
        with pdfplumber.open(pdf_file) as pdf:
            # 2ページ目を取得（0ベースなので1）
            if len(pdf.pages) < 2:
                st.error("PDFファイルに2ページ目が見つかりません")
                return None
                
            page = pdf.pages[1]
            
            # テキストを抽出
            page_text = page.extract_text()
            
            # デバッグ用：抽出したテキストを表示
            with st.expander("🔍 抽出されたPDFテキスト（デバッグ用）"):
                st.text_area("PDFテキスト", page_text, height=400)
            
            # テーブルを抽出
            tables = page.extract_tables()
            
            # デバッグ用：テーブル構造を表示
            with st.expander("🔍 抽出されたテーブル構造（デバッグ用）"):
                for i, table in enumerate(tables):
                    st.write(f"**テーブル {i+1}:**")
                    if table:
                        try:
                            # 列名の重複を処理
                            headers = table[0] if table[0] else None
                            if headers:
                                # 重複した列名に番号を追加
                                unique_headers = []
                                header_counts = {}
                                for header in headers:
                                    if header in header_counts:
                                        header_counts[header] += 1
                                        unique_headers.append(f"{header}_{header_counts[header]}")
                                    else:
                                        header_counts[header] = 1
                                        unique_headers.append(header)
                                
                                df = pd.DataFrame(table[1:], columns=unique_headers)
                            else:
                                df = pd.DataFrame(table)
                            
                            st.dataframe(df)
                        except Exception as e:
                            st.write(f"テーブル表示エラー: {str(e)}")
                            # エラーの場合は生データを表示
                            st.write("生データ:")
                            for j, row in enumerate(table[:5]):  # 最初の5行のみ表示
                                st.write(f"行{j}: {row}")
            
            # 年月の抽出（例：2025年3月中平残）
            year_month_match = re.search(r'(\d{4})年\s*(\d{1,2})月', page_text)
            if year_month_match:
                year = year_month_match.group(1)
                month = year_month_match.group(2).zfill(2)
                year_month = f"{year}-{month}"
            else:
                year_month = "不明"
            
            # 証券の金額を抽出
            def extract_securities_amounts(text, tables):
                """各証券の金額を抽出する"""
                debug_info = []
                
                # 抽出対象の証券項目（スペースを含む形式も考慮）
                # 注意: 検索順序が重要！より具体的なパターンを先に検索する
                securities_patterns = {
                    '短期社債': ['短 期 社 債', '短期社債'],  # 「社債」より先に検索
                    '社債': ['社 債', '社債'],                # 「短期社債」の後に検索
                    '国債': ['国 債', '国債'],
                    '地方債': ['地 方 債', '地方債'],
                    '株式': ['株 式', '株式'],
                    '外国証券': ['外 国 証 券', '外国証券'],
                    'その他の証券': ['そ の 他 の 証 券', 'その他の証券', 'そ の 他 証 券']
                }
                
                securities_data = {}
                
                # 各証券項目を初期化
                for security in securities_patterns.keys():
                    securities_data[security] = "0"
                
                # 方法1: テキストから直接抽出（スペースを考慮）
                debug_info.append("テキストから直接抽出を開始...")
                
                # テキストを行に分割
                lines = text.split('\n')
                
                for security, patterns in securities_patterns.items():
                    debug_info.append(f"{security}を検索中...")
                    
                    for pattern in patterns:
                        for line_idx, line in enumerate(lines):
                            # 社債の場合は短期社債と区別するための特別処理
                            if security == '社債' and pattern in line:
                                # 「短期」が含まれていないことを確認
                                if '短期' not in line and '短 期' not in line:
                                    debug_info.append(f"{security}を含む行を発見 (パターン: '{pattern}', 行{line_idx}): {line}")
                                    
                                    # パターンの後にある数値を抽出
                                    pattern_index = line.find(pattern)
                                    if pattern_index >= 0:
                                        # パターンの後の部分を取得
                                        after_pattern = line[pattern_index + len(pattern):]
                                        
                                        # 最初の数値を探す
                                        numbers = re.findall(r'([0-9,]+)', after_pattern)
                                        for num in numbers:
                                            clean_num = num.replace(',', '')
                                            if clean_num.isdigit() and len(clean_num) >= 4:
                                                debug_info.append(f"{security}の金額を発見: {clean_num}")
                                                securities_data[security] = clean_num
                                                break
                                        
                                        if securities_data[security] != "0":
                                            break
                                else:
                                    debug_info.append(f"{security}の候補行をスキップ (短期社債と判定): {line}")
                            
                            elif security != '社債' and pattern in line:
                                debug_info.append(f"{security}を含む行を発見 (パターン: '{pattern}', 行{line_idx}): {line}")
                                
                                # パターンの後にある数値を抽出
                                pattern_index = line.find(pattern)
                                if pattern_index >= 0:
                                    # パターンの後の部分を取得
                                    after_pattern = line[pattern_index + len(pattern):]
                                    
                                    # 最初の数値を探す
                                    numbers = re.findall(r'([0-9,]+)', after_pattern)
                                    for num in numbers:
                                        clean_num = num.replace(',', '')
                                        if clean_num.isdigit() and len(clean_num) >= 4:
                                            debug_info.append(f"{security}の金額を発見: {clean_num}")
                                            securities_data[security] = clean_num
                                            break
                                    
                                    if securities_data[security] != "0":
                                        break
                        
                        # 見つかったら他のパターンを試さない
                        if securities_data[security] != "0":
                            break
                
                # 方法2: 正規表現による抽出（スペースを考慮した柔軟なパターン）
                debug_info.append("正規表現による抽出を開始...")
                
                for security, patterns in securities_patterns.items():
                    if securities_data[security] == "0":
                        debug_info.append(f"{security}の正規表現マッチングを試行...")
                        
                        for pattern in patterns:
                            # 社債の場合は短期社債を除外する正規表現を使用
                            if security == '社債':
                                # 負の先読みを使用して「短期」が前にない「社債」を抽出
                                flexible_pattern = pattern.replace(' ', r'\s*')
                                regex_patterns = [
                                    rf'(?<!短\s*期\s*){flexible_pattern}\s+([0-9,]+)',
                                    rf'(?<!短期){re.escape(pattern)}\s+([0-9,]+)',
                                ]
                            else:
                                # 通常の処理
                                flexible_pattern = pattern.replace(' ', r'\s*')
                                regex_patterns = [
                                    rf'{flexible_pattern}\s+([0-9,]+)',
                                    rf'{re.escape(pattern)}\s+([0-9,]+)',
                                ]
                            
                            for regex_pattern in regex_patterns:
                                match = re.search(regex_pattern, text)
                                if match:
                                    found_amount = match.group(1).replace(',', '')
                                    if found_amount.isdigit() and len(found_amount) >= 4:
                                        debug_info.append(f"{security}を正規表現で抽出 (パターン: '{pattern}'): {found_amount}")
                                        securities_data[security] = found_amount
                                        break
                            
                            if securities_data[security] != "0":
                                break
                
                # 方法3: テーブルから抽出（最後の手段）
                debug_info.append("テーブルからの抽出を開始...")
                
                for table_idx, table in enumerate(tables):
                    if not table:
                        continue
                    
                    debug_info.append(f"テーブル {table_idx + 1} を処理中...")
                    
                    for row_idx, row in enumerate(table):
                        if not row:
                            continue
                        
                        row_text = ' '.join([str(cell) if cell else '' for cell in row])
                        
                        for security, patterns in securities_patterns.items():
                            if securities_data[security] == "0":
                                for pattern in patterns:
                                    if pattern in row_text:
                                        debug_info.append(f"テーブルで{security}を含む行を発見 (テーブル{table_idx+1}, 行{row_idx}): {row}")
                                        
                                        # この行から数値を抽出
                                        for cell_idx, cell in enumerate(row):
                                            if cell and isinstance(cell, str):
                                                numbers = re.findall(r'([0-9,]+)', cell)
                                                for num in numbers:
                                                    clean_num = num.replace(',', '')
                                                    if clean_num.isdigit() and len(clean_num) >= 4:
                                                        debug_info.append(f"テーブルで{security}の金額を発見: {clean_num}")
                                                        securities_data[security] = clean_num
                                                        break
                                                if securities_data[security] != "0":
                                                    break
                                        if securities_data[security] != "0":
                                            break
                                if securities_data[security] != "0":
                                    break
                
                return securities_data, debug_info
            
            # 証券金額を抽出
            securities_data, debug_info = extract_securities_amounts(page_text, tables)
            
            # デバッグ情報を表示
            with st.expander("🔍 抽出結果の詳細（デバッグ用）"):
                st.write("**抽出処理のログ:**")
                for info in debug_info:
                    st.write(f"- {info}")
                
                # 証券キーワードを含む行をテーブルから探す
                st.write("**証券を含むテーブル行の詳細:**")
                securities_patterns = {
                    '短期社債': ['短 期 社 債', '短期社債'],  # 「社債」より先に検索
                    '社債': ['社 債', '社債'],                # 「短期社債」の後に検索
                    '国債': ['国 債', '国債'],
                    '地方債': ['地 方 債', '地方債'],
                    '株式': ['株 式', '株式'],
                    '外国証券': ['外 国 証 券', '外国証券'],
                    'その他の証券': ['そ の 他 の 証 券', 'その他の証券', 'そ の 他 証 券']
                }
                
                for i, table in enumerate(tables):
                    if not table:
                        continue
                    st.write(f"テーブル {i+1}:")
                    for j, row in enumerate(table):
                        if row:
                            row_text = ' '.join([str(cell) if cell else '' for cell in row])
                            for security, patterns in securities_patterns.items():
                                for pattern in patterns:
                                    if pattern in row_text:
                                        st.write(f"  {security} (パターン: '{pattern}') - 行{j}: {row}")
                                        # 各セルの数値をチェック
                                        for k, cell in enumerate(row):
                                            if cell:
                                                numbers = re.findall(r'([0-9,]+)', str(cell))
                                                if numbers:
                                                    st.write(f"    セル{k} '{cell}' から数値: {numbers}")
                                        break
                                if any(pattern in row_text for pattern in patterns):
                                    break
                
                st.write("**最終抽出結果:**")
                for security, amount in securities_data.items():
                    st.write(f"- {security}: {amount}")
            
            return {
                '年月': year_month,
                **securities_data
            }
        
    except Exception as e:
        st.error(f"PDFの読み込み中にエラーが発生しました: {str(e)}")
        return None

# メインアプリケーション
st.title("🏦 証券データ抽出システム")
st.markdown("---")

# サイドバー
with st.sidebar:
    st.header("ページ選択")
    page = st.selectbox(
        "表示するページを選択してください",
        ["データ抽出", "グラフ表示"]
    )
    
    st.markdown("---")
    
    if page == "データ抽出":
        st.header("ファイルアップロード")
        uploaded_file = st.file_uploader(
            "PDFファイルを選択してください",
            type=['pdf'],
            help="地方銀行主要勘定のPDFファイルをアップロードしてください"
        )
    else:
        uploaded_file = None

# メインエリア
if page == "データ抽出":
    # データ抽出ページ
    if uploaded_file is not None:
        # PDFからデータを抽出
        with st.spinner("PDFから証券データを抽出中..."):
            extracted_data = extract_securities_from_pdf(uploaded_file)
        
        if extracted_data:
            st.success("✅ 証券データの抽出が完了しました")
            
            # 抽出したデータを表示
            st.subheader("📊 抽出結果")
            
            # 年月を表示
            st.write(f"**年月: {extracted_data['年月']}**")
            
            # 証券データを3列で表示
            col1, col2, col3 = st.columns(3)
            
            securities_list = ['国債', '地方債', '短期社債', '社債', '株式', '外国証券', 'その他の証券']
            
            for i, security in enumerate(securities_list):
                col_idx = i % 3
                amount = int(extracted_data[security]) if extracted_data[security].isdigit() else 0
                
                if col_idx == 0:
                    with col1:
                        st.metric(security, f"{amount:,} 百万円")
                elif col_idx == 1:
                    with col2:
                        st.metric(security, f"{amount:,} 百万円")
                else:
                    with col3:
                        st.metric(security, f"{amount:,} 百万円")
            
            # データの修正フォーム
            st.subheader("🔧 データの確認・修正")
            
            # セッション状態の初期化
            if 'confirmed_data' not in st.session_state:
                st.session_state.confirmed_data = None
            
            with st.form("data_correction_form"):
                corrected_year_month = st.text_input("年月 (YYYY-MM形式)", value=extracted_data['年月'])
                
                # 各証券項目の入力フィールドを2列で配置
                col_a, col_b = st.columns(2)
                
                corrected_amounts = {}
                
                with col_a:
                    corrected_amounts['国債'] = st.text_input("国債 (百万円)", value=extracted_data['国債'])
                    corrected_amounts['地方債'] = st.text_input("地方債 (百万円)", value=extracted_data['地方債'])
                    corrected_amounts['短期社債'] = st.text_input("短期社債 (百万円)", value=extracted_data['短期社債'])
                    corrected_amounts['社債'] = st.text_input("社債 (百万円)", value=extracted_data['社債'])
                
                with col_b:
                    corrected_amounts['株式'] = st.text_input("株式 (百万円)", value=extracted_data['株式'])
                    corrected_amounts['外国証券'] = st.text_input("外国証券 (百万円)", value=extracted_data['外国証券'])
                    corrected_amounts['その他の証券'] = st.text_input("その他の証券 (百万円)", value=extracted_data['その他の証券'])
                
                if st.form_submit_button("💾 確定"):
                    try:
                        # データの検証
                        final_data = {'年月': corrected_year_month}
                        all_valid = True
                        
                        for security, value in corrected_amounts.items():
                            if not value.isdigit():
                                st.error(f"❌ {security}の値が正しくありません（数値のみ入力してください）")
                                all_valid = False
                            else:
                                final_data[security] = int(value)
                        
                        if all_valid:
                            # セッション状態に保存
                            st.session_state.confirmed_data = final_data
                            st.success("✅ データが確定されました")
                            
                    except ValueError:
                        st.error("❌ 正しい形式で入力してください")
            
            # 確定されたデータがある場合の処理（フォーム外）
            if st.session_state.confirmed_data:
                final_data = st.session_state.confirmed_data
                
                # 確定データを表示
                st.subheader("📋 確定されたデータ")
                
                # 年月を表示
                st.write(f"**年月: {final_data['年月']}**")
                
                display_data = []
                for security in securities_list:
                    display_data.append({
                        '証券種類': security,
                        '金額（百万円）': f"{final_data[security]:,}"
                    })
                
                df_display = pd.DataFrame(display_data)
                st.dataframe(df_display, use_container_width=True)
                
                # データベース保存とCSVダウンロードのボタンを横並びで配置
                col_save, col_download = st.columns(2)
                
                with col_save:
                    if st.button("💾 データベースに保存", type="primary"):
                        success, result = save_to_database(final_data)
                        if success:
                            if result == "updated":
                                st.success("✅ データベースのレコードを更新しました")
                            else:
                                st.success("✅ データベースに新しいレコードを追加しました")
                        else:
                            st.error(f"❌ データベース保存エラー: {result}")
                
                with col_download:
                    # CSV保存のオプション
                    csv_data = pd.DataFrame([final_data])
                    csv_string = csv_data.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📥 CSVファイルをダウンロード",
                        data=csv_string,
                        file_name=f"securities_data_{final_data['年月']}.csv",
                        mime="text/csv"
                    )
    else:
        st.info("👆 左側のサイドバーからPDFファイルをアップロードしてください")
    
    # データベースの内容を表示
    st.markdown("---")
    st.subheader("📊 データベースの内容")
    
    # データベースを読み込み
    db_df = load_database()
    
    if not db_df.empty:
        # データを年月順にソート
        db_df_sorted = db_df.sort_values('年月', ascending=True)
        
        # データを表示
        st.dataframe(db_df_sorted, use_container_width=True)
        
        # データベース全体のCSVダウンロード
        csv_all_data = db_df_sorted.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 全データをCSVでダウンロード",
            data=csv_all_data,
            file_name=f"securities_database_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
        
        # 統計情報
        col_stat1, col_stat2 = st.columns(2)
        with col_stat1:
            st.metric("総レコード数", len(db_df))
        with col_stat2:
            latest_date = db_df['年月'].max() if '年月' in db_df.columns else "不明"
            st.metric("最新データ", latest_date)
            
    else:
        st.info("データベースにデータがありません。PDFファイルを処理してデータを追加してください。")

elif page == "グラフ表示":
    # グラフ表示ページ
    st.subheader("📈 証券データの時系列グラフ")
    
    # データベースを読み込み
    db_df = load_database()
    
    if not db_df.empty:
        # データを年月順にソート（昇順：時系列用）
        db_df_sorted = db_df.sort_values('年月', ascending=True)
        
        # 証券の種類リスト
        securities_columns = ['国債', '地方債', '短期社債', '社債', '株式', '外国証券', 'その他の証券']
        
        # グラフオプション
        col_opt1, col_opt2, col_opt3 = st.columns(3)
        with col_opt1:
            graph_category = st.selectbox(
                "グラフカテゴリ",
                ["金額グラフ", "比率グラフ"]
            )
        
        with col_opt2:
            if graph_category == "金額グラフ":
                chart_type = st.selectbox(
                    "グラフの種類を選択",
                    ["積み上げ棒グラフ", "線グラフ", "エリアグラフ"]
                )
            else:  # 比率グラフ
                chart_type = st.selectbox(
                    "グラフの種類を選択",
                    ["円グラフ（最新期）", "比率積み上げ棒グラフ", "比率線グラフ"]
                )
        
        with col_opt3:
            if graph_category == "金額グラフ":
                show_total = st.checkbox("合計値を表示", value=True)
            else:
                show_total = False
        
        # データの準備
        chart_data = db_df_sorted[['年月'] + securities_columns].copy()
        
        # 数値型に変換（エラー処理付き）
        for col in securities_columns:
            chart_data[col] = pd.to_numeric(chart_data[col], errors='coerce').fillna(0)
        
        # 合計値を計算
        chart_data['合計'] = chart_data[securities_columns].sum(axis=1)
        
        # 比率データの準備（比率グラフの場合）
        if graph_category == "比率グラフ":
            ratio_data = chart_data.copy()
            for col in securities_columns:
                # 合計が0でない行のみ比率を計算
                ratio_data[col] = ratio_data.apply(
                    lambda row: (row[col] / row['合計'] * 100) if row['合計'] > 0 else 0, 
                    axis=1
                )
        
        # 金額グラフの場合は合計値表示オプションを適用
        if graph_category == "金額グラフ" and show_total:
            chart_data['合計表示用'] = chart_data['合計']
        
        # グラフを作成
        if graph_category == "金額グラフ":
            if chart_type == "積み上げ棒グラフ":
                fig = go.Figure()
                
                # 各証券種類の棒を追加
                colors = px.colors.qualitative.Set3
                for i, security in enumerate(securities_columns):
                    fig.add_trace(go.Bar(
                        name=security,
                        x=chart_data['年月'],
                        y=chart_data[security],
                        marker_color=colors[i % len(colors)]
                    ))
                
                fig.update_layout(
                    title="証券データの時系列推移（積み上げ棒グラフ）",
                    xaxis_title="年月",
                    yaxis_title="金額（百万円）",
                    barmode='stack',
                    height=600,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
                
            elif chart_type == "線グラフ":
                fig = go.Figure()
                
                colors = px.colors.qualitative.Set3
                for i, security in enumerate(securities_columns):
                    fig.add_trace(go.Scatter(
                        name=security,
                        x=chart_data['年月'],
                        y=chart_data[security],
                        mode='lines+markers',
                        line_color=colors[i % len(colors)]
                    ))
                
                if show_total:
                    fig.add_trace(go.Scatter(
                        name='合計',
                        x=chart_data['年月'],
                        y=chart_data['合計'],
                        mode='lines+markers',
                        line=dict(width=3, color='black', dash='dash')
                    ))
                
                fig.update_layout(
                    title="証券データの時系列推移（線グラフ）",
                    xaxis_title="年月",
                    yaxis_title="金額（百万円）",
                    height=600,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
                
            else:  # エリアグラフ
                fig = go.Figure()
                
                colors = px.colors.qualitative.Set3
                for i, security in enumerate(securities_columns):
                    fig.add_trace(go.Scatter(
                        name=security,
                        x=chart_data['年月'],
                        y=chart_data[security],
                        mode='lines',
                        stackgroup='one',
                        fill='tonexty' if i > 0 else 'tozeroy',
                        line_color=colors[i % len(colors)]
                    ))
                
                fig.update_layout(
                    title="証券データの時系列推移（エリアグラフ）",
                    xaxis_title="年月",
                    yaxis_title="金額（百万円）",
                    height=600,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
        
        else:  # 比率グラフ
            if chart_type == "円グラフ（最新期）":
                # 最新期のデータを取得
                latest_data = chart_data.iloc[-1]
                
                # 0でない証券のみを表示
                pie_labels = []
                pie_values = []
                pie_colors = []
                colors = px.colors.qualitative.Set3
                
                for i, security in enumerate(securities_columns):
                    if latest_data[security] > 0:
                        pie_labels.append(security)
                        pie_values.append(latest_data[security])
                        pie_colors.append(colors[i % len(colors)])
                
                fig = go.Figure(data=[go.Pie(
                    labels=pie_labels,
                    values=pie_values,
                    marker_colors=pie_colors,
                    textinfo='label+percent',
                    textposition="auto",
                    hovertemplate='%{label}<br>金額: %{value:,.0f}百万円<br>割合: %{percent}<extra></extra>'
                )])
                
                fig.update_layout(
                    title=f"証券構成比率（{latest_data['年月']}）",
                    height=600,
                    showlegend=True,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=-0.1,
                        xanchor="center",
                        x=0.5
                    )
                )
                
            elif chart_type == "比率積み上げ棒グラフ":
                fig = go.Figure()
                
                colors = px.colors.qualitative.Set3
                for i, security in enumerate(securities_columns):
                    fig.add_trace(go.Bar(
                        name=security,
                        x=ratio_data['年月'],
                        y=ratio_data[security],
                        marker_color=colors[i % len(colors)]
                    ))
                
                fig.update_layout(
                    title="証券構成比率の時系列推移（積み上げ棒グラフ）",
                    xaxis_title="年月",
                    yaxis_title="構成比率（%）",
                    barmode='stack',
                    height=600,
                    yaxis=dict(range=[0, 100]),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
                
            else:  # 比率線グラフ
                fig = go.Figure()
                
                colors = px.colors.qualitative.Set3
                for i, security in enumerate(securities_columns):
                    fig.add_trace(go.Scatter(
                        name=security,
                        x=ratio_data['年月'],
                        y=ratio_data[security],
                        mode='lines+markers',
                        line_color=colors[i % len(colors)]
                    ))
                
                fig.update_layout(
                    title="証券構成比率の時系列推移（線グラフ）",
                    xaxis_title="年月",
                    yaxis_title="構成比率（%）",
                    height=600,
                    yaxis=dict(range=[0, 100]),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
        
        # グラフを表示
        st.plotly_chart(fig, use_container_width=True)
        
        # データテーブルも表示
        st.subheader("📊 データテーブル")
        
        # 表示用にデータを整形
        if graph_category == "金額グラフ":
            display_chart_data = chart_data.copy()
            for col in securities_columns + (['合計'] if show_total else []):
                if col in display_chart_data.columns:
                    display_chart_data[col] = display_chart_data[col].apply(lambda x: f"{x:,.0f}")
        else:  # 比率グラフ
            display_chart_data = ratio_data.copy()
            # 合計列を削除（比率では不要）
            if '合計' in display_chart_data.columns:
                display_chart_data = display_chart_data.drop('合計', axis=1)
            for col in securities_columns:
                if col in display_chart_data.columns:
                    display_chart_data[col] = display_chart_data[col].apply(lambda x: f"{x:.1f}%")
        
        st.dataframe(display_chart_data, use_container_width=True)
        
        # 統計情報
        st.subheader("📈 統計情報")
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        
        with col_stat1:
            st.metric("データ期間数", len(chart_data))
        
        if graph_category == "金額グラフ":
            with col_stat2:
                latest_total = chart_data[securities_columns].sum(axis=1).iloc[-1] if len(chart_data) > 0 else 0
                st.metric("最新期合計", f"{latest_total:,.0f} 百万円")
            
            with col_stat3:
                avg_total = chart_data[securities_columns].sum(axis=1).mean() if len(chart_data) > 0 else 0
                st.metric("期間平均", f"{avg_total:,.0f} 百万円")
        else:  # 比率グラフ
            with col_stat2:
                # 最新期で最も高い比率の証券を表示
                if len(chart_data) > 0:
                    latest_ratios = ratio_data.iloc[-1][securities_columns]
                    max_security = latest_ratios.idxmax()
                    max_ratio = latest_ratios.max()
                    st.metric("最新期最大比率", f"{max_security}: {max_ratio:.1f}%")
                else:
                    st.metric("最新期最大比率", "データなし")
            
            with col_stat3:
                # 期間を通じて最も安定している証券（標準偏差が最小）を表示
                if len(chart_data) > 1:
                    ratio_std = ratio_data[securities_columns].std()
                    most_stable = ratio_std.idxmin()
                    stability_value = ratio_std.min()
                    st.metric("最安定証券", f"{most_stable}: σ{stability_value:.1f}%")
                else:
                    st.metric("最安定証券", "データ不足")
        
        # 比率グラフの場合は追加の分析情報を表示
        if graph_category == "比率グラフ" and len(chart_data) > 1:
            st.subheader("📊 構成比率分析")
            
            # 各証券の平均比率と変動係数を表示
            analysis_data = []
            for security in securities_columns:
                avg_ratio = ratio_data[security].mean()
                std_ratio = ratio_data[security].std()
                cv = (std_ratio / avg_ratio * 100) if avg_ratio > 0 else 0  # 変動係数
                
                analysis_data.append({
                    '証券種類': security,
                    '平均比率': f"{avg_ratio:.1f}%",
                    '標準偏差': f"{std_ratio:.1f}%",
                    '変動係数': f"{cv:.1f}%"
                })
            
            analysis_df = pd.DataFrame(analysis_data)
            st.dataframe(analysis_df, use_container_width=True)
            
            # 比率変化の傾向分析
            st.subheader("📈 比率変化の傾向")
            
            if len(chart_data) >= 2:
                trend_info = []
                first_period = ratio_data.iloc[0]
                latest_period = ratio_data.iloc[-1]
                
                for security in securities_columns:
                    change = latest_period[security] - first_period[security]
                    if abs(change) > 1:  # 1%以上の変化のみ表示
                        trend = "増加" if change > 0 else "減少"
                        trend_info.append(f"• **{security}**: {abs(change):.1f}%ポイント{trend}")
                
                if trend_info:
                    st.write("**期間全体での主要な変化:**")
                    for info in trend_info:
                        st.markdown(info)
                else:
                    st.write("大きな構成比率の変化は見られません（±1%以内）")
        
    else:
        st.info("📝 データベースにデータがありません。まずはデータ抽出ページでPDFファイルを処理してデータを追加してください。")

# フッター
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center; color: #666; font-size: 0.8em;'>
    証券データ抽出システム | 地方銀行主要勘定PDFから各種証券データを抽出します
    </div>
    """,
    unsafe_allow_html=True
)
