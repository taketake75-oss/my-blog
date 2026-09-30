import os
import glob
from datetime import datetime
from google import genai
from dotenv import load_dotenv

# .env ファイルの環境変数を読み込む
load_dotenv()

# APIキー・各種ID設定（.env から安全に取得）
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def get_existing_slugs():
    """既存の記事ファイル名（slug）を取得して重複を防止する"""
    blog_dir = os.path.join(process_cwd_or_path(), "my-blog/src/content/blog/*.md")
    # my-blog直下にいる場合は src/content/blog/*.md
    if not glob.glob(blog_dir):
        blog_dir = "src/content/blog/*.md"
    
    files = glob.glob(blog_dir)
    slugs = [os.path.basename(f).replace(".md", "") for f in files]
    return slugs

def generate_keywords(count=3):
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    existing_slugs = get_existing_slugs()
    today_str = datetime.now().strftime("%Y-%m-%d")
    month_str = datetime.now().strftime("%m月")

    prompt = f"""
あなたはガジェット・家電・PC周辺機器専門のSEOアフィリエイトブロガーです。
楽天市場で検索・購入されやすい、現在（{month_str}）のトレンドや需要に合ったブログ記事のキーワード案を{count}件生成してください。

【制約事項】
1. 以下の既存記事ファイル名（アルファベット英単語ハイフン区切り）と重複しないテーマを選んでください。
既存記事: {", ".join(existing_slugs)}

2. 出力フォーマットは必ず以下のカンマ区切り形式（CSV/TXT形式）のみとし、余計な説明テキストやコードブロック（```）は出力しないでください。
形式: キーワード, src/content/blog/半角英数字ハイフン名.md

【出力例】
デスクライト LED おしゃれ, src/content/blog/desk-light-led-recommend.md
ワイヤレス充電器 3in1, src/content/blog/wireless-charger-3in1-best.md
"""

    models_to_try = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
    
    for model_name in models_to_try:
        try:
            print(f"🤖 Gemini ({model_name}) にキーワード選定を依頼中...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            text = response.text.strip()
            # バックトラック（```）などを除去
            lines = [line.strip() for line in text.split("\n") if line.strip() and "," in line and not line.startswith("```")]
            if lines:
                return lines
        except Exception as e:
            print(f"⚠️ {model_name} エラー: {e}")
            
    return []

def process_cwd_or_path():
    return os.cwd() if hasattr(os, 'cwd') else os.getcwd()

def main():
    print("==========================================")
    print("🎯 キーワード自動選定処理を開始します")
    print("==========================================")
    
    # 3件生成（件数は変更可能）
    keywords_lines = generate_keywords(count=3)
    
    if not keywords_lines:
        print("❌ キーワードの自動生成に失敗しました。")
        return

    output_file = "keywords.txt"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(keywords_lines) + "\n")
        
    print(f"\n✅ 『{output_file}』 に以下のキーワードを書き出しました:\n")
    for line in keywords_lines:
        print(f"  • {line}")
    print("\nあとは `python3 generate_article.py` を実行するだけです！")

if __name__ == "__main__":
    main()