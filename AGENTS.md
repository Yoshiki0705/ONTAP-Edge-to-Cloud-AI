# AGENTS.md

> Edge-to-cloud data collection, analytics, and AI pipelines from Raspberry Pi and SORACOM to AWS services

## Project Overview

This repository provides reference architectures for connecting IoT/edge devices (Raspberry Pi, SORACOM cellular gateways) to AWS analytics and AI services (Athena, Glue, SageMaker, Bedrock, Rekognition).

## Build & Test Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest

# Lint CloudFormation
cfn-lint cloud/**/*.yaml
```

## Coding Conventions

- Python 3.12 for edge scripts and Lambda functions
- TypeScript for CDK constructs
- Structured JSON logging
- Type hints required for all Python functions

## Supply-Chain Security

### Automated Security Workflows

| Workflow | File | Purpose |
|----------|------|---------|
| zizmor | `.github/workflows/zizmor.yml` | GitHub Actions security linting |
| gitleaks | `.github/workflows/gitleaks.yml` | Secret detection — custom rules in `.gitleaks.toml` |
| OpenSSF Scorecard | `.github/workflows/scorecard.yml` | Automated security health scoring |

### Local Security Checks

```bash
# Pre-commit hook runs automatically (via .githooks/pre-commit):
#   1. Author email verification
#   2. gitleaks secret scanning (staged files)
#   3. zizmor lint (if workflow files changed)

# Manual verification
gitleaks detect --config .gitleaks.toml --no-git --source .
zizmor .github/workflows/
```

### Actions Pinning Policy

- All third-party Actions MUST be pinned to SHA hashes: `uses: owner/action@<sha> # vX.Y.Z`
- `actions/checkout` must set `persist-credentials: false`
- Verify with `zizmor .github/workflows/` before committing workflow changes

---

## Agent Output Standards

> ユーザーレベル Kiro グローバル steering のミラー。steering 未ロードの環境でも従えるようにする。

> CI: `.github/workflows/agent-output-audit.yml`（命名/中立性/リーク/parity）と `gitleaks.yml`（シークレット）。

### Naming (NetApp / AWS)

- 初出は **Amazon FSx for NetApp ONTAP**、以降 **FSx for ONTAP**。`FSxN` / 単独 `FSx` / `FSx ONTAP` は不可。アクセスポイントは **FSx for ONTAP S3 AP**。
- NetApp Workload Factory / NetApp Console / BlueXP は提案しない。native 等価物（CloudWatch, ONTAP REST API, FabricPool, AWS DataSync, Snapshot/FlexClone/SnapMirror）に置換。
- 例外: 外部引用タイトルの逐語引用（その行に `allow:naming` コメントを付与）。

### Vendor neutrality (right-tool-for-the-job)

- ベンダー対決/優劣表現は禁止（"best", "beats X", "X より優れている", "競合ツール", "優位性", "game-changer"）。選択肢として提示し、推奨案自身の制約も含めてトレードオフを対称に記載。

### Public-output safety

- 個人名/ペルソナ名・メール・AWS アカウントID・内部IP/ホスト名・サポートケース番号・ベンダー内部チケットID をコミットしない。role ベース表記（"Storage Specialist lens"）と "an internal product request (tracked)" を使う。
- プロセスメタデータのノイズ禁止（"Persona Review Summary"・レビューラウンド・日付・レンズ数）。レビュー知見は inline の role-based lens note（`> **Topic** (Role lens): ...`）として織り込み、provenance は `.private/`（gitignore）へ。

### Bilingual docs (JA primary + EN)

- JA/EN parity を維持（セクション構成/数の一致、inline note の対応）。片方を変更したら同じ変更で両方に反映。

### Technical reference / guide docs

- 必須要素: エグゼクティブサマリの結論、FAQ/よくある誤解、選択フローチャート（mermaid 可）、OT/IT セキュリティ考慮（該当時）、段階的導入ステップ、Related Documents（逆リンク）、≥10 の inline role-based lens レビュー。

### Before committing docs

```bash
gitleaks detect --config .gitleaks.toml --no-git --source .
# CI が agent-output チェックをミラー: .github/workflows/agent-output-audit.yml
```
