# デプロイメントガイド

Edge-to-Cloud AI プロジェクトの CloudFormation スタックを既存環境へデプロイする手順書。

---

## Quick Start（最短デプロイ）

FSx for ONTAP を使わず、AI 画像分析だけを試したい場合の最短手順:

```bash
# 1. 事前検証
./scripts/preflight-check.sh --skip network

# 2. 共有基盤デプロイ（3〜5分）
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides Environment=poc AlertEmail=you@example.com \
  --capabilities CAPABILITY_NAMED_IAM \
  --tags Project=edge-to-cloud-ai

# 3. デプロイ確認
aws cloudformation describe-stacks --stack-name edge-to-cloud-ai-poc \
  --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' --output table

# 4. ユースケースデプロイ（1〜2分）
aws cloudformation deploy \
  --template-file usecases/3d-print-quality/template.yaml \
  --stack-name edge-to-cloud-print-quality-poc \
  --parameter-overrides SharedStackName=edge-to-cloud-ai-poc \
  --capabilities CAPABILITY_NAMED_IAM

# 5. Lambda コードのデプロイ（テンプレートはプレースホルダーのみ）
cd cloud/ai/image_analyzer
zip -r /tmp/image_analyzer.zip handler.py
aws lambda update-function-code \
  --function-name edge-to-cloud-image-analyzer-edge-to-cloud-print-quality-poc \
  --zip-file fileb:///tmp/image_analyzer.zip
```

> 詳細な手順、既存 VPC への統合、FSx for ONTAP の追加は以下のセクションを参照。

---

## デプロイ後に得られるもの

| スタック | 作成されるリソース | 確認方法 |
|---------|-------------------|---------|
| ingestion | S3 バケット、Kinesis Stream、Firehose、SNS Topic、IAM Role、Glue DB | `aws cloudformation describe-stacks --stack-name <name> --query 'Stacks[0].Outputs'` |
| fsxn | VPC、サブネット x2、FSx for ONTAP、SVM | FSx コンソールでファイルシステム確認 |
| 3d-print-quality | Lambda 関数、CloudWatch Alarm、EventBridge Rule | `aws lambda get-function --function-name <name>` |
| visual-inspection | Lambda 関数、CloudWatch Alarm | 同上 |
| ontap-telemetry | Glue Crawler、CloudWatch Alarm、Athena Named Queries | Glue コンソールで Crawler 確認 |

---

## 目次

1. [前提条件](#1-前提条件)
2. [アーキテクチャとデプロイ順序](#2-アーキテクチャとデプロイ順序)
3. [事前検証（Preflight Check）](#3-事前検証preflight-check)
4. [スタック別デプロイ手順](#4-スタック別デプロイ手順)
5. [パラメータリファレンス](#5-パラメータリファレンス)
6. [`deploy` vs `create-stack` の違い](#6-deploy-vs-create-stack-の違い)
7. [VPC エンドポイント競合マトリクス](#7-vpc-エンドポイント競合マトリクス)
8. [コスト概算](#8-コスト概算)
9. [Day 2 運用](#9-day-2-運用)
10. [トラブルシューティング](#10-トラブルシューティング)
11. [クリーンアップ](#11-クリーンアップ)

---

## 1. 前提条件

### ツール

| ツール | 最低バージョン | インストール |
|--------|---------------|-------------|
| AWS CLI | v2.x | [公式ガイド](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| jq | 1.6+ | macOS: `brew install jq` / Linux: `sudo apt-get install jq` / Windows: `choco install jq` |
| cfn-lint | 1.x (推奨) | `pip install cfn-lint` |
| zip | (任意) | Lambda コードパッケージ作成用 |

### AWS アカウント要件

- CloudFormation、S3、Kinesis、Lambda、IAM、SNS、Glue の操作権限
- FSx for ONTAP スタックをデプロイする場合: `fsx:*` 権限
- Bedrock を利用するユースケース: 対象モデルのアクセスが有効化済み
- `CAPABILITY_NAMED_IAM` を承認できる権限

### リージョン

東京リージョン（`ap-northeast-1`）を推奨。Bedrock モデル ID の `jp.` プレフィックスは[クロスリージョン推論](https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html)の日本リージョン指定であり、`ap-northeast-1` でのみ利用可能。他リージョンで使用する場合はプレフィックスを変更すること（例: `us.` → `us-east-1`）。

---

## 2. アーキテクチャとデプロイ順序

```
┌─────────────────────────────────────────────────────────────────┐
│                    デプロイ順序                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ① cloud/fsxn/template.yaml          (任意 — FSx for ONTAP)    │
│       ↓                                                         │
│  ② cloud/ingestion/template.yaml     (必須 — 共有基盤)          │
│       ↓                                                         │
│  ③ usecases/*/template.yaml          (選択 — ユースケース)      │
│     ├── ontap-telemetry-analytics                               │
│     ├── 3d-print-quality                                        │
│     └── visual-inspection                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**依存関係:**
- ユースケーススタックは `ingestion` スタックの Outputs を `Fn::ImportValue` で参照する
- `fsxn` スタックは独立 — FSx for ONTAP が不要であれば省略可

---

## 3. 事前検証（Preflight Check）

デプロイ前に必ず事前検証スクリプトを実行する。

```bash
# 全チェック実行
./scripts/preflight-check.sh

# ネットワークチェックをスキップ
./scripts/preflight-check.sh --skip network

# Bedrock チェックをスキップ（モデル未利用時）
./scripts/preflight-check.sh --skip bedrock

# 特定スタックのみ検証
./scripts/preflight-check.sh --stack ingestion

# リージョン指定
./scripts/preflight-check.sh --region ap-northeast-1
```

スクリプトが確認する項目:
- AWS CLI・認証情報の有効性
- IAM 権限のスポットチェック
- CloudFormation テンプレートの構文検証
- VPC CIDR の重複検知
- AZ 数の確認（FSx for ONTAP Multi-AZ には 2 AZ 必要）
- Bedrock モデルアクセス
- 既存スタックとの名前競合
- コスト警告

---

## 4. スタック別デプロイ手順

### 4.1 FSx for ONTAP スタック（任意）

> **コスト注意**: FSx for ONTAP は最低 ~$500+/月。PoC 完了後は速やかに削除すること。

```bash
# パラメータファイルをコピーして編集
cp cfn-params/fsxn.example.json cfn-params/fsxn.local.json
# vi cfn-params/fsxn.local.json  ← 環境に合わせて編集

# デプロイ
aws cloudformation deploy \
  --template-file cloud/fsxn/template.yaml \
  --stack-name edge-to-cloud-fsxn-poc \
  --parameter-overrides \
    Environment=poc \
    VpcCidr=10.0.0.0/16 \
    SubnetCidr1=10.0.1.0/24 \
    SubnetCidr2=10.0.2.0/24 \
    FSxStorageCapacity=1024 \
    FSxThroughputCapacity=128 \
  --capabilities CAPABILITY_NAMED_IAM \
  --tags Project=edge-to-cloud-ai Environment=poc
```

所要時間: 約 30〜45 分（FSx for ONTAP の作成に時間がかかる）

### 4.2 Ingestion スタック（必須）

```bash
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides \
    Environment=poc \
    AlertEmail=alerts@example.com \
  --capabilities CAPABILITY_NAMED_IAM \
  --tags Project=edge-to-cloud-ai Environment=poc
```

SORACOM 連携が必要な場合（セルラー接続用）:

> **SORACOM Operator ID とは**: SORACOM コンソールの「オペレーター設定」で確認できる `OP00` で始まる識別子。AWS IAM ロールの ExternalId として使用し、SORACOM Funnel/Beam からの AssumeRole を安全に制限します。

```bash
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides \
    Environment=poc \
    AlertEmail=alerts@example.com \
    SoracomOperatorId=OP00XXXXXXXX \
  --capabilities CAPABILITY_NAMED_IAM \
  --tags Project=edge-to-cloud-ai Environment=poc
```

所要時間: 約 3〜5 分

#### デプロイ後の確認

```bash
# Outputs を確認（S3 バケット名、Kinesis ARN、SNS Topic ARN 等）
aws cloudformation describe-stacks --stack-name edge-to-cloud-ai-poc \
  --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' --output table
```

> **SNS 確認メール**: `AlertEmail` を指定した場合、AWS から確認メールが届きます。**メール内のリンクをクリックしてサブスクリプションを承認**しないと、アラートは配信されません。

### 4.3 ユースケーススタック（選択）

#### ONTAP テレメトリ分析

```bash
aws cloudformation deploy \
  --template-file usecases/ontap-telemetry-analytics/template.yaml \
  --stack-name edge-to-cloud-telemetry-poc \
  --parameter-overrides \
    SharedStackName=edge-to-cloud-ai-poc \
  --tags Project=edge-to-cloud-ai Environment=poc UseCase=ontap-telemetry
```

#### 3D プリント品質監視

```bash
aws cloudformation deploy \
  --template-file usecases/3d-print-quality/template.yaml \
  --stack-name edge-to-cloud-print-quality-poc \
  --parameter-overrides \
    SharedStackName=edge-to-cloud-ai-poc \
    BedrockScreeningModel=jp.anthropic.claude-haiku-4-5-20251001-v1:0 \
    BedrockDetailModel=jp.anthropic.claude-sonnet-4-5-20250929-v1:0 \
    ConfidenceThreshold=0.7 \
  --capabilities CAPABILITY_NAMED_IAM \
  --tags Project=edge-to-cloud-ai Environment=poc UseCase=3d-print-quality
```

#### 外観検査（Visual Inspection）

```bash
aws cloudformation deploy \
  --template-file usecases/visual-inspection/template.yaml \
  --stack-name edge-to-cloud-visual-inspection-poc \
  --parameter-overrides \
    SharedStackName=edge-to-cloud-ai-poc \
    BedrockScreeningModel=jp.anthropic.claude-haiku-4-5-20251001-v1:0 \
    BedrockDetailModel=jp.anthropic.claude-sonnet-4-5-20250929-v1:0 \
  --capabilities CAPABILITY_NAMED_IAM \
  --tags Project=edge-to-cloud-ai Environment=poc UseCase=visual-inspection
```

### 4.4 Lambda 関数コードのデプロイ

CloudFormation テンプレートの Lambda 関数はプレースホルダーコードのみ含みます。実際のハンドラーコードは別途デプロイが必要です:

```bash
# 3D Print Quality / Visual Inspection 共通
cd cloud/ai/image_analyzer
zip -r /tmp/image_analyzer.zip handler.py requirements.txt
aws lambda update-function-code \
  --function-name edge-to-cloud-image-analyzer-edge-to-cloud-print-quality-poc \
  --zip-file fileb:///tmp/image_analyzer.zip

# 依存ライブラリが必要な場合は Lambda Layer を作成
# pip install -r requirements.txt -t python/
# zip -r /tmp/layer.zip python/
# aws lambda publish-layer-version --layer-name image-analyzer-deps \
#   --zip-file fileb:///tmp/layer.zip --compatible-runtimes python3.12
```

> **注意**: `update-function-code` を実行するまで、Lambda 関数は HTTP 501 を返します。

---

## 5. パラメータリファレンス

### cloud/fsxn/template.yaml

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `Environment` | String | `poc` | 環境名（`poc` / `production`） |
| `VpcCidr` | String | `10.0.0.0/16` | VPC の CIDR ブロック |
| `SubnetCidr1` | String | `10.0.1.0/24` | サブネット 1（プライマリ AZ） |
| `SubnetCidr2` | String | `10.0.2.0/24` | サブネット 2（セカンダリ AZ） |
| `FSxStorageCapacity` | Number | `1024` | ストレージ容量（GiB、最小 1024） |
| `FSxThroughputCapacity` | Number | `128` | スループット容量（MBps: 128/256/512/1024/2048） |

### cloud/ingestion/template.yaml

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `Environment` | String | `poc` | 環境名（`poc` / `staging` / `production`） |
| `SoracomOperatorId` | String | `""` | SORACOM オペレータ ID（セルラー接続時のみ） |
| `AlertEmail` | String | `""` | アラート送信先メールアドレス |

### usecases/ontap-telemetry-analytics/template.yaml

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `SharedStackName` | String | `edge-to-cloud-ai-poc` | Ingestion スタック名（CrossStack 参照用） |

### usecases/3d-print-quality/template.yaml

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `SharedStackName` | String | `edge-to-cloud-ai-poc` | Ingestion スタック名 |
| `BedrockScreeningModel` | String | `jp.anthropic.claude-haiku-4-5-20251001-v1:0` | Stage 1 スクリーニング用モデル |
| `BedrockDetailModel` | String | `jp.anthropic.claude-sonnet-4-5-20250929-v1:0` | Stage 2 詳細分析用モデル |
| `ConfidenceThreshold` | String | `0.7` | アラート発報の信頼度閾値 |

### usecases/visual-inspection/template.yaml

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| `SharedStackName` | String | `edge-to-cloud-ai-poc` | Ingestion スタック名 |
| `BedrockScreeningModel` | String | `jp.anthropic.claude-haiku-4-5-20251001-v1:0` | Stage 1 スクリーニング用モデル |
| `BedrockDetailModel` | String | `jp.anthropic.claude-sonnet-4-5-20250929-v1:0` | Stage 2 詳細分析用モデル |

---

## 6. `deploy` vs `create-stack` の違い

| 項目 | `aws cloudformation deploy` | `aws cloudformation create-stack` |
|------|----------------------------|----------------------------------|
| 冪等性 | あり（既存スタックは update） | なし（既存で失敗） |
| パラメータ渡し | `--parameter-overrides Key=Value` | `--parameters file://params.json` |
| 変更セット | 自動作成・実行 | 手動で `create-change-set` が必要 |
| 推奨用途 | CI/CD、繰り返しデプロイ | 初回のみ・JSON パラメータファイル利用時 |

本プロジェクトでは **`deploy`** を推奨。`create-stack` を使う場合:

```bash
# create-stack 形式（パラメータファイル利用）
aws cloudformation create-stack \
  --template-body file://cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameters file://cfn-params/ingestion.example.json \
  --capabilities CAPABILITY_NAMED_IAM

# スタック完了待ち
aws cloudformation wait stack-create-complete \
  --stack-name edge-to-cloud-ai-poc
```

> **注意**: `deploy` の `--parameter-overrides` は `Key=Value` 形式だが、`create-stack` の `--parameters` は JSON 配列形式（`cfn-params/*.example.json` の形式）を受け取る。

---

## 7. VPC エンドポイント競合マトリクス

プライベートサブネットから各サービスにアクセスするために必要な VPC エンドポイント一覧。既存 VPC に統合する場合、重複作成に注意。

| VPC エンドポイント | 種別 | 必要とするスタック | 備考 |
|-------------------|------|-------------------|------|
| `com.amazonaws.<region>.fsx` | Interface | fsxn | FSx for ONTAP 管理 API |
| `com.amazonaws.<region>.s3` | Gateway | ingestion, 全ユースケース | 無料、ルートテーブル紐付け |
| `com.amazonaws.<region>.kinesis-streams` | Interface | ingestion | Kinesis PutRecord |
| `com.amazonaws.<region>.kinesis-firehose` | Interface | ingestion | Firehose 配信 |
| `com.amazonaws.<region>.bedrock-runtime` | Interface | 3d-print-quality, visual-inspection | モデル呼び出し |
| `com.amazonaws.<region>.sns` | Interface | ingestion, 全ユースケース | アラート送信 |
| `com.amazonaws.<region>.glue` | Interface | ontap-telemetry-analytics | Crawler 実行 |
| `com.amazonaws.<region>.logs` | Interface | 全 Lambda | CloudWatch Logs |
| `com.amazonaws.<region>.monitoring` | Interface | 全ユースケース | CloudWatch メトリクス |

### 既存 VPC に統合する場合の注意点

1. **CIDR 重複**: `preflight-check.sh` で自動検出。既存 VPC と `10.0.0.0/16` が被る場合はパラメータで変更
2. **セキュリティグループ**: FSx for ONTAP は NFS (2049)、SMB (445)、HTTPS (443) を内部通信に使用
3. **DNS 解決**: VPC 内 DNS が有効であること（`EnableDnsSupport: true`）
4. **ルートテーブル**: S3 Gateway エンドポイントは対象サブネットのルートテーブルに明示的に紐付ける必要がある
5. **SnapMirror ポート**: テンプレートは 11104-11105/tcp を `0.0.0.0/0` に開放している（SnapMirror クロスリージョン用）。オンプレミスからの SnapMirror のみ使う場合は、送信元 IP を限定すること

---

## 8. コスト概算

### 月額コスト目安（ap-northeast-1、PoC 構成）

| リソース | 構成 | 概算月額 |
|---------|------|---------|
| FSx for ONTAP | 1 TiB SSD, 128 MBps, Multi-AZ | ~$500+ |
| Kinesis Data Stream | ON_DEMAND モード | ~$15–50 |
| Amazon Data Firehose | 5 MB バッファ, 300s 間隔 | ~$5–20 |
| S3 | Standard, 数 GB | ~$1–10 |
| Lambda | 1000 回/日, 256 MB, 90s | ~$5–15 |
| Bedrock (Claude) | 1000 回/日 | ~$10–100 |
| Glue Crawler | 1 回/日 | ~$30/月 |
| SNS | 数百通/月 | <$1 |
| **合計（FSx 込み）** | | **~$570–730** |
| **合計（FSx 無し）** | | **~$70–230** |

> **コスト削減ポイント:**
> - PoC 完了後は FSx for ONTAP スタックを削除する
> - Kinesis を ON_DEMAND → PROVISIONED（低トラフィック時）に切り替える
> - Glue Crawler のスケジュールを週次に変更する
> - Lambda の Bedrock 呼び出しを Haiku のみに絞る（Sonnet は確信度が低い時だけ）

> **AWS 無料利用枠の適用（新規アカウント 12 か月以内）:**
> - S3: 5 GB 標準ストレージ
> - Lambda: 100 万リクエスト/月 + 40 万 GB-秒
> - Kinesis: 対象外（ON_DEMAND は無料枠なし）
> - SNS: 1,000 メール通知/月

---

## 9. Day 2 運用

### 9.1 スタック更新

```bash
# テンプレートを変更後、deploy を再実行（冪等）
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides Environment=poc AlertEmail=new-alerts@example.com \
  --capabilities CAPABILITY_NAMED_IAM
```

```bash
# ドリフト検出（手動変更の検知）
aws cloudformation detect-stack-drift --stack-name edge-to-cloud-ai-poc
# 数分後に結果確認
aws cloudformation describe-stack-drift-detection-status \
  --stack-drift-detection-id <detection-id>
```

### 9.2 監視ダッシュボード

デプロイ後に確認すべきメトリクス:

| メトリクス | ネームスペース | 閾値例 |
|-----------|--------------|--------|
| FSx for ONTAP 容量使用率 | `EdgeToCloud/ONTAP` | > 80% で警告 |
| FSx for ONTAP 書き込みレイテンシ | `EdgeToCloud/ONTAP` | P95 > 5ms で警告 |
| Lambda エラー率 | `AWS/Lambda` | > 5% |
| Kinesis IteratorAge | `AWS/Kinesis` | > 60s |
| 異常検出率 | `EdgeToCloud/PrintQuality` | > 30% |

### 9.3 ログ確認

```bash
# Lambda ログ確認
aws logs tail /aws/lambda/edge-to-cloud-image-analyzer-edge-to-cloud-print-quality-poc \
  --follow --since 1h

# スタックイベント確認
aws cloudformation describe-stack-events \
  --stack-name edge-to-cloud-ai-poc \
  --query 'StackEvents[?ResourceStatus==`CREATE_FAILED` || ResourceStatus==`UPDATE_FAILED`]'
```

### 9.4 バックアップとリカバリ

- **S3**: バージョニング有効。ライフサイクルルールで 90 日後に IA、365 日後に Glacier
- **FSx for ONTAP**: 自動バックアップを有効化（Snapshot ポリシー設定は ONTAP 側）
- **Kinesis**: 24 時間のデータ保持（リプレイ可能）

### 9.5 スケーリング

| コンポーネント | スケーリング方法 |
|--------------|----------------|
| Kinesis | ON_DEMAND で自動 |
| Firehose | バッファサイズ / 間隔の調整 |
| Lambda | 同時実行数の予約設定 |
| FSx for ONTAP | スループット / ストレージの段階的増加 |

---

## 10. トラブルシューティング

### よくあるエラー

| エラー | 原因 | 対処 |
|--------|------|------|
| `InsufficientCapabilities` | `CAPABILITY_NAMED_IAM` 未指定 | `--capabilities CAPABILITY_NAMED_IAM` を追加 |
| `Stack already exists` | 同名スタックが存在 | スタック名を変更、または `deploy`（update）を使用 |
| `No export named ...` | 依存スタックが未デプロイ | Ingestion スタックを先にデプロイ |
| `CIDR block conflicts` | VPC CIDR が既存と重複 | `VpcCidr` パラメータを変更 |
| `ResourceNotFound (Bedrock)` | モデルアクセス未有効化 | Bedrock コンソールでモデルアクセスを有効化 |
| `CREATE_FAILED (FSx)` | AZ 不足またはクォータ超過 | Service Quotas で上限確認 |

### ロールバック後のリカバリ

```bash
# スタック状態確認
aws cloudformation describe-stacks \
  --stack-name edge-to-cloud-ai-poc \
  --query 'Stacks[0].StackStatus'

# ROLLBACK_COMPLETE のスタックを削除して再作成
aws cloudformation delete-stack --stack-name edge-to-cloud-ai-poc
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-ai-poc
# → 再デプロイ
```

---

## 11. クリーンアップ

スタックの削除は作成と**逆順**で行う。

```bash
# ③ ユースケーススタック（どの順番でも可）
aws cloudformation delete-stack --stack-name edge-to-cloud-visual-inspection-poc
aws cloudformation delete-stack --stack-name edge-to-cloud-print-quality-poc
aws cloudformation delete-stack --stack-name edge-to-cloud-telemetry-poc

# 完了待ち
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-visual-inspection-poc
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-print-quality-poc
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-telemetry-poc

# ② Ingestion スタック
aws cloudformation delete-stack --stack-name edge-to-cloud-ai-poc
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-ai-poc

# ① FSx for ONTAP スタック（デプロイした場合のみ）
aws cloudformation delete-stack --stack-name edge-to-cloud-fsxn-poc
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-fsxn-poc
```

> **注意**: S3 バケット（`DataLakeBucket`）は `DeletionPolicy: Retain` のため、スタック削除後も残る。手動で削除が必要:
> ```bash
> aws s3 rb s3://edge-to-cloud-ai-poc-<ACCOUNT_ID> --force
> ```

---

## 関連ドキュメント

- [cfn-params/README.md](../../cfn-params/README.md) — パラメータファイルの使い方
- [cloud/fsxn/README.md](../../cloud/fsxn/README.md) — FSx for ONTAP 構成の詳細
- [docs/ja/security-design.md](./security-design.md) — セキュリティ設計
- [docs/ja/operations-design.md](./operations-design.md) — 運用設計
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — コントリビューションガイド
