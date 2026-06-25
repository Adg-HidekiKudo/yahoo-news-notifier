# services/search_service.py
from __future__ import annotations

import math
import re
from collections import defaultdict
from typing import List, Dict, Tuple


WORD_RE = re.compile(r"[一-龠ぁ-んァ-ンA-Za-z0-9]+")


def tokenize(text: str) -> List[str]:
    if not text:
        return []
    return WORD_RE.findall(text.lower())


class SearchService:
    """
    超軽量・純Python全文検索エンジン

    - add_article(title, body, url)
    - search(query, limit=5) -> List[(score, url, title)]
    """

    def __init__(self):
        # doc_id -> {"title": str, "body": str}
        self.docs: Dict[str, Dict[str, str]] = {}

        # term -> {doc_id: tf}
        self.term_freqs: Dict[str, Dict[str, int]] = defaultdict(dict)

        # doc_id -> doc_len
        self.doc_lens: Dict[str, int] = {}

        # キャッシュ
        self._total_docs: int = 0

    def add_article(self, title: str, body: str, url: str):
        """記事をインデックスに追加 or 更新"""
        if not url:
            return

        text = f"{title}\n{body}"
        tokens = tokenize(text)
        if not tokens:
            return

        self.docs[url] = {"title": title, "body": body}
        self.doc_lens[url] = len(tokens)
        self._total_docs = len(self.docs)

        # 既存の term_freqs からこの doc を一旦削除（更新対応）
        for term, posting in self.term_freqs.items():
            if url in posting:
                del posting[url]

        # 再登録
        tf: Dict[str, int] = defaultdict(int)
        for t in tokens:
            tf[t] += 1

        for term, count in tf.items():
            self.term_freqs[term][url] = count

    def _idf(self, term: str) -> float:
        df = len(self.term_freqs.get(term, {}))
        if df == 0 or self._total_docs == 0:
            return 0.0
        return math.log((self._total_docs + 1) / (df + 0.5))

    def search(self, query: str, limit: int = 5) -> List[Tuple[float, str, str]]:
        """
        クエリ文字列に対して関連度の高い記事を返す
        戻り値: [(score, url, title), ...]
        """
        tokens = tokenize(query)
        if not tokens or self._total_docs == 0:
            return []

        scores: Dict[str, float] = defaultdict(float)

        for term in tokens:
            posting = self.term_freqs.get(term)
            if not posting:
                continue

            idf = self._idf(term)
            for doc_id, tf in posting.items():
                # 単純な tf * idf
                scores[doc_id] += tf * idf

        # タイトル・本文の部分一致ボーナス
        for doc_id, meta in self.docs.items():
            title = meta["title"]
            body = meta["body"]
            bonus = 0.0
            for term in tokens:
                if term in title.lower():
                    bonus += 1.5
                elif term in body.lower():
                    bonus += 0.5
            scores[doc_id] += bonus

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        result: List[Tuple[float, str, str]] = []
        for doc_id, score in ranked[:limit]:
            result.append((score, doc_id, self.docs[doc_id]["title"]))
        return result
