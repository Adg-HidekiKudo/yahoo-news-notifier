import os
import time
import requests
from datetime import datetime
from bs4 import BeautifulSoup
from google import genai
import openpyxl

# === 設定エリア ===
CONFIG_FILE = "config.txt"
EXCEL_FILE = "news_log.xlsx"
# ==================

def load_config():
    """config.txtから各種設定を読み込む"""
    # 設定の初期値を用意
    config = {
        "webhook_url": None,
        "category": "domestic",
        "keywords": [],
        "gemini_api_key": None,
        "check_interval": 60
    }
    
    # config.txt が存在しない場合はエラー
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ エラー: 設定ファイル '{CONFIG_FILE}' が見つかりません。")
        return None
        
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                    
                # 各種設定を読み込み
                if line.startswith("DISCORD_WEBHOOK_URL="):
                    config["webhook_url"] = line.split("=", 1)[1].strip()
                elif line.startswith("CATEGORY="):
                    val = line.split("=", 1)[1].strip()
                    if val:
                        config["category"] = val
                elif line.startswith("KEYWORDS="):
                    val = line.split("=", 1)[1].strip()
                    if val:
                        config["keywords"] = [k.strip() for k in val.split(",") if k.strip()]
                elif line.startswith("GEMINI_API_KEY="):
                    val = line.split("=", 1)[1].strip()
                    if val:
                        config["gemini_api_key"] = val
                elif line.startswith("CHECK_INTERVAL="):
                    val = line.split("=", 1)[1].strip()
                    if val and val.isdigit():
                        config["check_interval"] = int(val)
                    
        # Webhook URLが読み込めなかった（空欄、または項目自体がない）場合の明確なエラー文
        if not config["webhook_url"]:
            print(f"❌ エラー: '{CONFIG_FILE}' 内に DISCORD_WEBHOOK_URL の値が設定されていません。")
            # 起動時のコマンド入力で補完させるため、ここではNoneを返さず部分的なconfigをそのまま渡します
            return None
            
        return config
            
    except Exception as e:
        print(f"❌ 設定ファイルの読み込み中にエラーが発生しました: {e}")
        return None


def get_latest_news(category):
    """指定されたカテゴリのYahoo!ニュースから最新記事を取得する"""
    base_domain = "https://news.yahoo.co.jp"
    url = f"{base_domain}/categories/{category}"

    # Webアクセス用のUser-Agent を設定
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        
        # 記事リンクを探して最初に見つかったものを返す
        for link in soup.find_all("a"):
            href = link.get("href", "")
            title = link.text.strip()
            
            if ("pickup" in href or "articles" in href) and len(title) > 10:
                if href.startswith("/"):
                    href = f"{base_domain}{href}"
                return {"title": title, "url": href}
                
    except Exception as e:
        print(f"データ取得エラー: {e}")
    return None


def fetch_news_body(article_url):
    """ニュースのURLから本文テキストをスクレイピングして取得する"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    try:
        response = requests.get(article_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            paragraphs = soup.find_all("p")
            body_text = "".join([p.text.strip() for p in paragraphs if len(p.text.strip()) > 10])
            return body_text[:1500]
    except Exception as e:
        print(f"⚠️ 本文の取得に失敗しました: {e}")
    return ""


def summarize_with_gemini(api_key, title, body_text):
    """Gemini APIを使用して、ニュース本文を3行の箇架書きに要約する"""
    if not api_key or not body_text:
        return None
        
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"""
        以下のニュース記事の内容を読み、重要なポイントを3行のシンプルな箇条書き（各行の先頭は「・」）で要約してください。
        余計な挨拶や前置きは一切省き、要約文だけを出力してください。

        【タイトル】: {title}
        【本文】: {body_text}
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text.strip()
    except Exception as e:
        print(f"⚠️ Gemini要約エラー: {e}")
    return None


def write_to_excel(category, title, url, summary):
    """ニュースデータをExcelファイルに書き込む（追記保存）"""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    clean_summary = summary if summary else "要約なし"
    row_data = [now_str, category, title, url, clean_summary]
    
    try:
        if os.path.exists(EXCEL_FILE):
            wb = openpyxl.load_workbook(EXCEL_FILE)
            ws = wb.active
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "News Log"
            ws.append(["通知日時", "カテゴリ", "ニュースタイトル", "記事URL", "AI要約内容"])
            
        ws.append(row_data)
        wb.save(EXCEL_FILE)
        print(f"🗄️ Excelデータベースに記録しました: {title}")
    except Exception as e:
        print(f"⚠️ Excelへの書き込みに失敗しました: {e}")


def send_to_discord(webhook_url, news, is_test=False, hit_word=None, summary=None):
    """Discordにニュースを通知する"""
    if news is None:
        content = "📢 【システム通知】ニュースデータの読み込みに失敗しました。"
    else:
        if is_test:
            prefix = "📢 【起動テスト成功】\n"
        elif hit_word:
            prefix = f"🎯 【キーワード的中: {hit_word}】\n"
        else:
            prefix = "📰 【新着ニュース】\n"
            
        content = f"{prefix}**{news['title']}**\n{news['url']}"
        
        if summary:
            content += f"\n\n> 🤖 **AIによる3行要約:**\n> {summary.replace('\n', '\n> ')}"

    payload = {"content": content}
    
    try:
        response = requests.post(webhook_url, json=payload, timeout=10)
        if 200 <= response.status_code < 300:
            if news:
                print(f"✅ Discordへ通知しました: {news['title']}")
            else:
                print("✅ Discordへテスト通知を送信しました。")
        else:
            print(f"❌ Discord側が拒否しました (ステータスコード: {response.status_code})")
    except Exception as e:
        print(f"❌ 通信エラーが発生しました: {e}")


def main():
    print("⚙️ 設定ファイルを読み込んでいます...")
    config = load_config()
    
    if not config:
        print("❌ プログラムを起動できませんでした。")
        return

    webhook_url = config["webhook_url"]
    category = config["category"]
    keywords = config["keywords"]
    api_key = config["gemini_api_key"]
    check_interval = config["check_interval"]

    # === 【修正箇所】ご指摘の日本語レイアウトのみに書き換え ===
    print("\n========= 現在の起動設定 =========")
    
    mode_text = "総合・主要" if category == "domestic" else category
    print(f"カテゴリ：{mode_text}")
    
    if keywords:
        print(f"キーワード：{', '.join(keywords)}")
    else:
        print("キーワード：設定なし (すべての記事を通知)")
        
    ai_status = "有効" if api_key else "無効"
    print(f"AI要約機能：{ai_status}")
    
    print(f"パトロール時間間隔：{check_interval}秒ごと")
    print("==================================\n")
    # ========================================================

    print("📡 ニュースのパトロールを開始しました...")
    
    last_news = get_latest_news(category)
    if last_news:
        print(f"現在の最新記事を記憶しました: {last_news['title']}")
        
        body = fetch_news_body(last_news["url"])
        summary = summarize_with_gemini(api_key, last_news["title"], body)
        
        send_to_discord(webhook_url, last_news, is_test=True, summary=summary)
        write_to_excel(mode_text, last_news["title"], last_news["url"], summary)
    else:
        print("⚠️ 初回のニュース取得に失敗しました。次の回に再試行します。")
    
    while True:
        time.sleep(check_interval)
        current_news = get_latest_news(category)
        
        if current_news and (last_news is None or current_news["title"] != last_news["title"]):
            last_news = current_news
            
            body = fetch_news_body(current_news["url"])
            summary = summarize_with_gemini(api_key, current_news["title"], body)
            
            if not keywords:
                print("🆕 新しい記事を検知しました！")
                send_to_discord(webhook_url, current_news, summary=summary)
                write_to_excel(mode_text, current_news["title"], current_news["url"], summary)
            else:
                for word in keywords:
                    if word.lower() in current_news["title"].lower():
                        print(f"🎯 キーワード「{word}」にヒットする新着記事を検知！")
                        send_to_discord(webhook_url, current_news, hit_word=word, summary=summary)
                        write_to_excel(mode_text, current_news["title"], current_news["url"], summary)
                        break


if __name__ == "__main__":
    main()
