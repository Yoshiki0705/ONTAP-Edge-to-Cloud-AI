# 品質ゲート

> このリポジトリのゲートが「何を検査し、どこで走り、壊れたときにどう検出されるか」。
> 常時ロードではない。ゲートを追加・変更するとき、CI が落ちた原因を調べるときに読む。
>
> English: [quality-gates_en.md](quality-gates_en.md)

## 実行の入口は Makefile だけ

パス一覧は `Makefile` の変数（`TEST_DIRS` / `PY_DIRS` / `CFN_TEMPLATES`）が単一の真実。
CI はツールを直接呼ばず make ターゲットを呼ぶ。ローカルと CI が別の木を検査しないため。

```bash
make dev-install     # .venv に requirements-dev.txt のピン留めツールを入れる
make tool-versions   # 実際に使われているバージョンを表示
make check           # lint + security + test + drift（CI と同じ）
```

| ターゲット | 検査対象 | 落ちる条件 |
|---|---|---|
| `make test` | `TEST_DIRS` | テスト失敗 |
| `make lint-py` | `PY_DIRS` | ruff の指摘 |
| `make lint-cfn` | `CFN_TEMPLATES` | cfn-lint の指摘 |
| `make bandit` | `PY_DIRS` | 重大度に関わらず 1 件でも |
| `make secrets` | 作業ツリー（`.gitleaks.toml`） | 検出 1 件でも |
| `make drift` | 下記の 5 ガード | ゲートが無音化する構造の検出 |
| `make agent-config` | global/workspace の steering・skills・hooks | 到達不能な設定 |

## drift ガード

ゲート本体ではなく、**ゲートが黙ったことを検出する**側。すべて `scripts/` にあり、
`make drift` と `.githooks/pre-commit` と CI から呼ばれる。

| スクリプト | 検出するもの |
|---|---|
| `check_agent_context_budget.py` | AGENTS.md の肥大、ローダーの厚み、索引先の到達性と追跡状態 |
| `check_test_coverage_drift.py` | 実在するのに `TEST_DIRS` / `testpaths` / CI matrix のどれかに無い tests/、新規の同名テストファイル |
| `check_git_hooks_wiring.py` | `core.hooksPath` の上書きで `.githooks/` が死んでいる状態、実行されない `.pre-commit-config.yaml` |
| `check_dependency_pins.py` | `requirements-dev.txt` のレンジ指定、CI の Python 版と Lambda ランタイムの不一致、CI のインライン `pip install` |
| `check_sql_interpolation.py` | `scripts/reviewed_sql_sites.txt` に無い SQL 組み立て箇所、および実体を失った記載 |

`scripts/tests/` に自己テストがある。`make test` で走る。

## 実測された無音失敗（このリポジトリで起きていたこと）

新しいゲートを足すときは、下記のどれかを繰り返していないかを確認する。
**通してはいけない入力で落ちることを確認するまで、そのゲートは信用しない。**

| 症状 | 起きていたこと |
|---|---|
| `.githooks/pre-commit` が一度も実行されていない | `core.hooksPath` がグローバル値に設定されており、リポジトリ側のフックパスを完全に置換していた。author email 検査と zizmor は未実行 |
| `.pre-commit-config.yaml` の 6 hooks がどこでも走らない | `pre-commit` CLI 未インストール、`.git/hooks/` 空、CI に `pre-commit run` を呼ぶジョブなし |
| gitleaks が既定ルールを 700KB 分見ていない | `[allowlist] paths` に `*.md` / `*.sh` / workflows / infra テンプレートを一括登録。gitleaks の allowlist の `paths` は**ファイルごとスキップ**なので、自作 2 ルールの騒音を消すために AWS キー・GitHub トークン・秘密鍵の検出も同時に無効化していた。`matchCondition = "AND"` でも狭まらない |
| gitleaks が 218 件検出したのに make が成功 | `command -v gitleaks && gitleaks detect ... \|\| echo "skipped"`。gitleaks は検出時に exit 1 を返すので `\|\|` 側が走り、「skipped」と表示して make は 0 を返していた |
| `# nosec` が効かない | bandit は**報告行そのもの**のコメントしか見ない。前の行に書いた場合 `Total lines skipped (#nosec): 0` になる |
| `pytest` と CI が別の集合を検査 | `testpaths` 未設定。`scripts/tests/` はどちらにも入っておらず、`edge/raspberry-pi/camera/test_prompt.py` は test 関数 0 個の CLI スクリプトなのに名前だけテストに見えていた |

## ゲートを足すときの手順

1. Makefile にターゲットを追加し、**`.PHONY` に必ず入れる**。
   同名ディレクトリがあると make は「up to date」を返してレシピを実行しない。
   `scripts/tests/test_makefile_phony.py` が宣言漏れで落ちる。
2. パスは Makefile の変数に集約する。ターゲット内に直接書かない。
3. CI からは make ターゲットを呼ぶ。ツール名を workflow に書かない。
4. **壊した状態で落ちることを確認する。** 検出されるべき入力を実際に置いて実行する。
   例: `printf 'TOKEN="ghp_..."' > tests/_probe.py && make secrets`
5. 抑制（`# nosec` / `# noqa` / allowlist）を入れるときは、
   抑制後に**否定コントロール**を通す。抑制が想定より広い範囲を消していないか。

## 関連ドキュメント

- [サプライチェーンセキュリティ](supply-chain-security.md) — Actions のピン留め、依存の追加
- [リファレンス doc の品質バー](reference-doc-quality.md)
- [セキュリティ設計](../ja/security-design.md) — OT/IT 境界を含む
- [TESTING.md](../../TESTING.md) — テストの内容と実行方法
