"""
全サービス統合テスト
目的:
- 各サービスの基本動作確認
- 依存関係の連携確認
- 実運用前の安全な総合テスト
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from services.ai_service import AIService
from services.discord_service import DiscordService
from services.excel_service import ExcelService
from services.scraping_service import ScrapingService
from services.speech_service import SpeechService


def test_all_services():
    print("=== 総合テスト開始 ===")

    # 1️⃣ スクレイピングテスト
    scraper = ScrapingService()
    news = scraper.get_latest_news("domestic")
    if news:
        print(f"📰 スクレイピング成功: {news['title']}")
        body = scraper.fetch_body(news["url"])
        print(f"本文取得文字数: {len(body)}")
    else:
        print("⚠️ スクレイピング失敗（ネットワークまたは構造変更）")
        news = {"title": "テスト記事", "url": "https://example.com"}
        body = "これはテスト用の本文です。"

    # 2️⃣ AI 要約テスト（Gemini APIキーは環境変数から取得）
    ai = AIService(api_key="DUMMY_KEY")  # 実運用時は本物のキーを設定
    summary = ai.summarize(news["title"], body)
    score = ai.semantic_score("テクノロジー", news["title"], body)
    print(f"🤖 要約結果: {summary}")
    print(f"🔎 セマンティックスコア: {score}")

    # 3️⃣ Excel 書き込みテスト
    excel = ExcelService("test_news_log.xlsx")
    excel.write("domestic", news["title"], news["url"], summary)
    print(f"🗄️ Excel 書き込み完了: {news['title']}")
    print(f"重複チェック結果: {excel.is_duplicate(news['title'])}")

    # 4️⃣ Discord 通知テスト（モック送信）
    discord = DiscordService()
    print("📢 Discord 通知テスト（モック）")
    discord.send(
        webhook_url="https://example.com/webhook",
        news=news,
        summary=summary,
        score=score,
        is_test=True
    )

    # 5️⃣ 音声読み上げテスト
    speaker = SpeechService()
    speaker.speak(f"テスト完了。記事タイトルは {news['title']} です。")

    print("✅ 総合テスト完了！")


if __name__ == "__main__":
    test_all_services()
