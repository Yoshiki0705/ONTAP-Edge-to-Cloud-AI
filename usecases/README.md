# Use Cases

IoT データのサイロ化を解消し、ONTAP に集約したデータを AWS AI/分析サービスで活用するユースケース集。

## 実装済み

| # | ユースケース | 概要 | ステータス |
|---|------------|------|-----------|
| 1 | [3D Print Quality Monitoring](./3d-print-quality/) | カメラ画像 → ONTAP → Bedrock Vision で印刷品質を自動検査 | ✅ コード実装済（実機テスト待ち） |
| 2 | [ONTAP Telemetry Analytics](./ontap-telemetry-analytics/) | ONTAP REST API → メトリクス収集 → 容量予測・異常検知 | ✅ コード実装済（実機テスト待ち） |
| 3 | [Visual Inspection (Manufacturing)](./visual-inspection/) | 製造品外観検査 → 傷・変色・バリ検出（プロンプト変更のみで再利用） | ✅ テンプレート作成済 |

## 計画中

| # | ユースケース | 概要 | 関連パターン |
|---|------------|------|-------------|
| 3 | Visual Inspection (Manufacturing) | 製造ライン外観検査 → 欠陥分類 | Pattern A (FPolicy) |
| 4 | Inventory AI Stocktaking | 倉庫棚画像 → 在庫カウント | Pattern A (FPolicy) |
| 5 | Environmental Sensor Monitoring | 環境センサー → 時系列分析 | Pattern B (SnapMirror) |
| 6 | Equipment Predictive Maintenance | 振動センサー → 故障予測 | Pattern B (SnapMirror) |

## アーキテクチャパターン

各ユースケースは以下のパターンの組み合わせで構成:

| パターン | データフロー | 用途 |
|---------|------------|------|
| **A: FPolicy → Lambda** | Pi → NFS → ONTAP → FPolicy → Lambda → Bedrock | 画像到着トリガーの即時分析 |
| **B: SnapMirror → S3 AP** | Pi → NFS → ONTAP → SnapMirror → FSx for ONTAP → S3 AP → Athena | バッチ分析・時系列クエリ |
| **C: REST API → 収集** | ONTAP REST API → Pi → NFS → ONTAP | ストレージ自体のテレメトリ |
| **D: FlexCache** | Cloud AI results → FlexCache → Edge ONTAP → Pi | 推論結果のエッジ配信 |

## 関連プロジェクト

FSx for ONTAP S3 Access Points を使ったサーバーレスパターン集（17ユースケース）:

- [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns)
  - [`event-driven-fpolicy`](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/tree/main/event-driven-fpolicy) — FPolicy イベント駆動パターン（本プロジェクトの Pattern A の基盤）
  - [`manufacturing-analytics`](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/tree/main/manufacturing-analytics) — 製造業分析パターン
  - [`logistics-ocr`](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/tree/main/logistics-ocr) — OCR/入出庫パターン
  - [`genai-rag-enterprise-files`](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/tree/main/genai-rag-enterprise-files) — RAG パターン

## ディレクトリ構造

```
usecases/
  README.md                          ← この文書
  3d-print-quality/
    README.md                        ユースケース説明 + アーキテクチャ
    demo-guide.md                    デモ実行手順
    (コードは edge/, cloud/ を参照)
  ontap-telemetry-analytics/
    README.md
    demo-guide.md
```
