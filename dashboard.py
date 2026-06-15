from __future__ import annotations

import argparse
import html
import socket
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_EXCEL_FILE = BASE_DIR / "news_log.xlsx"

CANONICAL_COLUMNS = [
    "通知日時",
    "カテゴリ",
    "ニュースタイトル",
    "記事URL",
    "AI要約内容",
    "重要度スコア",
]


def _safe_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _parse_datetime(value: Any):
    try:
        return pd.to_datetime(value, errors="coerce")
    except Exception:
        return pd.NaT


def _load_news_log(excel_file: Path) -> pd.DataFrame:
    if not excel_file.exists():
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    try:
        df = pd.read_excel(excel_file, sheet_name="News Log")
    except ValueError:
        df = pd.read_excel(excel_file, sheet_name=0)
    except Exception:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    # Current files use Japanese headers. Some older generated files may have
    # mojibake headers, so fall back to positional names for the known layout.
    if not set(CANONICAL_COLUMNS[:4]).issubset(set(df.columns)) and len(df.columns) >= 6:
        df = df.iloc[:, :6].copy()
        df.columns = CANONICAL_COLUMNS

    for column in CANONICAL_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    df = df[CANONICAL_COLUMNS].copy()
    df["通知日時"] = df["通知日時"].apply(_parse_datetime)
    df["重要度スコア"] = df["重要度スコア"].apply(lambda v: _safe_int(v, 0))
    return df.dropna(how="all")


def _apply_filters(df: pd.DataFrame, params: dict[str, list[str]]) -> pd.DataFrame:
    filtered = df.copy()
    query = _param(params, "q")
    category = _param(params, "category")
    min_score = _safe_int(_param(params, "min_score"), 0)
    date_from = _param(params, "date_from")
    date_to = _param(params, "date_to")

    if query:
        lower_query = query.lower()
        mask = (
            filtered["ニュースタイトル"].astype(str).str.lower().str.contains(lower_query, na=False)
            | filtered["AI要約内容"].astype(str).str.lower().str.contains(lower_query, na=False)
            | filtered["カテゴリ"].astype(str).str.lower().str.contains(lower_query, na=False)
        )
        filtered = filtered[mask]

    if category:
        filtered = filtered[filtered["カテゴリ"].astype(str) == category]

    if min_score:
        filtered = filtered[filtered["重要度スコア"] >= min_score]

    if date_from:
        start = pd.to_datetime(date_from, errors="coerce")
        if not pd.isna(start):
            filtered = filtered[filtered["通知日時"] >= start]

    if date_to:
        end = pd.to_datetime(date_to, errors="coerce")
        if not pd.isna(end):
            filtered = filtered[filtered["通知日時"] < end + pd.Timedelta(days=1)]

    sort = _param(params, "sort") or "newest"
    if sort == "score":
        filtered = filtered.sort_values(["重要度スコア", "通知日時"], ascending=[False, False])
    else:
        filtered = filtered.sort_values("通知日時", ascending=False)

    return filtered


def _param(params: dict[str, list[str]], key: str, default: str = "") -> str:
    values = params.get(key)
    return values[0].strip() if values else default


def _build_url(params: dict[str, list[str]], **updates: str) -> str:
    flat = {key: values[0] for key, values in params.items() if values and values[0]}
    for key, value in updates.items():
        if value:
            flat[key] = value
        elif key in flat:
            del flat[key]
    query = urlencode(flat)
    return f"/?{query}" if query else "/"


def _score_class(score: int) -> str:
    if score >= 80:
        return "score-high"
    if score >= 50:
        return "score-mid"
    return "score-low"


def _render_bar_chart(series: pd.Series, params: dict[str, list[str]]) -> str:
    if series.empty:
        return '<p class="muted">データがありません。</p>'

    max_count = max(int(series.max()), 1)
    rows = []
    for label, count in series.items():
        width = int((int(count) / max_count) * 100)
        href = _build_url(params, category=str(label))
        rows.append(
            f"""
            <a class="bar-row" href="{html.escape(href)}">
              <span class="bar-label">{html.escape(str(label))}</span>
              <span class="bar-track"><span class="bar-fill" style="width:{width}%"></span></span>
              <span class="bar-count">{int(count)}</span>
            </a>
            """
        )
    return "\n".join(rows)


def _render_score_histogram(df: pd.DataFrame) -> str:
    if df.empty:
        return '<p class="muted">データがありません。</p>'

    bins = [(0, 39), (40, 59), (60, 79), (80, 100)]
    labels = ["0-39", "40-59", "60-79", "80-100"]
    counts = []
    for start, end in bins:
        counts.append(int(((df["重要度スコア"] >= start) & (df["重要度スコア"] <= end)).sum()))

    max_count = max(max(counts), 1)
    bars = []
    for label, count in zip(labels, counts):
        height = max(8, int((count / max_count) * 130)) if count else 8
        bars.append(
            f"""
            <div class="hist-bar">
              <div class="hist-value">{count}</div>
              <div class="hist-fill" style="height:{height}px"></div>
              <div class="hist-label">{label}</div>
            </div>
            """
        )
    return f'<div class="histogram">{"".join(bars)}</div>'


def _render_cards(df: pd.DataFrame) -> str:
    if df.empty:
        return '<section class="empty">該当するニュースはありません。</section>'

    cards = []
    for _, row in df.head(80).iterrows():
        title = html.escape(_safe_text(row["ニュースタイトル"]))
        category = html.escape(_safe_text(row["カテゴリ"]))
        url = html.escape(_safe_text(row["記事URL"]))
        summary = html.escape(_safe_text(row["AI要約内容"])).replace("\n", "<br>")
        score = _safe_int(row["重要度スコア"])
        notified_at = row["通知日時"]
        if pd.isna(notified_at):
            date_text = ""
        else:
            date_text = html.escape(notified_at.strftime("%Y-%m-%d %H:%M"))

        cards.append(
            f"""
            <article class="news-card">
              <div class="card-topline">
                <span class="pill">{category}</span>
                <span class="date">{date_text}</span>
                <span class="score-pill {_score_class(score)}">{score}</span>
              </div>
              <h2><a href="{url}" target="_blank" rel="noreferrer">{title}</a></h2>
              <p>{summary or "要約はありません。"}</p>
            </article>
            """
        )
    return "\n".join(cards)


def _render_page(excel_file: Path, params: dict[str, list[str]]) -> bytes:
    df = _load_news_log(excel_file)
    filtered = _apply_filters(df, params)
    categories = sorted(_safe_text(v) for v in df["カテゴリ"].dropna().unique() if _safe_text(v))

    total = len(df)
    shown = len(filtered)
    average_score = round(float(filtered["重要度スコア"].mean()), 1) if shown else 0
    high_count = int((filtered["重要度スコア"] >= 80).sum()) if shown else 0
    latest = filtered["通知日時"].max() if shown else pd.NaT
    latest_text = latest.strftime("%Y-%m-%d %H:%M") if not pd.isna(latest) else "-"

    q = html.escape(_param(params, "q"))
    current_category = _param(params, "category")
    min_score = html.escape(_param(params, "min_score", "0") or "0")
    date_from = html.escape(_param(params, "date_from"))
    date_to = html.escape(_param(params, "date_to"))
    sort = _param(params, "sort") or "newest"

    category_options = ['<option value="">すべて</option>']
    for category in categories:
        selected = " selected" if category == current_category else ""
        category_options.append(
            f'<option value="{html.escape(category)}"{selected}>{html.escape(category)}</option>'
        )

    sort_options = {
        "newest": "新しい順",
        "score": "重要度順",
    }
    sort_html = "".join(
        f'<option value="{key}"{" selected" if key == sort else ""}>{label}</option>'
        for key, label in sort_options.items()
    )

    category_counts = filtered["カテゴリ"].value_counts()
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    excel_status = html.escape(str(excel_file))

    page = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="60">
  <title>Yahoo! News Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7f9;
      --panel: #ffffff;
      --ink: #20262e;
      --muted: #687484;
      --line: #dce3ea;
      --accent: #0f766e;
      --accent-2: #2563eb;
      --warn: #b45309;
      --danger: #b91c1c;
      --ok: #15803d;
      --shadow: 0 10px 24px rgba(31, 41, 55, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Segoe UI", "Yu Gothic UI", "Meiryo", sans-serif;
      line-height: 1.55;
    }}
    header {{
      background: #16202a;
      color: white;
      padding: 22px 28px 18px;
      border-bottom: 4px solid var(--accent);
    }}
    .header-inner {{
      max-width: 1180px;
      margin: 0 auto;
      display: flex;
      justify-content: space-between;
      gap: 20px;
      align-items: end;
    }}
    h1 {{
      margin: 0;
      font-size: 26px;
      font-weight: 700;
    }}
    .sub {{
      margin-top: 4px;
      color: #c7d2de;
      font-size: 13px;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 22px 20px 40px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }}
    .metric, .panel, .news-card, .empty {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
    }}
    .metric {{
      padding: 16px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
    }}
    .metric strong {{
      display: block;
      margin-top: 4px;
      font-size: 24px;
    }}
    form.filters {{
      display: grid;
      grid-template-columns: 1.5fr 1fr 0.8fr 0.9fr 0.9fr 0.8fr auto;
      gap: 10px;
      align-items: end;
      margin-bottom: 18px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      box-shadow: var(--shadow);
    }}
    label {{
      display: grid;
      gap: 5px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
    }}
    input, select, button {{
      min-height: 38px;
      border: 1px solid #cbd5df;
      border-radius: 6px;
      padding: 8px 10px;
      font: inherit;
      background: white;
      color: var(--ink);
    }}
    button {{
      border-color: var(--accent);
      background: var(--accent);
      color: white;
      cursor: pointer;
      font-weight: 700;
      padding-inline: 16px;
    }}
    .clear-link {{
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      color: var(--accent-2);
      text-decoration: none;
      font-weight: 700;
      white-space: nowrap;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 0.9fr 1.1fr;
      gap: 16px;
      margin-bottom: 18px;
    }}
    .panel {{
      padding: 16px;
      min-height: 220px;
    }}
    .panel h2 {{
      margin: 0 0 14px;
      font-size: 17px;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 110px 1fr 44px;
      gap: 10px;
      align-items: center;
      color: inherit;
      text-decoration: none;
      padding: 7px 0;
      border-bottom: 1px solid #edf1f5;
    }}
    .bar-row:last-child {{ border-bottom: 0; }}
    .bar-label {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      color: var(--muted);
      font-size: 13px;
    }}
    .bar-track {{
      height: 11px;
      background: #e8eef3;
      border-radius: 999px;
      overflow: hidden;
    }}
    .bar-fill {{
      display: block;
      height: 100%;
      background: var(--accent-2);
      border-radius: 999px;
    }}
    .bar-count {{
      color: var(--muted);
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}
    .histogram {{
      height: 174px;
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      align-items: end;
      padding-top: 12px;
    }}
    .hist-bar {{
      display: grid;
      justify-items: center;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
    }}
    .hist-fill {{
      width: 100%;
      max-width: 58px;
      background: var(--accent);
      border-radius: 6px 6px 0 0;
    }}
    .hist-value {{
      font-weight: 700;
      color: var(--ink);
    }}
    .news-list {{
      display: grid;
      gap: 12px;
    }}
    .news-card {{
      padding: 16px;
    }}
    .card-topline {{
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }}
    .pill, .score-pill {{
      display: inline-flex;
      align-items: center;
      min-height: 24px;
      border-radius: 999px;
      padding: 3px 9px;
      font-size: 12px;
      font-weight: 700;
    }}
    .pill {{
      background: #e6f3f1;
      color: #0f5e58;
    }}
    .score-pill {{
      margin-left: auto;
      color: white;
      font-variant-numeric: tabular-nums;
    }}
    .score-low {{ background: var(--ok); }}
    .score-mid {{ background: var(--warn); }}
    .score-high {{ background: var(--danger); }}
    .date {{
      color: var(--muted);
      font-size: 12px;
    }}
    .news-card h2 {{
      margin: 0 0 8px;
      font-size: 18px;
      line-height: 1.4;
    }}
    .news-card a {{
      color: var(--ink);
      text-decoration: none;
    }}
    .news-card a:hover {{ color: var(--accent-2); }}
    .news-card p {{
      margin: 0;
      color: #3b4652;
    }}
    .empty {{
      padding: 28px;
      text-align: center;
      color: var(--muted);
    }}
    .muted {{
      color: var(--muted);
      margin: 0;
    }}
    footer {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 0 20px 22px;
      color: var(--muted);
      font-size: 12px;
    }}
    @media (max-width: 900px) {{
      .header-inner {{ display: block; }}
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      form.filters {{ grid-template-columns: 1fr 1fr; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 560px) {{
      header {{ padding-inline: 18px; }}
      main {{ padding-inline: 14px; }}
      .metrics, form.filters {{ grid-template-columns: 1fr; }}
      .score-pill {{ margin-left: 0; }}
      .bar-row {{ grid-template-columns: 86px 1fr 34px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <div>
        <h1>Yahoo! News Dashboard</h1>
        <div class="sub">Excelログを60秒ごとに再読込します</div>
      </div>
      <div class="sub">最終更新: {generated_at}</div>
    </div>
  </header>
  <main>
    <section class="metrics">
      <div class="metric"><span>総件数</span><strong>{total}</strong></div>
      <div class="metric"><span>表示中</span><strong>{shown}</strong></div>
      <div class="metric"><span>平均重要度</span><strong>{average_score}</strong></div>
      <div class="metric"><span>最新通知</span><strong>{latest_text}</strong></div>
    </section>

    <form class="filters" method="get">
      <label>検索
        <input type="search" name="q" value="{q}" placeholder="タイトル・要約・カテゴリ">
      </label>
      <label>カテゴリ
        <select name="category">{"".join(category_options)}</select>
      </label>
      <label>最低重要度
        <input type="number" min="0" max="100" name="min_score" value="{min_score}">
      </label>
      <label>開始日
        <input type="date" name="date_from" value="{date_from}">
      </label>
      <label>終了日
        <input type="date" name="date_to" value="{date_to}">
      </label>
      <label>並び順
        <select name="sort">{sort_html}</select>
      </label>
      <button type="submit">絞り込み</button>
      <a class="clear-link" href="/">クリア</a>
    </form>

    <section class="grid">
      <div class="panel">
        <h2>カテゴリ別件数</h2>
        {_render_bar_chart(category_counts, params)}
      </div>
      <div class="panel">
        <h2>重要度分布</h2>
        {_render_score_histogram(filtered)}
      </div>
    </section>

    <section class="news-list">
      {_render_cards(filtered)}
    </section>
  </main>
  <footer>
    読み込み元: {excel_status} / 重要度80以上: {high_count}件
  </footer>
</body>
</html>"""
    return page.encode("utf-8")


class DashboardHandler(BaseHTTPRequestHandler):
    excel_file = DEFAULT_EXCEL_FILE

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path not in ("/", "/index.html"):
            self.send_error(404)
            return

        params = parse_qs(parsed.query)
        body = _render_page(self.excel_file, params)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[dashboard] {self.address_string()} - {format % args}")


def _find_port(preferred_port: int) -> int:
    for port in range(preferred_port, preferred_port + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("空いているポートが見つかりませんでした。")


def main() -> None:
    parser = argparse.ArgumentParser(description="Yahoo! News local dashboard")
    parser.add_argument("--file", default=str(DEFAULT_EXCEL_FILE), help="Excelログファイル")
    parser.add_argument("--host", default="127.0.0.1", help="待ち受けホスト")
    parser.add_argument("--port", type=int, default=8501, help="待ち受けポート")
    parser.add_argument("--no-browser", action="store_true", help="ブラウザを自動で開かない")
    args = parser.parse_args()

    excel_file = Path(args.file).resolve()
    DashboardHandler.excel_file = excel_file
    port = _find_port(args.port)
    server = ThreadingHTTPServer((args.host, port), DashboardHandler)
    url = f"http://{args.host}:{port}"

    print(f"Dashboard: {url}")
    print(f"Excel log : {excel_file}")
    print("Stop      : Ctrl+C")

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
