# services/discord_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from utils.http import get_client


CATEGORY_COLORS = {
    "domestic": 0x2F80ED,
    "総合・主要": 0x2F80ED,
    "world": 0x9B51E0,
    "business": 0xF2994A,
    "it": 0x00A3A3,
    "science": 0x27AE60,
    "entertainment": 0xEB5757,
    "sports": 0x219653,
    "local": 0x56CCF2,
}

DEFAULT_COLOR = 0x5865F2
MAX_DESCRIPTION_LENGTH = 900
MAX_FIELD_LENGTH = 1024
MAX_TITLE_LENGTH = 256


def _truncate(value: Any, limit: int) -> str:
    text = "" if value is None else str(value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _score_text(value: int | None) -> str:
    return "-" if value is None else f"{value}/100"


def _category_color(category: str | None) -> int:
    if not category:
        return DEFAULT_COLOR
    return CATEGORY_COLORS.get(category, DEFAULT_COLOR)


class DiscordService:
    def send(
        self,
        webhook_url,
        news,
        summary=None,
        points=None,
        score=None,
        hit_word=None,
        importance=None,
        is_test=False,
        category=None,
    ):
        if news is None:
            payload = {"content": "システムエラー: ニュース取得に失敗しました。"}
        else:
            payload = self._build_embed_payload(
                news=news,
                summary=summary,
                points=points,
                score=score,
                hit_word=hit_word,
                importance=importance,
                is_test=is_test,
                category=category,
            )

        try:
            client = get_client()
            client.post_json(webhook_url, payload)
        except Exception as e:
            print(f"Discord送信失敗: {e}")

    def _build_embed_payload(
        self,
        news,
        summary=None,
        points=None,
        score=None,
        hit_word=None,
        importance=None,
        is_test=False,
        category=None,
    ):
        title = _truncate(news.get("title", "ニュース"), MAX_TITLE_LENGTH)
        url = news.get("url", "")
        thumbnail_url = news.get("thumbnail_url")
        category_name = category or news.get("category") or "-"

        if is_test:
            headline = "起動テスト"
        elif hit_word:
            headline = "キーワード一致"
        elif score is not None:
            headline = "関連度一致"
        else:
            headline = "新着ニュース"

        if hit_word:
            reason = f"キーワード: {hit_word}"
        elif score is not None:
            reason = f"関連度スコア: {score}/100"
        elif is_test:
            reason = "起動時の初回通知"
        else:
            reason = "新着記事を検知"

        embed = {
            "title": title,
            "url": url,
            "description": f"🧩 **AI要約（3行）**\n{_truncate(summary or 'AI要約はありません。', MAX_DESCRIPTION_LENGTH)}",
            "color": _category_color(category_name),
            "author": {"name": headline},
            "fields": [
                {"name": "カテゴリ", "value": _truncate(category_name, MAX_FIELD_LENGTH), "inline": True},
                {"name": "重要度", "value": _score_text(importance), "inline": True},
                {"name": "📝 重要ポイント（5点）", "value": points, "inline": False},
                {"name": "関連度", "value": _score_text(score), "inline": True},
                {"name": "通知理由", "value": _truncate(reason, MAX_FIELD_LENGTH), "inline": False},
            ],
            "footer": {"text": "Yahoo! News Notifier"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if isinstance(thumbnail_url, str) and thumbnail_url.startswith(("http://", "https://")):
            embed["thumbnail"] = {"url": thumbnail_url}

        return {"content": "", "embeds": [embed]}
