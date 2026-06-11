import time

from news_processor import (
    fetch_news_body,
    get_latest_news,
    load_config,
    send_to_discord,
    speak_text,
    summarize_with_gemini,
    score_semantic_match,
    write_to_excel,
)


def should_notify_article(title, body, keywords, semantic_interest, semantic_threshold, api_key):
    """キーワードとセマンティック興味の両方で通知判定する"""
    if keywords:
        for word in keywords:
            if word.lower() in title.lower():
                return True, word, None

    if semantic_interest and api_key and body:
        score = score_semantic_match(api_key, semantic_interest, title, body)
        if score is not None and score >= semantic_threshold:
            return True, None, score

    # キーワードもセマンティック興味も指定されていない場合は全件通知
    if not keywords and not semantic_interest:
        return True, None, None

    return False, None, None


def main():
    print("⚙️ 設定ファイルを読み込んでいます...")
    config = load_config()

    if not config:
        print("❌ プログラムを起動できませんでした。")
        return

    webhook_url = config["webhook_url"]
    categories = config.get("categories") or []
    keywords = config["keywords"]
    api_key = config["gemini_api_key"]
    ai_summary_enabled = config.get("ai_summary_enabled", True)
    semantic_interest = config.get("semantic_interest")
    semantic_threshold = config.get("semantic_threshold", 80)
    check_interval = config["check_interval"]

    print("\n========= 現在の起動設定 =========")
    
    # カテゴリ表示（domestic は日本語表記へ変換）
    display_cats = ["総合・主要" if c == "domestic" else c for c in categories]
    print(f"カテゴリ：{', '.join(display_cats)}")
    
    if keywords:
        print(f"キーワード：{', '.join(keywords)}")
    else:
        print("キーワード：設定なし (すべての記事を通知)")

    gemini_status = "設定" if api_key else "未設定"
    print(f"GeminiAPIキー：{gemini_status}")

    if semantic_interest:
        print(f"セマンティック関心：{semantic_interest} (しきい値 {semantic_threshold})")
    else:
        print("セマンティック関心：無効")
        
    if ai_summary_enabled:
        if api_key:
            print("AI要約機能：有効")
        else:
            print("AI要約機能：有効（GeminiAPIキー未設定のため要約は実行されません）")
    else:
        print("AI要約機能：無効")
    
    print(f"パトロール時間間隔：{check_interval}秒ごと")
    print("==================================\n")

    print("📡 ニュースのパトロールを開始しました...")

    # 初回起動時のチェック: 各カテゴリごとに最新記事を取得して処理
    last_news = {c: None for c in categories}
    from news_processor import is_title_already_notified

    any_found = False
    for cat in categories:
        latest = get_latest_news(cat)
        if latest:
            any_found = True
            if is_title_already_notified(latest["title"]):
                print(f"⏭️  [重複スキップ] ({cat}) 過去ログにある既存の記事のため、通知・朗読をスキップします: {latest['title']}")
                last_news[cat] = latest["title"]
            else:
                mode_text = "総合・主要" if cat == "domestic" else cat
                print(f"🆕 初回の最新記事を検知しました ({cat}): {latest['title']}")
                body = fetch_news_body(latest["url"])
                summary = summarize_with_gemini(api_key, latest["title"], body) if ai_summary_enabled else None
                notify, hit_word, semantic_score = should_notify_article(
                    latest["title"],
                    body,
                    keywords,
                    semantic_interest,
                    semantic_threshold,
                    api_key,
                )
                if notify:
                    send_to_discord(
                        webhook_url,
                        latest,
                        is_test=True,
                        summary=summary,
                        semantic_score=semantic_score,
                    )
                    write_to_excel(mode_text, latest["title"], latest["url"], summary)
                    speech = f"起動しました。最新ニュース、{latest['title']}。"
                    if summary:
                        speech += (f"要約、{summary.replace('・', '').replace('\n', '。')}")
                    speak_text(speech)
                else:
                    print(f"⏭️  [絞り込みスキップ] ({cat}) セマンティック/キーワード条件に一致しませんでした: {latest['title']}")
                last_news[cat] = latest["title"]

    if not any_found:
        print("⚠️ 初回のニュース取得に失敗しました。次の回に再試行します。")

    # パトロールの無限ループ
    while True:
        time.sleep(check_interval)
        # 各カテゴリを順次チェックする（同期実装）
        for cat in categories:
            current_news = get_latest_news(cat)

            if current_news and (last_news.get(cat) is None or current_news["title"] != last_news.get(cat)):
                last_news[cat] = current_news["title"]

                # ここでも過去ログの重複を最終チェック（安全ガード）
                from news_processor import is_title_already_notified

                if is_title_already_notified(current_news["title"]):
                    continue

                body = fetch_news_body(current_news["url"])
                summary = summarize_with_gemini(api_key, current_news["title"], body) if ai_summary_enabled else None
                speech = f"新着ニュースです、{current_news['title']}。"
                if summary:
                    speech += f"要約、{summary.replace('・', '').replace('\n', '。')}"

                mode_text = "総合・主要" if cat == "domestic" else cat
                notify, hit_word, semantic_score = should_notify_article(
                    current_news["title"],
                    body,
                    keywords,
                    semantic_interest,
                    semantic_threshold,
                    api_key,
                )

                if notify:
                    if hit_word:
                        print(f"🎯 キーワード「{hit_word}」にヒット ({cat}): {current_news['title']}")
                    elif semantic_interest and semantic_score is not None:
                        print(f"🔎 セマンティック一致度 {semantic_score}/100 で通知 ({cat}): {current_news['title']}")
                    else:
                        print(f"🆕 新着記事を検知しました ({cat}): {current_news['title']}")

                    send_to_discord(
                        webhook_url,
                        current_news,
                        hit_word=hit_word,
                        summary=summary,
                        semantic_score=semantic_score,
                    )
                    write_to_excel(
                        mode_text,
                        current_news["title"],
                        current_news["url"],
                        summary,
                    )
                    speak_text(speech)
                else:
                    print(f"⏭️  [絞り込みスキップ] ({cat}) 記事は関心条件に一致しませんでした: {current_news['title']}")


if __name__ == "__main__":
    main()
