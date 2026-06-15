# services/discord_service.py
from utils.http import get_client, HTTPError

class DiscordService:
    def send(self, webhook_url, news, summary=None, score=None, hit_word=None, importance=None, is_test=False):
        if news is None:
            content = "📢 システムエラー: ニュース取得に失敗しました。"
        else:
            prefix = (
                "📢 【起動テスト】\n" if is_test else
                f"🎯 【キーワード一致: {hit_word}】\n" if hit_word else
                "📰 【新着ニュース】\n"
            )

            content = f"{prefix}**{news['title']}**\n{news['url']}"

            if summary:
                content += f"\n\n> 🤖 要約:\n> {summary.replace('\n', '\n> ')}"

            if score is not None:
                content += f"\n\n> 🔎 関連度: {score}/100"

            if importance is not None:
                content += f"\n\n> 🟥 重要度: {importance}/100"

        try:
            client = get_client()
            client.post_json(webhook_url, {"content": content})
        except Exception as e:
            print(f"❌ Discord送信失敗: {e}")
