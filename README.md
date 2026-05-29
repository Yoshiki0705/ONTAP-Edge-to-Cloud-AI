🌐 **日本語** | [English](README_en.md)

# ONTAP Edge-to-Cloud AI

> NetApp ONTAP をデータハブとして、エッジデバイスで収集した現場データを集約し、AI/分析で活用するリファレンスアーキテクチャ

## 概要

ONTAP（FAS/AFF、ONTAP Select、または FSx for ONTAP）をデータの集約先として、エッジデバイス（Raspberry Pi、カメラ、センサー等）が収集した現場データを NFS/SMB で書き込み、ONTAP の機能（FPolicy、SnapMirror、S3 Access Points）を通じて AWS AI/分析サービスに連携するパイプラインです。

最初の PoC として **3Dプリント品質監視** を実装しています。

## アーキテクチャ

```
[エッジデバイス]                  [ONTAP データハブ]                [AI / 分析]
                                 FAS/AFF | ONTAP Select | FSxN
┌────────────────┐               ┌────────────────────┐          ┌──────────────────┐
│ Raspberry Pi 5 │──NFS─────────→│                    │          │ AWS              │
│  カメラ         │               │  検査画像           │─S3 AP──→│  Bedrock (GenAI) │
│  センサー       │               │  センサーCSV        │          │  SageMaker (ML)  │
├────────────────┤               │  設備ログ           │─SnapMirror→ FSxN ─S3 AP──→│
│ 3Dプリンター    │──SMB─────────→│  3Dモデル           │          │  Athena (SQL)    │
├────────────────┤               │                    │          │  Glue (ETL)      │
│ USB カメラ     │──NFS─────────→│  FPolicy (イベント)  │          │  QuickSight (BI) │
└────────────────┘               │  REST API (テレメトリ)│          ├──────────────────┤
                                 │  ARP/AI (保護)      │          │ ローカル AI       │
[エッジ接続オプション]             │  Snapshot (保全)    │          │  AIDE GPUサーバー │
├─ 有線 LAN (10GbE)              └────────────────────┘          │  Pi エッジ推論    │
├─ Wi-Fi                                                         └──────────────────┘
├─ SORACOM セルラー (オプション)
└─ SORACOM S+ Camera (オプション)
```

### データフロー

1. **エッジ → ONTAP**: デバイスが NFS/SMB で ONTAP に直接書き込み（LAN 経由）
2. **ONTAP → AI/分析**: FPolicy イベント駆動、SnapMirror 同期、S3 AP 経由で AWS サービスに接続
3. **AI 結果 → ONTAP**: 推論結果を ONTAP に書き戻し、エッジデバイスが参照

### ONTAP がデータハブである理由

| 機能 | 役割 |
|------|------|
| **Multi-Protocol** | NFS (Linux/Pi) + SMB (Windows/プリンター) + S3 (AWS) を同一データで |
| **FPolicy** | ファイル到着をトリガーに自動分析パイプラインを起動 |
| **SnapMirror** | エッジ ONTAP → クラウド FSxN への帯域効率の良い同期 |
| **S3 Access Points** | ONTAP/FSxN 上のデータに S3 API で直接アクセス（データコピー不要） |
| **Snapshot** | 任意時点のデータセットを固定（AI 学習データ、監査） |
| **ARP/AI** | IoT デバイス侵害時のランサムウェア検知・自動保護 |
| **FlexCache** | クラウドの AI 結果をエッジで低遅延参照 |

### エッジデバイス（選択肢）

| デバイス | 接続 | 用途 |
|---------|------|------|
| Raspberry Pi 5 (16GB) | 有線 LAN (NFS) | カメラ撮影、センサー収集、エッジ推論 |
| USB カメラ (4K) | Pi 経由 | 外観検査、品質監視 |
| CSI カメラ (NoIR V2) | Pi 経由 | 暗所撮影、近赤外線 |
| 3D プリンター | 有線 LAN (SMB) | 印刷データ保存、ステータス連携 |
| SORACOM S+ Camera | セルラー (オプション) | 有線LANがない現場のカメラ |
| SORACOM Air + Pi | セルラー (オプション) | 有線LANがない現場の接続 |
| 産業用センサー | Pi GPIO / I2C / SPI | 温湿度、振動、電流、圧力 |

### ONTAP プラットフォーム（選択肢）

| プラットフォーム | 配置 | 特徴 |
|----------------|------|------|
| FAS/AFF | オンプレミス | ハードウェアアプライアンス。エントリーからハイエンドまで |
| ONTAP Select | オンプレミス / VM | ソフトウェア定義。汎用サーバーや VM 上で動作 |
| FSx for ONTAP | AWS クラウド | フルマネージド。S3 AP、SnapMirror 先として |

### AI/分析（選択肢）

| サービス | 配置 | 用途 |
|---------|------|------|
| Amazon Bedrock | クラウド | 画像AI (Claude Vision)、レポート生成 |
| Amazon SageMaker | クラウド | カスタム ML モデル（予知保全、異常検知） |
| Amazon Athena | クラウド | SQL 分析（S3 AP 経由で ONTAP データを直接クエリ） |
| AWS Glue | クラウド | ETL、データカタログ |
| AIDE GPU サーバー | ローカル | オンプレミス AI 推論（大規模モデル） |
| Pi エッジ推論 | エッジ | TensorFlow Lite / ONNX Runtime（軽量モデル） |

## 現在のステータス

| コンポーネント | ステータス | 備考 |
|--------------|-----------|------|
| AWS インフラ (CFn) | ✅ デプロイ済 | S3, Kinesis, Lambda, IAM, Glue, SNS |
| Lambda (2段階AI分析) | ✅ デプロイ済 | Haiku スクリーニング + Sonnet 詳細分析 |
| ONTAP テレメトリ収集 | ✅ 実装済 | REST API ポーリング (モックE2Eテスト済) |
| エッジカメラコード | ✅ 実装済 | Pi到着後にテスト |
| 設計ドキュメント | ✅ 完成 | 日英同期 8ドキュメント |
| 実機テスト | 📋 ハードウェア待ち | Pi + カメラ + ONTAP 到着後 |

## クイックスタート

### 前提条件

- AWS CLI v2 + 認証設定済み
- Python 3.12+
- Bedrock モデルアクセス有効化（Claude Haiku 4.5 / Sonnet 4.5）
- ONTAP 9.13.1+（FPolicy、REST API、S3 AP）

### AWS インフラデプロイ

```bash
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides Environment=poc \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### エッジデバイスセットアップ

```bash
# Raspberry Pi 初回セットアップ → edge/raspberry-pi/SETUP.md
cd edge/raspberry-pi/camera
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python simple_capture.py --loop
```

## ディレクトリ構成

```
edge/                          エッジデバイスコード
  raspberry-pi/
    camera/                    カメラキャプチャ → ONTAP NFS 書き込み
    sensors/                   ONTAP REST API テレメトリ収集
    SETUP.md                   初回セットアップ Playbook
  soracom/                     SORACOM 設定ガイド (オプション)
cloud/                         AWS クラウドインフラ
  ingestion/template.yaml      CloudFormation
  ai/                          Lambda (画像分析、フィードバック記録)
  processing/                  Glue ETL
docs/                          設計ドキュメント (日英同期)
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

## 関連プロジェクト

- [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) — FSx for ONTAP S3 Access Points × Lakehouse 統合（親プロジェクト）

## ライセンス

MIT
