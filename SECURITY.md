# セキュリティポリシー / Security Policy

日本語が正典です。English follows below.

## 対象範囲

このリポジトリは個人の技術検証で、所属組織の公式製品ではありません。稼働中のサービスは
なく、あるのは読者が**自分の AWS アカウントにデプロイするためのコードとテンプレート**です。
したがって守るべきものは「動いている環境」ではなく、**デプロイした人の環境を危険にする
欠陥を出荷していないこと**です。

具体的に想定している欠陥は次の 3 つです。

| 種類 | 例 |
|---|---|
| 出荷物が読者の環境を危険にする | テンプレートの過大な IAM 権限、公開されたエンドポイント、パブリッシャー由来の値が検証されずにパスやキーや SQL に届く経路（[`cloud/iot_ingestion/identifiers.py`](cloud/iot_ingestion/identifiers.py)） |
| サプライチェーン | ワークフローの Actions ピン、`requirements*.txt` の依存、`.githooks/` と `scripts/` のゲート |
| 非公開情報の混入 | 実 IP・ホスト名・アカウント ID・個人名・資格情報がコミットされている |

## 報告の方法

| 内容 | 報告先 |
|---|---|
| 悪用可能な欠陥（IAM、入力検証、認可、依存） | **Security タブの「Report a vulnerability」から非公開で**報告してください |
| 非公開情報の混入 | 同じく非公開で。**該当箇所のパスと行だけを書き、値そのものは引用しないでください**。公開 Issue は露出を拡大します |
| 安全でない構成に読者を導く記述 | 公開 Issue で構いません。議論が他の読者にも役立ちます |

## 対応

- 対象ブランチは `main` のみです。過去のタグやコミットに遡った修正は行いません
- **応答時間の保証はありません。** 個人の検証活動として、可能な範囲で対応します
- 非公開情報の混入は最優先で扱います。まず `main` から削除し、履歴の書き換えは別に判断します。
  **git の履歴はホスト側にキャッシュされるため、force-push 後も残ることがあります。**
  `main` からの削除は緩和策であって、消えたことの保証ではありません
- 修正が入った場合、内容は公開の変更履歴（PR）に残ります。報告者名は希望がなければ書きません

## 既にある予防的な仕組み

| 仕組み | 検出するもの |
|---|---|
| `make security`（bandit + gitleaks） | 静的解析の指摘、作業ツリーのシークレット |
| `make action-pins-verify` | 存在しない SHA へのピン、コメントと実際のバージョンの不一致 |
| `make lint` の SQL 検査 | 未レビューの SQL 組み立て箇所 |
| Security & Privacy ワークフロー | 追跡してはいけないパス、実 IP、個人名 |
| GitHub Secret scanning + push protection | 既知の形のシークレット |

限界も書いておきます。**実機での E2E テストは未完了で、ONTAP 連携は実環境で確認されて
いません**（[検証状態](docs/ja/verification-status.md)）。検証されていないコードを本番に
そのまま置かないでください。

---

# Security Policy (English)

## Scope

This is a personal technical-validation project, not an official product of any
organisation. Nothing here is a running service; what ships is **code and templates that
readers deploy into their own AWS accounts**. So the thing to protect is not a live
environment but the absence of defects that would put *a reader's* environment at risk.

| Class | Example |
|---|---|
| Shipped content endangering a reader | over-broad IAM in a template, an exposed endpoint, a publisher-controlled value reaching a path, key or SQL statement unvalidated ([`cloud/iot_ingestion/identifiers.py`](cloud/iot_ingestion/identifiers.py)) |
| Supply chain | Actions pins, dependencies in `requirements*.txt`, the gates in `.githooks/` and `scripts/` |
| Non-public information committed | real IPs, hostnames, account IDs, personal names, credentials |

## Reporting

| Concern | Where |
|---|---|
| An exploitable defect (IAM, input validation, authorisation, dependencies) | **Privately, via "Report a vulnerability" on the Security tab** |
| Non-public information committed | Also privately. **Give the path and line only; do not quote the value itself.** A public issue amplifies the exposure |
| Guidance that would lead a reader to an insecure configuration | A public issue is fine; discussing it openly helps other readers |

## Response

- Only `main` is in scope. Fixes are not backported to earlier tags or commits
- **No response time is promised.** This is a personal project, handled as capacity allows
- Committed non-public information is treated as the highest priority: removed from `main`
  first, with history rewriting assessed separately. **Git history is cached by the host and
  can survive a force-push**, so removal from `main` is a mitigation, not a guarantee
- Fixes are visible in the public PR history. Reporters are not named unless they ask to be

## Preventive controls already here

`make security` (bandit, gitleaks), `make action-pins-verify` (a pin to a SHA that does not
exist, or a comment naming another version), the SQL construction sweep in `make lint`, the
Security & Privacy workflow (paths that must not be tracked, real IPs, personal names), and
GitHub secret scanning with push protection.

One limit worth stating: **end-to-end testing on real hardware is incomplete and the ONTAP
integration has not been exercised against a real filesystem** (see
[verification status](docs/en/verification-status.md)). Do not put unverified code into
production as-is.
