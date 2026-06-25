# CHANGELOG

## 2026-06-25
### Full-text Search Engine (BM25 + Fuzzy) を追加
- 全文検索エンジン（BM25）を実装
- Fuzzy（曖昧一致）検索を追加
- AIなしモードの検索精度が大幅に向上
- config.txt の変更は不要
- テストコード（test_search.py）を追加

## 2026-06-18
### 🚀 高速化アップデート
- カテゴリ取得を asyncio + to_thread で完全並列化（3〜5倍高速化）
- AI 要約（summarize）を非同期化
- 重要度スコア（importance_score）を非同期化
- メインループの sleep を await 化
- Gemini 混雑時（503/429）でも停止しない安定構造に改善

## 2026-06-15
### ✨ 機能追加
- ローカル Web ダッシュボードを追加
- Excel 自動グラフ生成を追加
- Discord Embed 通知を強化（サムネイル・重要度・関連度）

## 2026-06-05
### 🎉 初期リリース
- Yahoo!ニュース自動監視
- AI 要約
- Discord 通知
- Excel ログ記録
- 音声読み上げ