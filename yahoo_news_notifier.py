import asyncio
import time

from config import load_config

# === 分離したサービス ===
from services.scraping_service import ScrapingService
from services.ai_service import AIService
from services.excel_service import ExcelService
from services.discord_service import DiscordService
from services.speech_service import SpeechService
from services.search_service import SearchService


def should_notify_article(
    title,
    body,
    keywords,
    semantic_interest,
    semantic_threshold,
    ai_service,
    search: SearchService,
    notify_all_when_no_filters=True
):
    title_lower = title.lower()
    body_lower = body.lower()

    # ============================
    # ① キーワード完全一致
    # ============================
    if keywords:
        for word in keywords:
            w = word.lower()
            if w in title_lower or w in body_lower:
                return True, f"keyword:{word}", 100

    # ============================
    # ② Fuzzy一致（曖昧一致）
    # ============================
    if keywords:
        for word in keywords:
            score = fuzz.partial_ratio(word.lower(), title_lower)
            if score >= 80:
                return True, f"fuzzy:{word}", score

    # ============================
    # ③ 全文検索（BM25）
    # ============================
    if keywords:
        for word in keywords:
            results = search.search(word, limit=1)
            if results:
                score, url, _ = results[0]
                if score >= 3.0:
                    return True, f"fulltext:{word}", score

    # ============================
    # ④ セマンティック一致（AIが使えるときだけ）
    # ============================
    if semantic_interest and ai_service and ai_service.ai_available:
        score = ai_service.semantic_score(semantic_interest, title, body)
        if score is not None and score >= semantic_threshold:
            return True, f"semantic:{semantic_interest}", score

    # ============================
    # ⑤ 条件なし通知（設定でONの場合）
    # ============================
    if notify_all_when_no_filters and not keywords and not semantic_interest:
        return True, "no_filter", None

    # ============================
    # ⑥ どれにも該当しない → 通知しない
    # ============================
    return False, None, None


async def analyze_article_async(ai_service, title, body):
    return await asyncio.to_thread(ai_service.analyze_article, title, body)


async def fetch_latest_async(scraper, category):
    """カテゴリ取得の非同期ラッパー（最重要）"""
    return category, await asyncio.to_thread(scraper.get_latest_news, category)


async def main():
    print("⚙️ 設定ファイルを読み込んでいます...")
    try:
        config = load_config()
    except Exception as e:
        print(f"❌ 設定の読み込みに失敗しました: {e}")
        return

    # === 設定値 ===
    webhook_url = config.DISCORD_WEBHOOK_URL
    categories = config.CATEGORY or []
    keywords = config.KEYWORDS
    api_key = config.GEMINI_API_KEY
    semantic_interest = config.SEMANTIC_INTEREST
    semantic_threshold = config.SEMANTIC_THRESHOLD
    check_interval = config.CHECK_INTERVAL

    notified_ai_limit = False

    if not webhook_url:
        print("❌ 設定ファイルに DISCORD_WEBHOOK_URL が指定されていません。")
        return

    # === サービス初期化 ===
    scraper = ScrapingService()
    ai_service = AIService(api_key) if api_key else None
    excel = ExcelService()
    discord = DiscordService()
    speaker = SpeechService()
    search = SearchService() 

    # === 現在の起動設定 ===
    print("\n========= 現在の起動設定 =========")
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

    if api_key:
        print("AI要約機能：有効")
    else:
        print("AI要約機能：無効（APIキー未設定）")

    print(f"パトロール時間間隔：{check_interval}秒ごと")
    print("==================================\n")

    print("📡 ニュースのパトロールを開始しました...")

    # === 初回チェック ===
    last_news = {c: None for c in categories}

    tasks = [fetch_latest_async(scraper, cat) for cat in categories]
    results = await asyncio.gather(*tasks)

    for cat, latest in results:
        if not latest:
            print(f"⚠️ 初回取得失敗: {cat}")
            continue

        title = latest["title"]
        url = latest["url"]

        if excel.is_duplicate(title):
            print(f"⏭️ [重複スキップ] ({cat}) {title}")
            last_news[cat] = title
            continue

        article = scraper.fetch_article(url)
        body = article["body"]
        latest["thumbnail_url"] = article.get("thumbnail_url")

        # ここで全文検索エンジンに登録
        search.add_article(title, body, url)

        # === AI呼び出し ===
        if ai_service and ai_service.ai_available:
            result = await analyze_article_async(ai_service, title, body)

            # 無料枠切れ判定
            if result is None:
                ai_service.ai_available = False

        # === AIなし処理（APIキーなし or 無料枠切れ） ===
        if not ai_service or not ai_service.ai_available:

            # 無料枠切れ通知（APIキーなしのときは通知しない）
            if ai_service and not ai_service.ai_available and not notified_ai_limit:
                print("⚠️ AI利用枠が上限に達しました。AI機能を停止します。")
                notified_ai_limit = True

            summary = None
            points = None
            importance = None

        else:
            summary = result.get("summary")
            points = "\n".join(result.get("points") or [])
            importance = result.get("importance")

        notify, hit_word, semantic_score = should_notify_article(
            title, body, keywords, semantic_interest, semantic_threshold, ai_service, search
        )

        mode_text = "総合・主要" if cat == "domestic" else cat

        if notify:
            discord.send(
                webhook_url,
                latest,
                is_test=True,
                summary=summary,
                points=points,
                score=semantic_score,
                importance=importance,
                category=mode_text
            )
            excel.write(mode_text, title, url, summary, importance)

            speech = f"起動しました。最新ニュース、{title}。"
            if summary:
                speech += summary.replace("・", "").replace("\n", "。")
            speaker.speak(speech)
        else:
            print(f"⏭️ [絞り込みスキップ] ({cat}) {title}")

        last_news[cat] = title

    # === 監視ループ ===
    while True:
        await asyncio.sleep(check_interval)

        tasks = [fetch_latest_async(scraper, cat) for cat in categories]
        results = await asyncio.gather(*tasks)

        for cat, current in results:
            if not current:
                continue

            title = current["title"]
            url = current["url"]

            if last_news.get(cat) == title:
                continue
            last_news[cat] = title

            if excel.is_duplicate(title):
                continue

            article = scraper.fetch_article(url)
            body = article["body"]
            current["thumbnail_url"] = article.get("thumbnail_url")

            if ai_service and ai_service.ai_available:
                result = await analyze_article_async(ai_service, title, body)
                summary = result.get("summary")
                points = "\n".join(result.get("points") or [])
                importance = result.get("importance")
            else:
                if ai_service and not ai_service.ai_available and not notified_ai_limit:
                    discord.send(
                        webhook_url,
                        {
                            "title": "AI機能が停止しました",
                            "url": "",
                            "thumbnail_url": None,
                            "category": "system"
                        },
                        summary="無料枠の上限に達したため、AI要約・重要ポイント抽出・重要度判定は停止しています。",
                        is_test=True
                    )
                    notified_ai_limit = True

                summary = None
                points = None
                importance = None

            notify, hit_word, semantic_score = should_notify_article(
                title, body, keywords, semantic_interest, semantic_threshold, ai_service, search
            )

            mode_text = "総合・主要" if cat == "domestic" else cat

            if notify:
                discord.send(
                    webhook_url,
                    current,
                    summary=summary,
                    points=points,
                    score=semantic_score,
                    hit_word=hit_word,
                    importance=importance,
                    category=mode_text
                )
                excel.write(mode_text, title, url, summary, importance)

                speech = f"新着ニュースです、{title}。"
                if summary:
                    speech += summary.replace("・", "").replace("\n", "。")
                speaker.speak(speech)
            else:
                print(f"⏭️ [絞り込みスキップ] ({cat}) {title}")


if __name__ == "__main__":
    asyncio.run(main())
