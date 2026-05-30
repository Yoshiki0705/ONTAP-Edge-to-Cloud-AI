🌐 **日本語** | [English](README_en.md)

# ONTAP Edge-to-Cloud AI

[![Tests](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai/actions/workflows/test.yml/badge.svg)](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Yoshiki0705/ontap-edge-to-cloud-ai/badge)](https://scorecard.dev/viewer/?uri=github.com/Yoshiki0705/ontap-edge-to-cloud-ai)

**TL;DR**: 現場の IoT デバイス（カメラ、センサー等）が生成するデータは、デバイスごと・拠点ごとに分散しがちです。ONTAP にデータを集約し、S3 Access Points 経由で AWS AI/分析サービスに接続することで、組織横断でのデータ活用を実現する仕組みを検証しています。

> **免責事項**: 本プロジェクトは個人の技術検証活動であり、所属組織の公式見解・推奨を示すものではありません。特定製品の購入を推奨するものでもありません。

## 解決したい課題

工場や拠点では、IoT デバイス（カメラ、センサー、制御PC 等）がデータを日々生成しています。しかし多くの場合、これらのデータはデバイスごと・拠点ごとに分散し、サイロ化しています。

**よくある状況:**
- カメラの画像はプリンター内蔵クラウドに、センサーデータは Pi の SD カードに、設備ログは Windows PC にバラバラに保存
- 拠点 A と拠点 B のデータを横断して分析する手段がない
- 個別のデバイスデータは見えるが、全体像（相関分析、トレンド）が把握できない
- AI で分析したいが、データが散在していてパイプラインが組めない

## このプロジェクトのアプローチ

分散した IoT データを ONTAP に集約し、AWS AI/分析サービスで組織横断のデータ活用を可能にします。

**ポイント:**
- エッジデバイスは NFS/SMB で ONTAP に書き込むだけ（デバイス側の実装はシンプル）
- ONTAP がデータの集約点となり、サイロ化を解消
- S3 Access Points で集約データに AWS サービスから直接アクセス（データコピー不要）
- SnapMirror で拠点間・エッジ→クラウドのデータ同期
- FPolicy でファイル到着をトリガーに自動分析

### 対象読者

- **IoT/エッジ開発者**: デバイスが生成するデータの集約・活用方法を探している方
- **データ活用推進者**: 分散したデータのサイロ化を解消し、組織横断で分析したい方
- **既存 ONTAP ユーザー**: ONTAP を IoT データの集約先として活用したい方
- **AWS ユーザー**: S3 以外のストレージソースから Athena/Bedrock/SageMaker を使いたい方

### ONTAP がない場合は？

このアーキテクチャは ONTAP を前提としていますが、コアのパターン（エッジ収集 → 集約 → AI分析）は他のストレージでも実現可能です:

| ストレージ | データフロー | 特徴 | 制約 |
|-----------|------------|------|------|
| **S3 直接** | エッジ → S3 → Athena/Bedrock | 最もシンプル。セットアップが容易。AWS ネイティブ統合。S3 Object Lock で改ざん防止。CloudFront でエッジキャッシュ配信可能 | NFS/SMB アクセス不可。既存ファイルワークフローとの統合に別途工夫が必要。イベント駆動は S3 Event Notifications で実現 |
| **EFS** | エッジ → NFS → EFS → Lambda/Bedrock | NFS マウント可能。Linux デバイスと親和性が高い。自動スケール。AWS Backup で保護 | SMB 非対応。S3 API 直接アクセス不可。イベント駆動は Lambda + CloudWatch で構築。リージョン間レプリケーションは EFS Replication で対応 |
| **ONTAP** | エッジ → NFS/SMB → ONTAP → S3 AP → AWS AI | NFS + SMB + S3 を同一データで提供。FPolicy でファイル到着トリガー。SnapMirror で差分同期。FlexCache でリモート拠点へ低遅延配信。ARP/AI でランサムウェア異常検知・自動 Snapshot 保護 | ONTAP 環境が必要。S3 AP は条件付き書き込み非対応。運用に ONTAP の知識が必要 |

**どれを選ぶべきか:**
- データがまだない / 新規構築 → **S3 直接**が最もシンプル
- Linux デバイスから NFS で書きたい / VPC 内で完結 → **EFS**
- 既に ONTAP/NAS にデータがある / NFS+SMB 両方必要 / データコピーを避けたい → **ONTAP**

## アーキテクチャ

```
[エッジデバイス]                  [ONTAP (データ集約)]              [AI / 分析]
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
[接続オプション]                    │  Snapshot (保全)    │          │  GPU サーバー     │
├─ 有線 LAN (10GbE)              └────────────────────┘          │  Pi エッジ推論    │
├─ Wi-Fi                                                         └──────────────────┘
├─ SORACOM セルラー (オプション)
└─ SORACOM S+ Camera (オプション)
```

### エッジデバイス（選択肢）

| デバイス | 接続 | 用途 |
|---------|------|------|
| Raspberry Pi 5 | 有線 LAN (NFS) | カメラ撮影、センサー収集、エッジ推論 |
| USB カメラ (4K) | Pi 経由 | 外観検査、品質監視 |
| CSI カメラ (NoIR V2) | Pi 経由 | 暗所撮影、近赤外線 |
| 3D プリンター | 有線 LAN (SMB) | 印刷データ保存 |
| SORACOM S+ Camera | セルラー (オプション) | 有線LANがない現場 |
| SORACOM Air + Pi | セルラー (オプション) | 有線LANがない現場の接続 |
| 産業用センサー | Pi GPIO / I2C / SPI | 温湿度、振動、電流 |

### ONTAP プラットフォーム（選択肢）

| プラットフォーム | 配置 | 特徴 |
|----------------|------|------|
| FAS/AFF | オンプレミス | ハードウェアアプライアンス |
| ONTAP Select | オンプレミス / VM | ソフトウェア定義。汎用サーバーや VM 上で動作 |
| FSx for ONTAP | AWS クラウド | フルマネージド。SnapMirror 先、S3 AP 対応 |

## このプロジェクトを作った動機

SA/SE として顧客の現場を訪問する中で、「IoT デバイスやセンサーのデータが拠点ごと・デバイスごとにバラバラで、横断的に分析できない」という声を繰り返し聞きました。データ自体は生成されているのに、サイロ化によって活用できていない状況です。

2024-2025年に以下の技術が揃ったことで、「集約 → 横断分析」を低コストで実現できるようになったと考え、検証を始めました:

- **FSx for ONTAP S3 Access Points** (2025年GA): 集約したデータにデータコピーなしで S3 API アクセス
- **Claude Vision / マルチモーダル AI の成熟**: 汎用プロンプトで産業用画像判定が実用精度に到達
- **Raspberry Pi 5 (16GB)**: エッジでの前処理・軽量推論が現実的な性能に

最初の PoC として **3Dプリント品質監視** を選びました（視覚的にわかりやすく、失敗が頻繁に起きるためテストデータが集まりやすい）。

## 現在の制約と限界

- **実機テスト未完了**: エッジデバイス（Raspberry Pi、カメラ）が未到着のため、エンドツーエンドの実機テストは未実施です。クラウド側（Lambda、Bedrock）は動作確認済み。
- **AI 精度は合成テストのみ**: プロンプトテストは公開画像と合成画像で実施（9/9 正解）。実環境（照明、カメラ角度、フィラメント色）での精度は未検証。
- **ONTAP 連携は設計のみ**: FPolicy、SnapMirror、S3 AP の連携コードは実装済みですが、実 ONTAP 環境での動作確認は未実施（モックテストのみ）。
- **単一デバイス構成**: 複数デバイスの同時運用、スケールアウトは未検証。

## ここまでで学んだこと

- **2段階AI分析でコスト85%削減**: 全画像を高精度モデルで分析すると月$259。Haiku でスクリーニングし異常疑いのみ Sonnet に回すと月$40。この設計パターンは他のAIパイプラインにも応用可能。
- **プロンプトだけで産業用画像判定が実用精度に達する**: カスタムモデル学習なしで、Claude Vision のプロンプトのみで 3Dプリント欠陥を 9/9 正解。ただし実環境での検証はこれから。
- **FSxN S3 Access Points の制約**: 条件付き書き込み非対応、イベント通知非対応。Iceberg/Delta Lake の直接書き込みはできない。FPolicy で補完する設計が必要。
- **ONTAP REST API は IoT テレメトリ収集に十分使える**: パフォーマンスメトリクス、容量、健全性を 1分間隔で収集可能。ポーリングベースだが PoC には十分。

## 現在のステータス

| コンポーネント | ステータス | 備考 |
|--------------|-----------|------|
| AWS インフラ (CFn) | ✅ デプロイ済 | S3, Kinesis, Lambda, IAM, Glue, SNS |
| Lambda (2段階AI分析) | ✅ デプロイ済 | Haiku スクリーニング + Sonnet 詳細 (コスト85%削減) |
| ONTAP テレメトリ収集 | ✅ 実装済 | REST API ポーリング (モックE2Eテスト済) |
| エッジカメラコード | ✅ 実装済 | Pi到着後にテスト |
| 設計ドキュメント | ✅ 完成 | 日英同期 8ドキュメント |
| 実機テスト | 📋 ハードウェア待ち | Pi + カメラ + ONTAP 到着後 |

## クイックスタート

### 前提条件

- AWS CLI v2 + 認証設定済み
- Python 3.12+
- Bedrock モデルアクセス有効化
- ONTAP 9.13.1+（FPolicy、REST API、S3 AP）

### デプロイ

```bash
# AWS インフラ
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides Environment=poc \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1

# エッジデバイス → edge/raspberry-pi/SETUP.md
```

## ドキュメント

| ドキュメント | 日本語 | English |
|------------|--------|---------|
| ユースケース調査 | [docs/ja/use-case-research.md](docs/ja/use-case-research.md) | [docs/en/use-case-research.md](docs/en/use-case-research.md) |
| データスキーマ設計 | [docs/ja/data-schema-design.md](docs/ja/data-schema-design.md) | [docs/en/data-schema-design.md](docs/en/data-schema-design.md) |
| セキュリティ設計 | [docs/ja/security-design.md](docs/ja/security-design.md) | [docs/en/security-design.md](docs/en/security-design.md) |
| 運用設計 | [docs/ja/operations-design.md](docs/ja/operations-design.md) | [docs/en/operations-design.md](docs/en/operations-design.md) |
| FAQ | [docs/ja/faq.md](docs/ja/faq.md) | [docs/en/faq.md](docs/en/faq.md) |

## 関連プロジェクト

- [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) — FSx for ONTAP S3 AP × Lakehouse 統合

## ライセンス

MIT
