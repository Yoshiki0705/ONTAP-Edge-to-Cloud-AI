# サプライチェーンセキュリティ

> GitHub Actions を追加・変更するとき、依存を追加するときに読む。
>
> English: [supply-chain-security_en.md](supply-chain-security_en.md)

## 自動チェック

| ワークフロー | ファイル | 目的 |
|---|---|---|
| zizmor | `.github/workflows/zizmor.yml` | Actions のセキュリティ lint（`paths: .github/workflows/**` のみで発火） |
| gitleaks | `.github/workflows/gitleaks.yml` | シークレット検出。`fetch-depth: 0` で履歴全体 |
| OpenSSF Scorecard | `.github/workflows/scorecard.yml` | セキュリティ健全性スコア |
| Agent Output Audit | `.github/workflows/agent-output-audit.yml` | 命名・比較表現・リーク・JA/EN parity |
| Security & Privacy | `.github/workflows/security-check.yml` | 追跡してはいけないパス、実 IP、ペルソナ名 |

## ローカル

```bash
make precommit-install   # core.hooksPath を .githooks に向ける（初回のみ）
make secrets             # 作業ツリーの gitleaks
zizmor .github/workflows/
```

`.githooks/pre-commit` はグローバルフックに委譲してから固有の検査を行う。
`core.hooksPath` は単一値なので、リポジトリ側に向けるだけではグローバル側の
検査（`.kiro/` や `.env` の staged パス遮断）が止まる。委譲はそれを避けるため。

> **履歴に関する注記**: `make secrets` は作業ツリーを見る。履歴は
> `gitleaks.yml` が見る。2026-05-29 の 1 コミットに 5 件（当時の
> `.githooks/pre-commit` と `tests/test_ontap_e2e.py`）が残っており、内容は
> 現行ファイルでは修正済み。履歴の書き換えは make ターゲットからは行わない。

## Actions のピン留め

- サードパーティ Actions は SHA でピン留めする: `uses: owner/action@<sha> # vX.Y.Z`
- `actions/checkout` は `persist-credentials: false` を設定する
- 変更前に `zizmor .github/workflows/` を通す

## 依存の追加

- **ゲートの判定を左右するツール**（ruff / bandit / cfn-lint / pytest）は
  `requirements-dev.txt` に `==` でピン留めする。レンジは、同じファイルから
  2 台のマシンが別のバージョンを入れることを許す。
  実測: `cfn-lint>=0.87.0` の指定下で PATH 側 1.52.1 / `.venv` 側 1.52.0 だった。
- CI は `pip install -r requirements-dev.txt` で入れる。workflow に
  バージョンを直接書かない。`check_dependency_pins.py` がインライン指定で落ちる。
- ランタイム依存（`requirements.txt`）はエッジデバイス向けにレンジを残している。
  本番配布物として固める場合はロックファイルを別に持つ。

> **未解消**: `.venv` は Python 3.14 で、CI と Lambda ランタイムは 3.12。
> `make test` は配布されるインタプリタを検証していない。
> `check_dependency_pins.py` がこれを NOTE として毎回表示する。

## 関連ドキュメント

- [品質ゲート](quality-gates.md)
- [セキュリティ設計](../ja/security-design.md)
