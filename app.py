import streamlit as st
from openai import OpenAI
import gspread
import pandas as pd
from datetime import datetime
import json

# ===============================================
# 🔐 セキュリティ設定 (最優先)
# ===============================================
def check_password():
    """パスワード認証を行う関数"""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    st.set_page_config(page_title="ログイン", page_icon="🔒")
    st.title("🔒 ログインが必要です")

    password_input = st.text_input("パスワードを入力してください", type="password")
    
    if st.button("ログイン"):
        # Secretsからパスワードを取得して照合
        try:
            correct_password = st.secrets["app_password"]
            if password_input == correct_password:
                st.session_state.password_correct = True
                st.rerun() # 画面をリロードしてアプリを表示
            else:
                st.error("パスワードが違います")
        except Exception:
            st.error("Secretsに 'app_password' が設定されていません。Streamlit Cloudの設定を確認してください。")
            
    return False

# ログインしていない場合はここでストップ（これより下のコードは実行されません）
if not check_password():
    st.stop()

# ===============================================
# アプリ本編
# ===============================================
st.title("🎨 AI絵日記 & 感情分析アプリ")

# ===============================================
# 🌟 Google Sheets 認証と接続 (Secrets対応)
# ===============================================
sh = None
worksheet = None
try:
    # Secretsから認証情報を読み込む
    sheets_auth_dict = st.secrets["sheets_auth"]
    gc = gspread.service_account_from_dict(sheets_auth_dict) 
    
    # URLの設定
    # ---!!! ここをあなたのスプレッドシートのURLに修正してください !!!---
    spreadsheet_url = "https://docs.google.com/spreadsheets/d/1OCRBMTg2a39M_uVG-YmsMZMtdq4R5XzOv26nYx1ajHQ"
    # ----------------------------------------------------------------------
    
    sh = gc.open_by_url(spreadsheet_url)
    worksheet = sh.sheet1
    
except Exception as e:
    st.sidebar.error("❌ データベース接続エラー")
    st.sidebar.info("Secretsの設定やURLを確認してください")

# ===============================================
# 🔄 今日の日記合体ロジック用関数
# ===============================================
def get_todays_previous_memo(worksheet):
    """今日すでに書いたメモがあれば取得する"""
    try:
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            return ""
        
        today_str = datetime.now().strftime("%Y/%m/%d")
        
        # '日付'カラムを文字列にして、今日の日付で始まるものを探す
        todays_entries = df[df['日付'].astype(str).str.startswith(today_str)]
        
        if not todays_entries.empty:
            # 今日のメモをすべて結合して返す
            previous_memos = todays_entries['元のメモ'].tolist()
            return "\n\n".join(previous_memos)
    except Exception:
        return ""
    return ""

# ===============================================
# メイン画面
# ===============================================

# APIキー読み込み
try:
    api_key = st.secrets["openai_api_key"]
except:
    st.error("OpenAI APIキーが設定されていません")
    st.stop()

# 今日の過去メモを取得（合体用）
previous_memo = ""
if worksheet:
    previous_memo = get_todays_previous_memo(worksheet)

st.subheader("📝 今日のメモ")

# 過去のメモがある場合はヒントを表示
if previous_memo:
    st.info(f"💡 今日は既に日記があります。入力すると自動で合体して書き直します。\n\n**過去のメモ:**\n{previous_memo}")

user_input = st.text_area("出来事を入力（追記もOK！）", height=150)

# ===============================================
# 生成・保存処理
# ===============================================
if st.button("日記を作成する"):
    if not user_input:
        st.warning("内容を入力してください！")
    elif not worksheet:
        st.error("スプレッドシートに接続できません")
    else:
        client = OpenAI(api_key=api_key)

        # 🌟 合体ロジック: 過去メモ + 新しいメモ
        if previous_memo:
            combined_input = f"{previous_memo}\n\n【追記】\n{user_input}"
            system_instruction_add = "ユーザーは今日の日記に追記をしました。過去の分と新しい分を上手にまとめて、一つの自然な日記に書き直してください。"
        else:
            combined_input = user_input
            system_instruction_add = "ユーザーの箇条書きメモを、情緒ある日記に清書してください。"

        with st.spinner("AIが執筆＆お絵かき中...🎨"):
            try:
                # 1. テキスト生成 (GPT-4o-mini)
                # 画像生成用のプロンプトも同時に作らせるのがポイント
                system_prompt = f"""
                あなたはプロのライター兼心理カウンセラーです。
                {system_instruction_add}
                
                以下の処理を行い、指定の形式で出力してください。
                1. 【日記の清書】: 大人の情緒ある丁寧な日本語の日記にする。
                2. 【感情分析】: ポジティブ度（100点満点）と一言コメント。
                3. 【画像生成プロンプト】: この日記の内容を「小学生がクレヨンで描いたような絵日記」にするための、画像生成AI(DALL-E 3)への英語の指示を作成する。
                   (例: A children's crayon drawing of [シーンの説明], colorful, simple style on white paper.)

                出力形式は必ず以下のように厳密に従ってください：
                ---
                【清書された日記】
                (ここに清書された文章)

                【分析結果】
                📊 ポジティブ度: (点数)/100
                💬 コメント: (ここにコメント)

                【IMAGE_PROMPT】
                (ここに英語のプロンプト)
                ---
                """

                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": combined_input}
                    ]
                )
                
                result_text = response.choices[0].message.content
                
                # 結果の分割（表示用と画像生成用に分ける）
                # 万が一 IMAGE_PROMPT が生成されなかった場合のエラーハンドリング
                if "【IMAGE_PROMPT】" in result_text:
                    diary_part = result_text.split("【IMAGE_PROMPT】")[0].strip()
                    image_prompt_part = result_text.split("【IMAGE_PROMPT】")[1].strip()
                else:
                    diary_part = result_text
                    image_prompt_part = ""
                
                # テキスト結果表示
                st.markdown("### 📖 日記")
                st.info(diary_part)

                # 2. 画像生成 (DALL-E 3) 🌟新規追加
                image_url = ""
                if image_prompt_part:
                    try:
                        # プロンプトの調整（スタイルを強調）
                        final_image_prompt = f"{image_prompt_part}, children's drawing style, crayon art, naive art, colorful, simple, white background."
                        
                        img_response = client.images.generate(
                            model="dall-e-3",
                            prompt=final_image_prompt,
                            size="1024x1024",
                            quality="standard",
                            n=1,
                        )
                        image_url = img_response.data[0].url
                        st.image(image_url, caption="AI絵日記", use_column_width=True)
                    except Exception as img_e:
                        st.warning(f"画像生成に失敗しました: {img_e}")

                # 3. 保存処理
                today = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
                
                # 分析結果セクションの抽出
                if "【分析結果】" in diary_part:
                    analysis_section = diary_part.split("【分析結果】")[1].strip()
                else:
                    analysis_section = "N/A"
                
                # スプレッドシートに保存
                # E列に「画像URL」というヘッダーを追加しておいてください
                worksheet.append_row([
                    today,
                    combined_input, # 合体したメモを保存
                    diary_part,     # 清書結果
                    analysis_section,
                    image_url       # 🌟 画像URLも保存
                ])
                st.success("保存しました！")

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")

st.markdown("---")
# ===============================================
# 📚 過去の日記表示 (最新版を表示)
# ===============================================
st.header("📚 過去の日記")

if worksheet:
    try:
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)

        if not df.empty:
            df = df.iloc[::-1] # 新しい順
            
            for index, row in df.iterrows():
                # タイトル作成
                try:
                    date_part = str(row['日付']).split(' ')[0]
                    # 分析結果のパース
                    analysis = str(row['分析結果'])
                    score = "N/A"
                    if "ポジティブ度" in analysis:
                        score = analysis.split("ポジティブ度")[1].split("/")[0].replace(":", "").strip()
                    
                    with st.expander(f"🗓️ {date_part} - 気分: {score}"):
                        # 画像表示 (画像URL列が存在し、URLが入っている場合)
                        # get_all_recordsはスプレッドシートの1行目のヘッダー名を使います
                        if '画像URL' in row and str(row['画像URL']).startswith('http'):
                             st.image(row['画像URL'], caption="絵日記", width=300)
                        
                        # 日記本文
                        if "【清書された日記】" in str(row['生成結果']):
                            body = str(row['生成結果']).split("【清書された日記】")[1].split("【分析結果】")[0].strip()
                            st.write(body)
                        else:
                            st.write(row['生成結果'])
                        
                        st.caption(f"元のメモ: {row['元のメモ']}")
                        
                except Exception:
                    continue

    except Exception as e:
        st.error(f"データの読み込みに失敗しました: {e}")