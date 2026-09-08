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
- `make action-pins`（形だけ、ネットワーク不要）と `make action-pins-verify`
  （SHA の実在と、コメントのタグが同じ commit を指すかを GitHub に問う）を通す。
  後者は CI の lint ジョブでも `github.token` を使って走る

> **ピン留めは 2 通りに壊れる。形は正しく、指す先が無い場合と、指す先はあるが
> コメントが別のバージョンを名乗る場合。** 実測で両方あった。
>
> - `github/codeql-action/upload-sarif` が `ce28f5bb`（コメントは `# v3.28.0`）で
>   ピン留めされていたが、**その commit は当該リポジトリに存在しない**（実際の
>   v3.28.0 は `48ab28a6`）。Scorecard ワークフローは追加された日から毎回、
>   ステップが 1 つも走る前に action の解決で失敗していた。README のバッジは
>   一度も実行されていないスキャンを指していた
> - `gitleaks/gitleaks-action` の `ff98106e` は v2.3.9 で、コメントは `# v2.3.8`
>   （v2.3.8 は `f586c143`）。**ピンは正しく、ラベルが誤っていた**ので何も落ちず、
>   ファイルは走っていないバージョンを説明していた
>
> **どちらも既存の検査では見えなかった。** zizmor はワークフローの内容を見るので
> 解決できない SHA は「形として正しい」で通す。Renovate は解決できるピンを更新する
> ので、見つからない digest は管理対象にならない。赤い X も、リポジトリ設定に
> 依存する Scorecard の検査項目による赤と区別できなかった。

> **未解消**: `ossf/scorecard-action` のピンは v2.4.1 で、最新は v2.4.4。
> 追随するかは Renovate の major/minor 方針に委ねている。

## 依存の追加

- **ゲートの判定を左右するツール**（ruff / bandit / cfn-lint / pytest）は
  `requirements-dev.txt` に `==` でピン留めする。レンジは、同じファイルから
  2 台のマシンが別のバージョンを入れることを許す。
  実測: `cfn-lint>=0.87.0` の指定下で PATH 側 1.52.1 / `.venv` 側 1.52.0 だった。
- CI は `pip install -r requirements-dev.txt` で入れる。workflow に
  バージョンを直接書かない。`check_dependency_pins.py` がインライン指定で落ちる。
- **ランタイム依存（`requirements.txt` 系）も `==` で固定する。**
  `check_dependency_pins.py` が全 requirements ファイルを検査して落ちる。
  以前は「エッジデバイス向けにレンジを残す」としていたが、それが 0 点の直接の原因だった
  （下記）。バージョンの追随は Renovate に任せる。
- `make deps-audit` が、固定したバージョンについて OSV に既知の脆弱性を問う。
  **ネットワークが必要で、こちらのコミットなしに判定が変わる**（夜間に advisory が
  公開されれば翌日は赤）ため `check` には入れない。公開前と定期的に流す。

> **レンジは供給網の所見であって利便性ではない。** OpenSSF Scorecard の
> Vulnerabilities が **0 点 / 既知の脆弱性 26 件**だった原因は、個別の危険な依存では
> なく requirements の書き方だった。
>
> - **レンジは「どのバージョンが動くか」を述べていない。** そのためスキャナはその
>   パッケージに対する過去の advisory を全部数える。numpy の 2018 年の項目が
>   `numpy>=1.26.0` に対して報告されていた
> - **下限自体も古かった。** `requests>=2.31.0` は 2.31.0 を許し、これは悪意ある
>   リダイレクトに `.netrc` の資格情報を渡す（PYSEC-2026-1872、2.32.4 で修正）。
>   ONTAP に認証する `sensors/ontap_telemetry.py` が使うのはこの `requests` である。
>   `pyarrow>=15.0.0` も 17.0.0 と 23.0.1 の修正より前を許していた
>
> **固定は曖昧さを消すもので、リスクを消すものではない。** 固定した時点で clean だった
> という記録に過ぎず、advisory は後から公開される。だから `make deps-audit` が要る。

> **未解消**: `.venv` は Python 3.14 で、CI と Lambda ランタイムは 3.12。
> `make test` は配布されるインタプリタを検証していない。
> `check_dependency_pins.py` がこれを NOTE として毎回表示する。

## 関連ドキュメント

- [品質ゲート](quality-gates.md)
- [セキュリティ設計](../ja/security-design.md)
