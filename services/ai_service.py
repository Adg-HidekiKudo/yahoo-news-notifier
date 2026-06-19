# services/ai_service.py
import time
import json
import re
from google import genai

class AIService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key)


    def _retry(self, func, *args, max_retries=8):
        for attempt in range(max_retries):
            try:
                return func(*args)
            except Exception as e:
                if "429" in str(e) or "503" in str(e):
                    wait = min(2 ** attempt * 2, 60)
                    print(f"⚠️ Gemini 一時エラー: {e} → {wait}秒待機")
                    time.sleep(wait)
                else:
                    print(f"❌ Gemini 永続エラー: {e}")
                    return None
        return None
    

    def analyze_article(self, title: str, body: str) -> dict:
        prompt = f"""
以下のニュース記事について、次の3つをまとめて生成してください。

1. 要約（3行）
2. 重要ポイント（5点、箇条書き）
3. 記事の重要度（0〜100）

必ず次の JSON 形式で返してください：

{{
    "summary": "...",
    "points": ["...", "...", "...", "...", "..."],
    "importance": 75
}}

タイトル: {title}

本文:
{body}
"""
        def _call():
            res = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            return res.text

        raw = self._retry(_call)
        if not raw:
            return {"summary": None, "points": None, "importance": None}
        
        # コードブロック除去
        clean = re.sub(r"^```[a-zA-Z]*|```$", "", raw.strip(), flags=re.MULTILINE).strip()

        try:
            return json.loads(clean)
        except Exception:
            print("JSONパース失敗:", clean)
            return {
                "summary": None,
                "points": None,
                "importance": None,
            }


    def semantic_score(self, interest: str, title: str, body: str):
        if not interest or not body:
            return None

        prompt = f"""
        以下の関心テーマと記事の関連度を0〜100で返してください。
        数字のみ出力。

        関心: {interest}
        タイトル: {title}
        本文: {body}
        """

        def _call():
            res = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            return res.text.strip()

        text = self._retry(_call)
        if not text:
            return None

        import re
        m = re.search(r"\b([0-9]{1,3})\b", text)
        if m:
            score = int(m.group(1))
            return score if 0 <= score <= 100 else None

        return None
