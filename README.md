🌐 **日本語** | [English](README_en.md)

# ONTAP Edge-to-Cloud AI

> 工場や拠点の NAS に眠るデータを、エッジデバイスと AI で活用するためのリファレンスアーキテクチャ

> **免責事項**: 本プロジェクトは個人の技術検証活動であり、所属組織の公式見解・推奨を示すものではありません。特定製品の購入を推奨するものでもありません。

## 解決したい課題

工場や拠点には、検査画像・設備ログ・センサーデータが NAS 上に日々蓄積されています。しかし多くの場合、これらのデータは「保存されているだけ」で分析や AI に活用されていません。

**よくある状況:**
- 検査画像が NAS に数TB あるが、目視確認以外に使われていない
- 設備のログは保存しているが、異常の予兆を見つけられていない
- データをクラウドの AI サービスで分析したいが、全量コピーは現実的でない
- エッジデバイス（カメラ、センサー）のデータを既存のストレージ基盤に統合したい

## このプロジェクトのアプローチ

既存の ONTAP NAS をデータの集約先として活用し、エッジデバイスが収集したデータを NFS/SMB で書き込み、ONTAP の機能を通じてクラウド AI/分析サービスに接続します。

**ポイント:**
- データを S3 に全量コピーしない（ONTAP の S3 Access Points で直接アクセス）
- 既存のファイルワークフロー（NFS/SMB）を変えない
- ファイル到着をトリガーに自動分析（FPolicy）
- エッジ → クラウドの同期は差分転送（SnapMirror）

### 対象読者

- **既存 ONTAP ユーザー**: NAS 上のデータを AI/分析で活用したい方
- **IoT/エッジ開発者**: エッジデバイスのデータを既存ストレージ基盤に統合したい方
- **AWS ユーザー**: S3 以外のストレージソースから Athena/Bedrock/SageMaker を使いたい方

### ONTAP がない場合は？

このアーキテクチャは ONTAP を前提としていますが、コアのパターン（エッジ収集 → 集約 → AI分析）は他のストレージでも実現可能です:

| ストレージ | 実現可能なこと | ONTAP を使う場合の追加価値 |
|-----------|--------------|--------------------------|
| S3 直接 | エッジ → S3 → Athena/Bedrock | — (最もシンプル) |
| EFS | NFS マウント → Lambda/Bedrock | — |
| **ONTAP** | 上記すべて + 以下 | FPolicy (イベント駆動)、SnapMirror (差分同期)、Multi-Protocol (NFS+SMB+S3 同一データ)、Snapshot (データ保全)、ARP/AI (セキュリティ) |

ONTAP の追加価値が活きるのは:
- 既に ONTAP/NAS があり、そこにデータが蓄積されている場合
- NFS と SMB の両方でアクセスする必要がある場合
- データをクラウドにコピーせず、S3 API で直接分析したい場合
- ファイル到着をトリガーに自動処理したい場合

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

SA/SE として顧客の現場を訪問する中で、「NAS にデータはあるが活用できていない」という声を繰り返し聞きました。2024-2025年に以下の技術が揃ったことで、この課題に対する実用的な解決策が初めて実現可能になったと考え、検証を始めました:

- **FSx for ONTAP S3 Access Points** (2025年GA): データコピーなしで S3 API アクセス
- **SORACOM Flux** (2024年GA): 低コードでカメラ × AI パイプライン構築
- **Claude Vision / マルチモーダル AI**: 汎用プロンプトで産業用画像判定が実用精度に

最初の PoC として **3Dプリント品質監視** を選びました（視覚的にわかりやすく、失敗が頻繁に起きるためテストデータが集まりやすい）。

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
| PoC計画テンプレート | [docs/ja/poc-proposal-template.md](docs/ja/poc-proposal-template.md) | [docs/en/poc-proposal-template.md](docs/en/poc-proposal-template.md) |
| FAQ | [docs/ja/faq.md](docs/ja/faq.md) | [docs/en/faq.md](docs/en/faq.md) |

## 関連プロジェクト

- [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) — FSx for ONTAP S3 AP × Lakehouse 統合

## ライセンス

MIT
