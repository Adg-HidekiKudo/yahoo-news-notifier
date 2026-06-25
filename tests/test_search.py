# test_search.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from services.search_service import SearchService
from rapidfuzz import fuzz

# ===== テスト用のミニ記事データセット =====
test_articles = [
    {
        "title": "Appleが新型iPhoneを発表",
        "body": "最新のA18チップを搭載し、カメラ性能が大幅に向上した。",
        "url": "1"
    },
    {
        "title": "地震で震度5強、津波の心配なし",
        "body": "午前3時ごろ大きな揺れを観測。気象庁が注意を呼びかけている。",
        "url": "2"
    },
    {
        "title": "AI技術が医療分野で急速に進化",
        "body": "生成AIが診断支援に活用され始めている。",
        "url": "3"
    },
    {
        "title": "政府が新たな経済政策を検討",
        "body": "財政出動を含む複数の案が議論されている。",
        "url": "4"
    }
]

# ===== 全文検索エンジン初期化 =====
search = SearchService()

# ===== 記事を全文検索エンジンに登録 =====
for a in test_articles:
    search.add_article(a["title"], a["body"], a["url"])

# ===== テストしたいクエリ =====
queries = ["地震", "iPhone", "AI", "経済政策", "揺れ", "生成モデル"]

for q in queries:
    print(f"\n=== Query: {q} ===")

    # --- BM25全文検索 ---
    results = search.search(q, limit=5)
    for score, url, title in results:
        print(f"[BM25] {score:.2f}  {title}")

    # --- Fuzzy一致 ---
    for a in test_articles:
        sim = fuzz.partial_ratio(q.lower(), a["title"].lower())
        if sim >= 50:
            print(f"[Fuzzy] {sim}  {a['title']}")
