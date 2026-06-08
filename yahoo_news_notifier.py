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

    # 初回起動時のチェック
    last_news = get_latest_news(category)
    if last_news:
        # Excelの過去ログをチェックして重複を防止
        from news_processor import is_title_already_notified

        if is_title_already_notified(last_news["title"]):
            print(f"⏭️  [重複スキップ] 過去ログにある既存の記事のため、通知・朗読をスキップします: {last_news['title']}")
        else:
            print(f"🆕 初回の最新記事を検知しました: {last_news['title']}")
            body = fetch_news_body(last_news["url"])
            summary = summarize_with_gemini(api_key, last_news["title"], body)
            send_to_discord(webhook_url, last_news, is_test=True, summary=summary)
            write_to_excel(mode_text, last_news["title"], last_news["url"], summary)
            speech = f"起動しました。最新ニュース、{last_news['title']}。"
            if summary:
                speech += (f"要約、{summary.replace('・', '').replace('\n', '。')}")
            speak_text(speech)
    else:
        print("⚠️ 初回のニュース取得に失敗しました。次の回に再試行します。")

    # パトロールの無限ループ
    while True:
        time.sleep(check_interval)
        current_news = get_latest_news(category)

        if current_news and (last_news is None or current_news["title"] != last_news["title"]):
            last_news = current_news

            # ここでも過去ログの重複を最終チェック（安全ガード）
            from news_processor import is_title_already_notified

            if is_title_already_notified(current_news["title"]):
                continue

            body = fetch_news_body(current_news["url"])
            summary = summarize_with_gemini(api_key, current_news["title"], body)
            speech = f"新着ニュースです、{current_news['title']}。"
            if summary:
                speech += f"要約、{summary.replace('・', '').replace('\n', '。')}"

            if not keywords:
                print(f"🆕 新着記事を検知しました: {current_news['title']}")
                send_to_discord(webhook_url, current_news, summary=summary)
                write_to_excel(
                    mode_text,
                    current_news["title"],
                    current_news["url"],
                    summary,
                )
                speak_text(speech)
            else:
                for word in keywords:
                    if word.lower() in current_news["title"].lower():
                        print(f"🎯 キーワード「{word}」にヒット: {current_news['title']}")
                        send_to_discord(
                            webhook_url,
                            current_news,
                            hit_word=word,
                            summary=summary,
                        )
                        write_to_excel(
                            mode_text,
                            current_news["title"],
                            current_news["url"],
                            summary,
                        )
                        speak_text(speech)
                        break


if __name__ == "__main__":
    main()
