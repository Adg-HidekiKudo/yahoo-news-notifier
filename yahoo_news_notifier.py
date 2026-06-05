import time

from news_processor import (
    fetch_news_body,
    get_latest_news,
    load_config,
    send_to_discord,
    speak_text,
    summarize_with_gemini,
    write_to_excel,
)


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

    print("📡 ニュースのパトロールを開始しました...")
    
    last_news = get_latest_news(category)
    if last_news:
        print(f"現在の最新記事を記憶しました: {last_news['title']}")
        
        body = fetch_news_body(last_news["url"])
        summary = summarize_with_gemini(api_key, last_news["title"], body)
        
        send_to_discord(webhook_url, last_news, is_test=True, summary=summary)
        write_to_excel(mode_text, last_news["title"], last_news["url"], summary)
        
        speech_text = f"パトロールを開始しました。現在の最新ニュースです。{last_news['title']}。"
        if summary:
            clean_summary = summary.replace("・", "").replace("\n", "。")
            speech_text += f"、AIによる要約です。{clean_summary}"

        speak_text(speech_text)
    else:
        print("⚠️ 初回のニュース取得に失敗しました。次の回に再試行します。")
    
    while True:
        time.sleep(check_interval)
        current_news = get_latest_news(category)
        
        if current_news and (last_news is None or current_news["title"] != last_news["title"]):
            last_news = current_news
            
            body = fetch_news_body(current_news["url"])
            summary = summarize_with_gemini(api_key, current_news["title"], body)
            
            # === 音声読み上げ用テキストの組み立てロジック ===
            speech_text = f"新着ニュースです。{current_news['title']}。"
            if summary:
                # AIの箇条書きの「・」を「。」に置き換えて、聞き取りやすい自然な文章にする
                clean_summary = summary.replace("・", "").replace("\n", "。")
                speech_text += f"、AIによる要約です。{clean_summary}"
            # ========================================================
            
            if not keywords:
                print("🆕 新しい記事を検知しました！")
                send_to_discord(webhook_url, current_news, summary=summary)
                write_to_excel(mode_text, current_news["title"], current_news["url"], summary)
                speak_text(speech_text)
            else:
                for word in keywords:
                    if word.lower() in current_news["title"].lower():
                        print(f"🎯 キーワード「{word}」にヒットする新着記事を検知！")
                        send_to_discord(webhook_url, current_news, hit_word=word, summary=summary)
                        write_to_excel(mode_text, current_news["title"], current_news["url"], summary)
                        speak_text(speech_text)
                        break


if __name__ == "__main__":
    main()
