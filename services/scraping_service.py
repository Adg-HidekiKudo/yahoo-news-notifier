# services/scraping_service.py
from __future__ import annotations

from bs4 import BeautifulSoup

from utils.http import get_text


BASE_DOMAIN = "https://news.yahoo.co.jp"


class ScrapingService:
    def __init__(self):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
            )
        }

    def get_latest_news(self, category: str):
        """カテゴリページから最新ニュースを取得"""
        url = f"{BASE_DOMAIN}/categories/{category}"

        try:
            html = get_text(url, headers=self.headers)
            soup = BeautifulSoup(html, "html.parser")

            for link in soup.select("a"):
                href = link.get("href", "")
                title = link.text.strip()

                if ("pickup" in href or "articles" in href) and len(title) > 10:
                    if href.startswith("/"):
                        href = f"{BASE_DOMAIN}{href}"
                    return {"title": title, "url": href, "category": category}

        except Exception as e:
            print(f"スクレイピング失敗: {e}")

        return None

    def fetch_body(self, url: str) -> str:
        """記事本文だけを取得"""
        return self.fetch_article(url)["body"]

    def fetch_article(self, url: str) -> dict:
        """記事本文とサムネイル候補を取得"""
        try:
            html = get_text(url, headers=self.headers)
            soup = BeautifulSoup(html, "html.parser")
            paragraphs = soup.find_all("p")
            body = "".join([p.text.strip() for p in paragraphs if len(p.text.strip()) > 10])
            return {
                "body": body[:1500],
                "thumbnail_url": self._extract_thumbnail_url(soup),
            }
        except Exception as e:
            print(f"本文取得失敗: {e}")
            return {"body": "", "thumbnail_url": None}

    def _extract_thumbnail_url(self, soup: BeautifulSoup) -> str | None:
        for selector in (
            'meta[property="og:image"]',
            'meta[name="twitter:image"]',
            'meta[property="twitter:image"]',
        ):
            tag = soup.select_one(selector)
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None
