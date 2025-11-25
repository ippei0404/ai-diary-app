import streamlit as st
from openai import OpenAI
import gspread
import pandas as pd
from datetime import datetime
import json # JSONを扱うためにインポート

# ===============================================
# 画面のタイトル設定
# ===============================================
st.set_page_config(page_title="AI日記 & 感情分析", page_icon="📖")
st.title("📖 AI日記 & 感情分析アプリ")

# ===============================================
# 🌟🌟🌟 Google Sheets 認証と接続 (Secrets対応) 🌟🌟🌟
# ===============================================
sh = None
try:
    # ----------------------------------------------------------------------
    # 変更点: Streamlit Secretsから認証情報を読み込む
    # sheets_authシークレットは、[sheets_auth]セクション以下の情報を格納している
    sheets_auth_dict = st.secrets["sheets_auth"]
    
    # 認証情報を辞書として渡す
    gc = gspread.service_account_from_dict(sheets_auth_dict) 
    
    # ----------------------------------------------------------------------
    
    # 接続するスプレッドシートのURLを指定
    # ---!!! ここは変更しないといけません !!!---
    # ローカル実行時もデプロイ時も、このURLは必要です。
    spreadsheet_url = "ここに作成したスプレッドシートのURLを貼り付け" 
    # ------------------------------------------
    
    # スプレッドシートを開く
    sh = gc.open_by_url(spreadsheet_url)
    worksheet = sh.sheet1 # 1枚目のシートを使用
    st.sidebar.success("✅ スプレッドシートに接続しました")
    
except Exception as e:
    st.sidebar.error("❌ スプレッドシート接続エラー")
    st.sidebar.info("認証情報（Secrets）またはスプレッドシートURL、共有設定を確認してください。")
    # 詳細なエラーをコンソールに出力
    # print(f"接続エラー詳細: {e}")

# ===============================================
# メイン画面：日記の入力エリアとAPIキー
# ===============================================

# APIキーの入力（安全のためサイドバーで入力）
# 開発者はローカルで実行するため、キー入力が必要です。
api_key = st.sidebar.text_input("OpenAI APIキーを入力してください", type="password")

st.subheader("📝 今日のメモ（雑でOK！）")
user_input = st.text_area("例：疲れた。でもラーメン美味しかった。部長の話が長かった。", height=150)

# ボタンが押されたときの処理
if st.button("日記を生成＆分析する"):
    if not api_key:
        st.error("左側のサイドバーにAPIキーを入力してください！")
    elif not user_input:
        st.warning("日記の内容を入力してください！")
    elif not sh:
        st.error("データベース（スプレッドシート）に接続できていません。左側のエラーを確認してください。")
    else:
        # OpenAIクライアントの準備
        client = OpenAI(api_key=api_key)

        with st.spinner("AIが執筆中...🤖"):
            try:
                # AIへの指示（プロンプト）
                system_prompt = """
                あなたはプロのライター兼心理カウンセラーです。
                ユーザーの「雑な日記メモ」を受け取り、以下の2つの処理を行い、必ず以下の出力形式に従ってください。

                1. 【日記の清書】: 読みやすく、情緒ある丁寧な日本語の日記にリライトする。
                2. 【感情分析】: その日記の「ポジティブ度（100点満点）」をつけ、心理分析に基づいた「一言コメント」を添える。

                出力形式は必ず以下のように厳密に従ってください：
                ---
                【清書された日記】
                （ここに清書された文章）

                【分析結果】
                📊 ポジティブ度: （点数）/100
                💬 AIからのコメント: （ここにコメント）
                ---
                """

                # AIにリクエストを送る
                response = client.chat.completions.create(
                    model="gpt-4o-mini", # コストと速度のバランスが良いモデル
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_input}
                    ]
                )

                # 結果の取得と表示
                result_text = response.choices[0].message.content
                st.markdown("### ✨ 生成結果")
                st.info(result_text)

                # 🌟🌟🌟 スプレッドシートへの保存 🌟🌟🌟
                # 日付、元のメモ、生成結果、分析結果を抽出
                today = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                
                # 分析結果セクション全体を取得
                analysis_section = result_text.split("【分析結果】")[1].strip() if "【分析結果】" in result_text else "N/A"
                
                # スプレッドシートに行を追加
                worksheet.append_row([
                    today,          # 日付
                    user_input,     # 元のメモ
                    result_text,    # 生成された全結果
                    analysis_section# 分析結果
                ])
                st.success(f"日記をスプレッドシートに保存しました。")
                # 🌟🌟🌟 保存処理終わり 🌟🌟🌟

            except Exception as e:
                st.error(f"AI処理中にエラーが発生しました。APIキーまたはプロンプトを確認してください: {e}")

st.markdown("---")
# ===============================================
# 📚 過去の日記表示セクション
# ===============================================
st.header("📚 過去の日記")

if sh: # 接続が成功している場合のみ表示
    try:
        # シートの全データを読み込む
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)

        if not df.empty:
            # 最新の日記が上に来るように並び替え
            df = df.iloc[::-1] 
            
            for index, row in df.iterrows():
                # 分析結果からポジティブ度とコメントを抽出し、見出しに使用
                # エラー対策として、行データが文字列であることを確認してから処理
                analysis_result_str = str(row['分析結果'])
                
                analysis_parts = analysis_result_str.split('\n')
                score_line = next((line for line in analysis_parts if 'ポジティブ度' in line), "📊 ポジティブ度: N/A/100")
                comment_line = next((line for line in analysis_parts if 'AIからのコメント' in line), "💬 AIからのコメント: N/A")
                
                # エキスパンダーのタイトルを作成
                # スコアを抽出するために、'/'で分割し、さらに':'で分割する
                try:
                    score = score_line.split(':')[1].strip()
                except IndexError:
                    score = "N/A"
                
                expander_title = f"🗓️ {str(row['日付']).split(' ')[0]} - {score}"
                
                with st.expander(expander_title):
                    st.markdown("#### ✨ 清書された日記")
                    
                    # 生成結果全体から清書された日記部分を抽出して表示
                    diary_entry_raw = str(row['生成結果'])
                    diary_entry = diary_entry_raw.split("【清書された日記】")[-1].split("【分析結果】")[0].strip()
                    st.markdown(diary_entry)
                    
                    st.markdown("#### 💖 感情分析")
                    st.markdown(score_line)
                    st.markdown(comment_line)
                    
                    st.caption(f"**（元のメモ）**：{str(row['元のメモ'])}")

        else:
            st.info("まだ日記が保存されていません。日記を生成して保存してください。")
            
    except Exception as e:
        st.error(f"過去の日記読み込みエラー: データ形式を確認してください。{e}")