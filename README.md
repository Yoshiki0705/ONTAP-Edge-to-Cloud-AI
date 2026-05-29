🌐 **日本語** | [English](README_en.md)

# ONTAP Edge-to-Cloud AI

> NetApp ONTAP × IoT × AWS AI/Analytics — ONTAP ストレージに蓄積されたデータを、エッジデバイス（Raspberry Pi、SORACOM）経由で AWS AI/分析サービスに連携するリファレンスアーキテクチャ

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Yoshiki0705/ontap-edge-to-cloud-ai/badge)](https://scorecard.dev/viewer/?uri=github.com/Yoshiki0705/ontap-edge-to-cloud-ai)

## 概要

ONTAP（オンプレミス FAS/AFF、ONTAP Select、または FSx for ONTAP）上のファイルデータ（検査画像、設備ログ、センサーCSV）を、IoT エッジデバイスで収集・前処理し、AWS の AI/分析サービスで活用するパイプラインです。最初の PoC として **3Dプリント品質監視** を実装しています。

### ONTAP が中心にある理由

- **既存データ資産の活用**: 工場/拠点の ONTAP NAS に蓄積されたデータを、コピーなしで AI/分析に接続
- **FPolicy イベント駆動**: ファイル到着をトリガーに自動分析パイプラインを起動
- **SnapMirror 同期**: エッジ → クラウド（FSxN）のデータ同期を帯域効率よく実現
- **S3 Access Points**: FSxN 上のデータに S3 API で直接アクセス（Athena、Bedrock、SageMaker）
- **Multi-Protocol**: NFS（エッジデバイス）+ SMB（Windows装置）+ S3（AWS サービス）を同一データで

### アーキテクチャ（2段階AI分析）

```
[Edge]                    [SORACOM]              [AWS Cloud]
Raspberry Pi 5            Flux / Funnel         ┌─────────────────────────────┐
┌──────────────┐          ┌─────────┐           │  S3 Data Lake               │
│ USB Camera   │──60s間隔→ │ Cellular│──HTTPS──→ │    ↓                        │
│ (1080p JPEG) │          │ or WiFi │           │  Lambda (2段階分析)           │
└──────────────┘          └─────────┘           │    ├─ Haiku: スクリーニング    │
                                                │    └─ Sonnet: 詳細分析(異常時) │
[ONTAP Storage]                                 │    ↓                         │
┌──────────────┐                                │  SNS → Slack/Email 通知      │
│ FAS/AFF      │──SnapMirror──→ FSx for ONTAP   │    ↓                         │
│ FPolicy      │                  ↓ S3 AP       │  Athena (SQL分析)            │
│ REST API     │                  Bedrock/SM    │  QuickSight (BI)            │
└──────────────┘                                └─────────────────────────────┘
```

### コスト最適化

| 方式 | 月間コスト | 説明 |
|------|-----------|------|
| 単一モデル (Sonnet) | ~$259/月 | 全画像を高精度モデルで分析 |
| **2段階分析 (採用)** | **~$40/月** | Haiku でスクリーニング、異常疑いのみ Sonnet |

### 現在のステータス

| コンポーネント | ステータス | 備考 |
|--------------|-----------|------|
| AWS インフラ (CFn) | ✅ デプロイ済 | S3, Kinesis, Lambda, IAM, Glue, SNS |
| Lambda (2段階分析) | ✅ デプロイ済 | Haiku + Sonnet, プロンプト精度100% |
| ONTAP テレメトリ収集 | ✅ 実装済 | REST API ポーリング (モックE2Eテスト済) |
| CloudWatch 監視 | ✅ 設定済 | ダッシュボード + アラーム×3 + 予算 |
| エッジコード | ✅ 実装済 | Pi到着後にテスト |
| SORACOM 連携 | 📋 設定待ち | SIM到着後に設定 |
| 実機テスト | 📋 ハードウェア待ち | Pi + カメラ到着後 |

### 関連プロジェクト

- [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) — FSx for ONTAP S3 Access Points × Lakehouse 統合（親プロジェクト）

## クイックスタート

### 前提条件

- AWS CLI v2 + 認証設定済み
- Python 3.12+
- Bedrock モデルアクセス有効化（Claude Haiku 4.5 / Sonnet 4.5）
- （オプション）ONTAP 9.13.1+ (FPolicy, REST API)

### AWS インフラデプロイ

```bash
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides \
    Environment=poc \
    SoracomOperatorId=<YOUR_OPERATOR_ID> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### エッジデバイスセットアップ

```bash
# Raspberry Pi 初回セットアップ → edge/raspberry-pi/SETUP.md

# Phase 1: 最小構成で動作確認
cd edge/raspberry-pi/camera
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python simple_capture.py --loop
```

## ディレクトリ構成

```
edge/                          エッジデバイスコード
  raspberry-pi/
    camera/                    カメラキャプチャシステム
      simple_capture.py        Phase 1: 最小スクリプト (Flux用)
      main.py                  Phase 2+: フル機能版 (バッファ、ヘルス監視)
    sensors/
      ontap_telemetry.py       ONTAP REST API テレメトリ収集
    SETUP.md                   初回セットアップ Playbook
  soracom/                     SORACOM 設定ガイド
cloud/                         AWS クラウドインフラ
  ingestion/template.yaml      CloudFormation (S3, Kinesis, IAM, Glue)
  ai/image_analyzer/           Lambda: 2段階画像分析
  ai/feedback_recorder/        Lambda: AI精度フィードバック記録
  processing/glue_etl_job.py   Glue ETL ジョブ
docs/                          設計ドキュメント (日英同期)
  ja/, en/                     各言語版
tests/                         テスト (20テスト全パス)
```

## ドキュメント

| ドキュメント | 日本語 | English |
|------------|--------|---------|
| ユースケース調査 | [docs/ja/use-case-research.md](docs/ja/use-case-research.md) | [docs/en/use-case-research.md](docs/en/use-case-research.md) |
| データスキーマ設計 | [docs/ja/data-schema-design.md](docs/ja/data-schema-design.md) | [docs/en/data-schema-design.md](docs/en/data-schema-design.md) |
| セキュリティ設計 | [docs/ja/security-design.md](docs/ja/security-design.md) | [docs/en/security-design.md](docs/en/security-design.md) |
| 運用設計 | [docs/ja/operations-design.md](docs/ja/operations-design.md) | [docs/en/operations-design.md](docs/en/operations-design.md) |
| ビジネスストーリー | [docs/ja/business-story.md](docs/ja/business-story.md) | [docs/en/business-story.md](docs/en/business-story.md) |
| PoC提案テンプレート | [docs/ja/poc-proposal-template.md](docs/ja/poc-proposal-template.md) | [docs/en/poc-proposal-template.md](docs/en/poc-proposal-template.md) |
| FAQ | [docs/ja/faq.md](docs/ja/faq.md) | [docs/en/faq.md](docs/en/faq.md) |
| SORACOM 設定 | [edge/soracom/README_ja.md](edge/soracom/README_ja.md) | [edge/soracom/README.md](edge/soracom/README.md) |

## ライセンス

MIT
