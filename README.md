🌐 **日本語** | [English](README_en.md)

# ONTAP Edge-to-Cloud AI

[![Tests](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai/actions/workflows/test.yml/badge.svg)](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Yoshiki0705/ontap-edge-to-cloud-ai/badge)](https://scorecard.dev/viewer/?uri=github.com/Yoshiki0705/ontap-edge-to-cloud-ai)

> IoT デバイスが生成するデータの分散・サイロ化を、ONTAP への集約 + Kafka/ClickHouse リアルタイム分析 + AWS AI で解消するリファレンスアーキテクチャ。エッジ〜クラウドのデータパイプラインを検証したいエンジニア向け。

> **免責事項**: 本プロジェクトは個人の技術検証であり、所属組織の公式見解・推奨を示すものではありません。

## はじめる

| やりたいこと | ガイド | 所要時間 |
|------------|--------|---------|
| プロジェクト概要を理解する | [FAQ](docs/ja/faq.md) | 5 min |
| AWS インフラをデプロイする | [デプロイガイド](docs/ja/deployment-guide.md) | 30 min |
| エッジデバイスをセットアップする | [Raspberry Pi セットアップ](edge/raspberry-pi/) | 20 min |
| データスキーマを確認する | [データスキーマ設計](docs/ja/data-schema-design.md) | 10 min |
| セキュリティ設計を確認する | [セキュリティ設計](docs/ja/security-design.md) | 15 min |
| Kafka/ClickHouse 連携を理解する | [Kafka 統合設計](docs/ja/kafka-integration.md) | 15 min |

<details><summary>📂 全ドキュメント一覧</summary>

| ドキュメント | 日本語 | English |
|------------|--------|---------|
| ユースケース調査 | [docs/ja/use-case-research.md](docs/ja/use-case-research.md) | [docs/en/use-case-research.md](docs/en/use-case-research.md) |
| データスキーマ設計 | [docs/ja/data-schema-design.md](docs/ja/data-schema-design.md) | [docs/en/data-schema-design.md](docs/en/data-schema-design.md) |
| Kafka 統合設計 | [docs/ja/kafka-integration.md](docs/ja/kafka-integration.md) | [docs/en/kafka-integration.md](docs/en/kafka-integration.md) |
| セキュリティ設計 | [docs/ja/security-design.md](docs/ja/security-design.md) | [docs/en/security-design.md](docs/en/security-design.md) |
| 運用設計 | [docs/ja/operations-design.md](docs/ja/operations-design.md) | [docs/en/operations-design.md](docs/en/operations-design.md) |
| デモシナリオ | [docs/ja/demo-scenarios.md](docs/ja/demo-scenarios.md) | [docs/en/demo-scenarios.md](docs/en/demo-scenarios.md) |
| Databricks 連携 | [docs/ja/databricks-integration.md](docs/ja/databricks-integration.md) | [docs/en/databricks-integration.md](docs/en/databricks-integration.md) |
| FAQ | [docs/ja/faq.md](docs/ja/faq.md) | [docs/en/faq.md](docs/en/faq.md) |
| デプロイガイド | [docs/ja/deployment-guide.md](docs/ja/deployment-guide.md) | [docs/en/deployment-guide.md](docs/en/deployment-guide.md) |
| 学んだこと | [docs/ja/lessons-learned.md](docs/ja/lessons-learned.md) | [docs/en/lessons-learned.md](docs/en/lessons-learned.md) |

</details>

## アーキテクチャ

```
[Edge Devices]              [ONTAP (Aggregation)]       [Real-Time Ops]       [AI / Analytics]
                            FAS/AFF|Select|FSx for ONTAP  On-prem VMs           AWS Cloud
+------------------+        +--------------------+      +---------------+      +------------------+
| Raspberry Pi 5   |--NFS-->| Inspection images  |      | Kafka         |      | Bedrock (GenAI)  |
|   Camera         |        | Sensor CSV         |      |  (events)     |      | Athena (SQL)     |
|   Sensors        |--Kafka>| Equipment logs     |      | ClickHouse    |      | Glue (ETL)       |
+------------------+        | 3D models          |      |  (analytics)  |      | SageMaker (ML)   |
| 3D Printer       |--SMB-->|                    |      +---------------+      +------------------+
+------------------+        | FPolicy (trigger)  |            |                       |
                            | REST API (metrics) |            v                       v
[Connectivity]              | ONTAP S3 (backup)  |      [Dashboards]           [Databricks]
|- Wired LAN (10GbE)        | ARP/AI (protect)   |      Anomaly detection     Unity Catalog
|- Wi-Fi                    | Snapshot (preserve) |      Quality trends        Gold datasets
|- Cellular (option)        +--------------------+      Payload lookup         Feature tables
                                    |
                                    |--SnapMirror--> FSx for ONTAP --> S3 AP --> AWS AI
```

**データの流れ:**
- **ペイロード** (画像、CSV、ログ): エッジ → NFS → ONTAP
- **イベント** (メタデータ): エッジ → Kafka → ClickHouse
- **AI 分析**: ONTAP → S3 AP → Bedrock / Lambda
- **バックアップ**: ClickHouse → ONTAP S3

<details><summary>⚠️ 制約・注意事項</summary>

| 項目 | 内容 | 詳細 |
|------|------|------|
| 実機テスト | エッジデバイス未到着。クラウド側のみ動作確認済み | [FAQ](docs/ja/faq.md) |
| AI 精度 | 合成画像テストのみ (9/9 正解)。実環境は未検証 | [デモシナリオ](docs/ja/demo-scenarios.md) |
| ONTAP 連携 | モックテストのみ。実 ONTAP 環境での検証は未実施 | [運用設計](docs/ja/operations-design.md) |
| S3 AP 制約 | 条件付き書き込み非対応、イベント通知非対応 | [FAQ](docs/ja/faq.md) |
| スケール | 単一デバイス構成のみ検証済み | — |

</details>

<details><summary>📚 関連プロジェクト・記事</summary>

| プロジェクト | 概要 |
|------------|------|
| [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) | FSx for ONTAP S3 AP × Lakehouse 統合 (Kafka + ClickHouse + Databricks 実装) |
| ↳ [manufacturing-data-platform](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/tree/main/integrations/manufacturing-data-platform) | 製造データプラットフォーム連携 |
| [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | FSx for ONTAP S3 AP サーバーレスパターン集 (17 ユースケース) |

</details>

<details><summary>🔧 開発者向け</summary>

```bash
git clone https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai.git
cd ontap-edge-to-cloud-ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```

詳細: [CONTRIBUTING.md](CONTRIBUTING.md) | [TESTING.md](TESTING.md)

</details>

## License

MIT

---

🌐 **日本語** | [English](README_en.md)
