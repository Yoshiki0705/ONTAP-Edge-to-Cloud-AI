🌐 [日本語](#日本語) | [English](#english)

---

# 日本語

# Edge-to-Cloud AI

> エッジデバイス（Raspberry Pi、SORACOM）からAWSクラウドへのデータ収集・分析・AI活用パイプライン

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Yoshiki0705/edge-to-cloud-ai/badge)](https://scorecard.dev/viewer/?uri=github.com/Yoshiki0705/edge-to-cloud-ai)

## 概要

IoT/エッジデバイスで収集したセンサーデータや画像を、AWSの分析・AIサービスに連携するリファレンスアーキテクチャです。最初のPoCとして **3Dプリント品質監視** を実装しています。

### アーキテクチャ（2段階AI分析）

```
[Edge]                    [SORACOM]              [AWS Cloud]
Raspberry Pi 5            Flux / Funnel          ┌─────────────────────────────┐
┌──────────────┐          ┌─────────┐           │  S3 Data Lake               │
│ USB Camera   │──60s間隔→│ Cellular│──HTTPS──→ │    ↓                         │
│ (1080p JPEG) │          │ or WiFi │           │  Lambda (2段階分析)          │
└──────────────┘          └─────────┘           │    ├─ Haiku: スクリーニング   │
                                                │    └─ Sonnet: 詳細分析(異常時)│
                                                │    ↓                         │
                                                │  SNS → Slack/Email 通知      │
                                                │    ↓                         │
                                                │  Glue → Athena (SQL分析)     │
                                                │  QuickSight (BI)             │
                                                └─────────────────────────────┘
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
| CloudWatch 監視 | ✅ 設定済 | ダッシュボード + エラーアラーム |
| 予算アラーム | ✅ 設定済 | $50/月上限 |
| Glue Crawler | ✅ 設定済 | 毎朝6時に自動実行 |
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

### AWS インフラデプロイ

```bash
# CloudFormation スタックデプロイ
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
# Raspberry Pi 初回セットアップ
# 詳細: edge/raspberry-pi/SETUP.md

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
      main.py                  Phase 2+: フル機能版
      config.py, capture.py    モジュール群
      buffer.py, uploader.py   オフライン耐性
      health.py                死活監視
      test_prompt.py           Bedrock プロンプトテスター
    sensors/
      ontap_telemetry.py       ONTAP REST API テレメトリ収集
    SETUP.md                   初回セットアップ Playbook
  soracom/                     SORACOM 設定ガイド (日英)
cloud/                         AWS クラウドインフラ
  ingestion/template.yaml      CloudFormation (S3, Kinesis, IAM, Glue)
  ai/image_analyzer/           Lambda: 2段階画像分析
  processing/glue_etl_job.py   Glue ETL ジョブ
docs/                          設計ドキュメント (日英同期)
  ja/, en/
    use-case-research.md       ユースケース調査
    data-schema-design.md      データスキーマ設計
    security-design.md         セキュリティ設計
tests/                         テスト
shared/scripts/                ユーティリティスクリプト
```

## ドキュメント

| ドキュメント | 日本語 | English |
|------------|--------|---------|
| ユースケース調査 | [docs/ja/use-case-research.md](docs/ja/use-case-research.md) | [docs/en/use-case-research.md](docs/en/use-case-research.md) |
| データスキーマ設計 | [docs/ja/data-schema-design.md](docs/ja/data-schema-design.md) | [docs/en/data-schema-design.md](docs/en/data-schema-design.md) |
| セキュリティ設計 | [docs/ja/security-design.md](docs/ja/security-design.md) | [docs/en/security-design.md](docs/en/security-design.md) |
| SORACOM 設定 | [edge/soracom/README_ja.md](edge/soracom/README_ja.md) | [edge/soracom/README.md](edge/soracom/README.md) |
| Pi セットアップ | [edge/raspberry-pi/SETUP.md](edge/raspberry-pi/SETUP.md) | — |

## ライセンス

MIT

---

# English

# Edge-to-Cloud AI

> Data collection, analytics, and AI pipelines from edge devices (Raspberry Pi, SORACOM) to AWS cloud

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Yoshiki0705/edge-to-cloud-ai/badge)](https://scorecard.dev/viewer/?uri=github.com/Yoshiki0705/edge-to-cloud-ai)

## Overview

Reference architecture for connecting IoT/edge device data (sensors, cameras) to AWS analytics and AI services. The first PoC implements **3D print quality monitoring**.

### Architecture (Two-Stage AI Analysis)

```
[Edge]                    [SORACOM]              [AWS Cloud]
Raspberry Pi 5            Flux / Funnel          ┌─────────────────────────────┐
┌──────────────┐          ┌─────────┐           │  S3 Data Lake               │
│ USB Camera   │──60s────→│ Cellular│──HTTPS──→ │    ↓                         │
│ (1080p JPEG) │          │ or WiFi │           │  Lambda (Two-Stage)          │
└──────────────┘          └─────────┘           │    ├─ Haiku: Screening       │
                                                │    └─ Sonnet: Detail (anomaly)│
                                                │    ↓                         │
                                                │  SNS → Slack/Email alert     │
                                                │    ↓                         │
                                                │  Glue → Athena (SQL)         │
                                                │  QuickSight (BI)             │
                                                └─────────────────────────────┘
```

### Cost Optimization

| Approach | Monthly Cost | Description |
|----------|-------------|-------------|
| Single model (Sonnet) | ~$259/month | Analyze all images with high-accuracy model |
| **Two-stage (adopted)** | **~$40/month** | Haiku screening, Sonnet only for suspected anomalies |

### Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| AWS Infrastructure (CFn) | ✅ Deployed | S3, Kinesis, Lambda, IAM, Glue, SNS |
| Lambda (Two-Stage) | ✅ Deployed | Haiku + Sonnet, prompt accuracy 100% |
| CloudWatch Monitoring | ✅ Configured | Dashboard + error alarm |
| Budget Alarm | ✅ Configured | $50/month limit |
| Glue Crawler | ✅ Configured | Daily at 6am |
| Edge Code | ✅ Implemented | Awaiting Pi arrival for testing |
| SORACOM Integration | 📋 Pending | Configure after SIM arrival |
| Hardware Testing | 📋 Pending | After Pi + camera arrival |

### Related Projects

- [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) — FSx for ONTAP S3 Access Points × Lakehouse integrations (parent project)

## Quick Start

### Prerequisites

- AWS CLI v2 + credentials configured
- Python 3.12+
- Bedrock model access enabled (Claude Haiku 4.5 / Sonnet 4.5)

### Deploy AWS Infrastructure

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

### Edge Device Setup

```bash
# Raspberry Pi initial setup
# Details: edge/raspberry-pi/SETUP.md

# Phase 1: Minimal config verification
cd edge/raspberry-pi/camera
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python simple_capture.py --loop
```

## Directory Structure

```
edge/                          Edge device code
  raspberry-pi/
    camera/                    Camera capture system
      simple_capture.py        Phase 1: Minimal script (for Flux)
      main.py                  Phase 2+: Full-featured version
      config.py, capture.py    Modules
      buffer.py, uploader.py   Offline resilience
      health.py                Health monitoring
      test_prompt.py           Bedrock prompt tester
    sensors/
      ontap_telemetry.py       ONTAP REST API telemetry collector
    SETUP.md                   Initial setup playbook
  soracom/                     SORACOM config guide (ja/en)
cloud/                         AWS cloud infrastructure
  ingestion/template.yaml      CloudFormation (S3, Kinesis, IAM, Glue)
  ai/image_analyzer/           Lambda: Two-stage image analysis
  processing/glue_etl_job.py   Glue ETL job
docs/                          Design documents (ja/en synced)
  ja/, en/
    use-case-research.md       Use case research
    data-schema-design.md      Data schema design
    security-design.md         Security design
tests/                         Tests
shared/scripts/                Utility scripts
```

## Documentation

| Document | 日本語 | English |
|----------|--------|---------|
| Use Case Research | [docs/ja/use-case-research.md](docs/ja/use-case-research.md) | [docs/en/use-case-research.md](docs/en/use-case-research.md) |
| Data Schema Design | [docs/ja/data-schema-design.md](docs/ja/data-schema-design.md) | [docs/en/data-schema-design.md](docs/en/data-schema-design.md) |
| Security Design | [docs/ja/security-design.md](docs/ja/security-design.md) | [docs/en/security-design.md](docs/en/security-design.md) |
| SORACOM Setup | [edge/soracom/README_ja.md](edge/soracom/README_ja.md) | [edge/soracom/README.md](edge/soracom/README.md) |
| Pi Setup | [edge/raspberry-pi/SETUP.md](edge/raspberry-pi/SETUP.md) | — |

## License

MIT
