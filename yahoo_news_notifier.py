import asyncio
import time

from config import load_config

# === 分離したサービス ===
from services.scraping_service import ScrapingService
from services.ai_service import AIService
from services.excel_service import ExcelService
from services.discord_service import DiscordService
from services.speech_service import SpeechService


def should_notify_article(title, body, keywords, semantic_interest, semantic_threshold, ai_service):
    """キーワード or セマンティック一致で通知判定"""
    # キーワード一致
    if keywords:
        for word in keywords:
            if word.lower() in title.lower():
                return True, word, None

    # セマンティック一致
    if semantic_interest and ai_service and body:
        score = ai_service.semantic_score(semantic_interest, title, body)
        if score is not None and score >= semantic_threshold:
            return True, None, score

    # 条件なし → 全件通知
    if not keywords and not semantic_interest:
        return True, None, None

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

    if not webhook_url:
        print("❌ 設定ファイルに DISCORD_WEBHOOK_URL が指定されていません。")
        return

    # === サービス初期化 ===
    scraper = ScrapingService()
    ai_service = AIService(api_key) if api_key else None
    excel = ExcelService()
    discord = DiscordService()
    speaker = SpeechService()

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
        print("AI要約機能：有効（GeminiAPIキー未設定のため要約は実行されません）")

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

        result = await analyze_article_async(ai_service, title, body)
        summary = result.get("summary")
        points = "\n".join(result.get("points") or [])
        importance = result.get("importance")

        notify, hit_word, semantic_score = should_notify_article(
            title, body, keywords, semantic_interest, semantic_threshold, ai_service
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

            result = await analyze_article_async(ai_service, title, body)
            summary = result.get("summary")
            points = "\n".join(result.get("points") or [])
            importance = result.get("importance")

            notify, hit_word, semantic_score = should_notify_article(
                title, body, keywords, semantic_interest, semantic_threshold, ai_service
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
