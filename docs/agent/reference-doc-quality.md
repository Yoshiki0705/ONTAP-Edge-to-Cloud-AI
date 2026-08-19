# リファレンス doc / ガイドの品質バー

> 技術リファレンスやガイドを新規作成・改稿するときに読む。会話や短い回答には適用しない。
>
> English: [reference-doc-quality_en.md](reference-doc-quality_en.md)

## 必須要素

| 要素 | 目的 |
|---|---|
| エグゼクティブサマリの結論 | 読者が最初の 10 行で判断できる |
| FAQ / よくある誤解 | 読まれなかった前提を回収する |
| 選択フローチャート（mermaid 可） | 「どれを選ぶか」を本文から分離する |
| OT/IT セキュリティ考慮（該当時） | 工場・現場設備を扱う doc で必須 |
| 段階的導入ステップ | PoC から本番までの順序 |
| Related Documents（逆リンク） | 到達性。リンクされない doc は読まれない |

## JA/EN parity

`docs/ja/` と `docs/en/` は `## ` 見出しの構成と数を一致させる。
片方を変更したら同じコミットで両方に反映する。
`.github/workflows/agent-output-audit.yml` が見出し数の差を警告する。

## 命名

- 初出は **Amazon FSx for NetApp ONTAP**、以降 **FSx for ONTAP**
- アクセスポイントは **FSx for ONTAP S3 AP**
- `FSxN` / 単独 `FSx` / `FSx ONTAP` は使わない
- 外部引用タイトルの逐語引用のみ例外。その行に `allow:naming` を付ける

## 比較の書き方

選択肢として提示する。優劣で語らない。推奨案自身の制約も対称に書く。
`最強` / `game-changer` / `競合ツール` / `優位性` / `より優れ` は
`agent-output-audit.yml` が hard-fail させる。

## 公開してはいけないもの

個人名・ペルソナ名、メールアドレス、AWS アカウント ID、内部 IP / ホスト名、
サポートケース番号、ベンダー内部チケット ID。role ベース表記
（`Storage Specialist lens`）と `an internal product request (tracked)` を使う。

レビュー過程のメタデータ（ラウンド数、レビュー日、レンズ数）を公開物に残さない。
読者にとってノイズであり、provenance は `.private/`（gitignore）に置く。

## 数値と確信度

- 性能・コストの数値には環境を併記する（version / region / 構成 / 測定日）
- 「サンプル実行」と「本番見積り」を分ける
- 確認していないことは「確認していません」と書く。もっともらしい既定値で埋めない

## コミット前

```bash
make secrets
# CI が同等の検査を行う: .github/workflows/agent-output-audit.yml
```

## 関連ドキュメント

- [品質ゲート](quality-gates.md)
- [サプライチェーンセキュリティ](supply-chain-security.md)
