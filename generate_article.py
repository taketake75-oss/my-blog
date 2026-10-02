import os
import time
import csv
import warnings
import requests
import difflib
from datetime import datetime
from dotenv import load_dotenv

# .env ファイルの環境変数を読み込む
load_dotenv()

# Pythonバージョン等の不要な警告を非表示
warnings.filterwarnings('ignore')

from google import genai

# --------------------------------------------------
# APIキー・各種ID設定
# --------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

RAKUTEN_APP_ID = os.getenv("RAKUTEN_APP_ID")
RAKUTEN_ACCESS_KEY = os.getenv("RAKUTEN_ACCESS_KEY")
RAKUTEN_AFFILIATE_ID = os.getenv("RAKUTEN_AFFILIATE_ID")

RAKUTEN_SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"


# --------------------------------------------------
# 1-1. 類似商品判定・重複排除関数
# --------------------------------------------------
def is_similar_title(title1: str, title2: str, threshold: float = 0.55) -> bool:
    """商品名タイトルが似すぎているか判定する（同一商品の別ショップ出店を排除）"""
    t1 = "".join([c for c in title1 if c.isalnum()])
    t2 = "".join([c for c in title2 if c.isalnum()])
    ratio = difflib.SequenceMatcher(None, t1, t2).ratio()
    return ratio > threshold

def filter_unique_items(raw_items: list, target_count: int = 3) -> list:
    """楽天APIから取得したリストから重複・酷似している商品を排除する"""
    unique_items = []
    for item in raw_items:
        is_duplicate = False
        for u_item in unique_items:
            if is_similar_title(item["name"], u_item["name"]):
                is_duplicate = True
                break
        if not is_duplicate:
            unique_items.append(item)
        if len(unique_items) >= target_count:
            break
    return unique_items


# --------------------------------------------------
# 1-2. 楽天商品検索API関数
# --------------------------------------------------
def fetch_rakuten_items(keyword: str, hits: int = 3):
    time.sleep(1.0)

    # 類似除外を見越して少し多め(10件)に取得する
    params = {
        "applicationId": RAKUTEN_APP_ID,
        "accessKey": RAKUTEN_ACCESS_KEY,
        "affiliateId": RAKUTEN_AFFILIATE_ID,
        "keyword": keyword,
        "hits": 10,
        "format": "json",
    }

    try:
        res = requests.get(RAKUTEN_SEARCH_URL, params=params, timeout=10)
        if res.status_code != 200:
            return []

        data = res.json()
        raw_items = []
        for item_data in data.get("Items", []):
            item = item_data["Item"]
            raw_items.append({
                "name": item.get("itemName"),
                "price": item.get("itemPrice"),
                "affiliate_url": item.get("affiliateUrl"),
                "image_url": item.get("mediumImageUrls", [{}])[0].get("imageUrl"),
                "caption": item.get("itemCaption", "")[:150]
            })
        
        # 重複・類似商品をフィルタリングして上位3件を取り出す
        filtered_items = filter_unique_items(raw_items, target_count=hits)
        return filtered_items

    except Exception as e:
        print(f"楽天APIエラー: {e}")
        return []


# --------------------------------------------------
# 2. LLM文章生成関数（プロンプト強化版）
# --------------------------------------------------
def generate_article_markdown(keyword: str, items: list) -> str:
    client = genai.Client(api_key=GEMINI_API_KEY)

    products_context = ""
    for i, item in enumerate(items, 1):
        products_context += f"\n【商品{i}】: {item['name']}\n価格: {item['price']}円\n概要: {item['caption']}\n"

    today_str = datetime.now().strftime("%Y-%m-%d")

    prompt = f"""
以下の条件に従い、モバイル・ガジェット層に向けたブログ記事（Markdown形式）を執筆してください。

【検索キーワード】
{keyword}

【紹介する商品一覧データ】
{products_context}

【構成案・ルール】
1. 記事の先頭には必ず以下のAstro用のYAML Frontmatter（メタ情報）を含めて出力してください。
   ※categoryは「PC周辺機器」「オーディオ」「スマホアクセサリ」「生活家電」など適切なものを1つ設定してください。
---
title: "（読者の目を引く魅力的なタイトル）"
description: "（記事の概要を100文字程度で）"
pubDate: "{today_str}"
category: "（適切なカテゴリー名）"
---

2. 導入部分で読者の悩み（持ち運びや充電不足など）に共感してください。
3. 「選び方のポイント（箇条書き）」を簡潔に解説してください。
4. 各商品の解説パートでは、見出し（### ）に商品名を入れ、特徴やどんな人におすすめかを解説してください。
   【重要な比較指示】
   - 3つの商品は「コスパモデル」「多機能・上位モデル」「初心者・エントリーモデル」など、それぞれどのようなターゲットや場面に向いているかを明確に差別化して解説してください。
   - 機能や特徴が近い商品が含まれている場合は、無理にまったく別物として扱わず、「予算重視の方」「保証や付属品重視の方」など、読者にとって役立つ切り口で比較を行ってください。
5. 各商品の解説の末尾に、必ず以下のようにプレースホルダー（置き換え記号）を1行出力してください。
   - 商品1の末尾 -> [[PRODUCT_CARD_1]]
   - 商品2の末尾 -> [[PRODUCT_CARD_2]]
   - 商品3の末尾 -> [[PRODUCT_CARD_3]]
6. 最後に「まとめ」を書いて締めくくってください。
7. 余計な前置きを含めず、Markdownのテキストのみを出力してください。
"""

    models_to_try = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]

    for model_name in models_to_try:
        for attempt in range(1, 4):
            try:
                print(f"            -> モデル '{model_name}' で生成実行中... (試行 {attempt}/3)")
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )

                text_content = ""
                if hasattr(response, 'text') and response.text:
                    text_content = response.text
                elif hasattr(response, 'candidates') and response.candidates:
                    parts = response.candidates[0].content.parts
                    text_parts = [p.text for p in parts if hasattr(p, 'text') and p.text]
                    text_content = "".join(text_parts)

                if text_content:
                    return text_content

            except Exception as e:
                print(f"            ⚠️ '{model_name}' 応答エラー: {e}")
                if "503" in str(e) or "429" in str(e):
                    print("            ⌛ サーバー高負荷のため、15秒待機して再試行します...")
                    time.sleep(15)
                else:
                    time.sleep(3)

    raise RuntimeError("利用可能なすべてのGeminiモデルで応答を得られませんでした。")


# --------------------------------------------------
# 3. 商品カードHTML組み込み
# --------------------------------------------------
def build_product_card_html(item: dict) -> str:
    return f"""
<div style="border: 1px solid #e0e0e0; padding: 15px; border-radius: 8px; margin: 20px 0; display: flex; flex-wrap: wrap; gap: 15px; background: #fff; max-width: 100%; box-sizing: border-box;">
        <div style="flex-shrink: 0; margin: 0 auto;">
            <img src="{item['image_url']}" alt="{item['name']}" style="width: 120px; height: auto; border-radius: 4px; max-width: 100%;">
        </div>
        <div style="flex: 1; min-width: 200px; display: flex; flex-direction: column; justify-content: space-between;">
            <div style="font-weight: bold; font-size: 0.95em; color: #333; word-break: break-word;">{item['name']}</div>
            <div style="color: #bf0000; font-weight: bold; margin-top: 5px;">価格：{item['price']:,}円</div>
            <div style="margin-top: 10px;">
                <a href="{item['affiliate_url']}" target="_blank" rel="noopener sponsored" style="background: #bf0000; color: #fff; padding: 8px 16px; border-radius: 4px; text-decoration: none; font-size: 0.85em; display: inline-block;">楽天市場で見る</a>
            </div>
        </div>
</div>
"""


# --------------------------------------------------
# 4. 単一記事の処理
# --------------------------------------------------
def process_single_article(keyword: str, output_filename: str):
    print(f"\n==========================================")
    print(f"🚀 記事生成開始: [{keyword}]")
    print(f"==========================================")

    print(f"1. 楽天APIから「{keyword}」の商品情報を取得中（重複除外フィルタ適用）...")
    items = fetch_rakuten_items(keyword, hits=3)
    if not items:
        print("⚠️ スキップ: 商品データが取得できませんでした。キーワードを見直してください。")
        return
    print(f"            -> 取得成功: {len(items)} 件のユニーク商品データを取得しました。")

    print("2. Gemini APIで記事のMarkdown本文を生成中...")
    raw_markdown = generate_article_markdown(keyword, items)

    print("3. 商品カードHTMLをアフィリエイトリンク付きで埋め込み中...")
    final_markdown = raw_markdown
    for i, item in enumerate(items, 1):
        placeholder = f"[[PRODUCT_CARD_{i}]]"
        card_html = build_product_card_html(item)
        final_markdown = final_markdown.replace(placeholder, card_html)

    output_dir = os.path.dirname(output_filename)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    print(f"4. 結果を {output_filename} に保存中...")
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(final_markdown)

    print(f"🎉 完了しました！『{output_filename}』が出力されました。")


# --------------------------------------------------
# 5. メイン実行処理
# --------------------------------------------------
def main():
    param_file = "keywords.txt"
    if not os.path.exists(param_file):
        param_file = "keywords.csv"
        if not os.path.exists(param_file):
            print("❌ パラメータファイル（keywords.txt または keywords.csv）が見つかりません。")
            return

    print(f"📂 パラメータファイル 『{param_file}』 から設定を読み込みます...")

    with open(param_file, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row_num, row in enumerate(reader, 1):
            if not row or row[0].startswith("#"):
                continue

            if row[0].lower() in ["keyword", "キーワード"]:
                continue

            if len(row) >= 2:
                keyword = row[0].strip()
                output_path = row[1].strip()

                if os.path.exists(output_path):
                    print(f"\n⏩ スキップ: 『{output_path}』 は既に存在します。")
                    continue

                process_single_article(keyword, output_path)
                time.sleep(2)
            else:
                print(f"⚠️ {row_num}行目のフォーマットが不正です: {row}")

    print("\n✨ すべての処理が完了しました！")


if __name__ == "__main__":
    main()