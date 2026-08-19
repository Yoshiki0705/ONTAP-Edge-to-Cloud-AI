# ONTAP × IoT × AWS Analytics/AI ユースケース調査

> 作成日: 2026-05-29
> プロジェクト: edge-to-cloud-ai
> 親プロジェクト: [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations)

---

## 1. 調査概要

現場の IoT デバイス（Raspberry Pi、カメラ、センサー等）が生成するデータは、デバイスごと・拠点ごとに分散しサイロ化しやすい。本調査では、ONTAP（FAS/AFF、ONTAP Select、FSx for ONTAP）をデータ集約先として活用し、AWS AI/分析サービスで組織横断のデータ活用を実現するパターンを整理した。

**調査で確認したこと:**

1. **ONTAP の多層的活用**: FPolicy によるイベント駆動連携、SnapMirror によるエッジ→クラウド同期、FlexCache による低遅延キャッシュ、ARP/AI によるセキュリティ、S3 Access Points による AWS サービス直接連携の5つの軸で活用可能
2. **FPolicy イベント駆動パイプライン**: エッジデバイスが NFS/SMB で ONTAP に書き込むだけで、FPolicy が Lambda をトリガーし Bedrock 分析を自動実行。デバイス側にクラウド連携コードが不要
3. **FSx for ONTAP S3 AP の活用パターン**: エッジで収集したデータの集約先として FSx for ONTAP を使い、S3 AP 経由で Athena/Glue/Bedrock/SageMaker に直接接続することで、データコピーなしに横断分析が可能
4. **PoC 構成例**: Raspberry Pi 5 + カメラ + 3Dプリンター + ONTAP の組み合わせで、データ集約 → AI 分析の一連のフローを小規模に検証可能

---

## 2. アーキテクチャパターン一覧

### パターン A: エッジ画像収集 → ONTAP → FPolicy → クラウドAI分析

```
[Edge]                     [ONTAP]                  [Cloud (AWS)]
Raspberry Pi 5             On-premises
+------------------+       +------------------+     +-------------------------+
| Camera module    |--NFS->| NFS Volume       |     |                         |
| (NoIR V2/BRIO)  |       |   |              |     | Lambda                  |
|                  |       | FPolicy (detect) |---->|   |                     |
| Pre-process:     |       |   |              |     | Bedrock (Claude Vision) |
|  - Resize        |       | Lambda trigger   |     | Rekognition             |
|  - JPEG compress |       +------------------+     |   |                     |
|  - Timestamp     |                                | DynamoDB (results)      |
+------------------+                                | SNS (alerts)            |
                                                    +-------------------------+
```

**適用ユースケース**: 外観検査、3Dプリント品質監視、在庫画像管理、安全装備確認

### パターン B: センサーデータ → ONTAP → SnapMirror → クラウド分析

```
[Edge]                     [ONTAP]                  [Cloud (AWS)]
Raspberry Pi 5             On-premises              FSx for ONTAP
+------------------+       +------------------+     +-------------------------+
| Sensors          |--NFS->| NFS Volume       |     | FSx for ONTAP Volume             |
|  - Temp/Humidity |       |   |              |     |   | S3 Access Point     |
|  - Vibration     |       | SnapMirror ------|--->| Athena (SQL)            |
|  - Current       |       | (incremental)    |     | Glue ETL                |
|  - Pressure      |       +------------------+     | SageMaker (prediction)  |
|                  |                                | CloudWatch (alerts)     |
| Pre-process:     |                                | QuickSight (BI)         |
|  - Aggregation   |                                +-------------------------+
|  - Outlier filter|
+------------------+
```

**適用ユースケース**: 設備予知保全、環境モニタリング、空調最適化

### パターン C: ONTAP イベント駆動 → クラウド処理

```
[ONTAP]                              [Cloud (AWS)]
On-premises
+---------------------+              +-------------------------+
| FPolicy             |--Lambda----->| Lambda                  |
|  - File create      |  trigger     |   |                     |
|  - File modify      |              | Step Functions          |
|  - File delete      |              |   +-- Glue (ETL)        |
|                     |              |   +-- Bedrock (analysis) |
| REST API            |              |   +-- SNS (notify)       |
|  - Performance      |              |                         |
|  - Capacity         |              | FSx for ONTAP (SnapMirror dest)  |
|  - Health           |              +-------------------------+
+---------------------+
         ^
         | NFS/SMB writes
+---------------------+
| Raspberry Pi 5      |
| (sensors/camera)    |
+---------------------+
```

**適用ユースケース**: ファイル到着トリガーの自動処理、ストレージ健全性監視、データライフサイクル管理

### パターン D: SnapMirror/FlexCache によるハイブリッドデータ同期

```
[On-premises]                                       [Cloud (AWS)]
ONTAP                                               FSx for ONTAP
+---------------------+                             +-------------------------+
| Factory data        |                             | FSx for ONTAP Volume             |
|  - Inspection imgs  |--SnapMirror (async)-------->|   | S3 Access Point     |
|  - Sensor CSV       |                             | Athena (SQL)            |
|  - Equipment logs   |                             | Glue (ETL/catalog)      |
|                     |                             | Bedrock (RAG)           |
| FlexCache           |<----------------------------| AI inference results    |
|  (ref results)      |                             | SageMaker model output  |
+---------------------+                             +-------------------------+
```

**適用ユースケース**: 大容量データの段階的クラウド移行、エッジでのAI結果参照、DR/BCP

---

## 3. 業界別ユースケース詳細

### 3.1 製造業

#### UC-M1: 3Dプリント品質監視

> **IoT分類**: 後付けIoT（既存の3Dプリンターに外付けカメラを追加）
> **制約**: プリンター内部への組み込み不可、プリンターAPIアクセスはベンダー依存、電源はUSB-C（Pi）+ USB（カメラ）で独立供給

| 項目 | 内容 |
|------|------|
| **概要** | FDM 3Dプリンターの印刷中にRaspberry Pi + カメラで定期撮影し、Bedrock Claude Vision で品質異常を検出 |
| **エッジ機材** | Raspberry Pi 5 (16GB) + Logitech BRIO 4K（照明環境下での高解像度撮影に適する。NoIR カメラは暗所/近赤外用途向き） |
| **データフロー** | Pi → NFS → ONTAP → FPolicy → Lambda → Bedrock Claude Vision → SNS通知 |
| **ONTAP連携** | 印刷用3Dモデル(STL/3MF)をONTAP NFS共有に保存、FPolicyで新規ファイル検知→自動印刷キュー投入 |
| **AI活用** | Claude Vision: 糸引き、層間剥離、ノズル詰まりの視覚的検出 |
| **期待される効果** | 無人印刷時の失敗早期検知、フィラメント浪費削減、印刷成功率向上 |
| **帯域見積** | 30秒間隔撮影 × 1080p JPEG (約300KB/枚) = 約600KB/分 = 約36MB/時。有線LAN経由では帯域制約なし。セルラー利用時: 約¥50-100/日 (SORACOM plan-D) |
| **成功指標** | 検出精度 ≥80%、キャプチャ→アラート ≤60秒、誤検知率 ≤10% |

#### UC-M2: 設備振動モニタリング + 予知保全

| 項目 | 内容 |
|------|------|
| **概要** | ONTAPストレージのディスクシェルフ振動や設備の振動をセンサーで収集し、異常パターンを学習 |
| **エッジ機材** | Raspberry Pi 5 + ADXL345加速度センサー + SORACOM SIM |
| **データフロー** | Pi → NFS → ONTAP → SnapMirror → FSx for ONTAP → S3 AP → SageMaker |
| **ONTAP連携** | ONTAP REST API でディスクIOPS/レイテンシを同時収集、相関分析 |
| **AI活用** | SageMaker: 時系列異常検知モデル (Random Cut Forest)、Bedrock: 根本原因診断レポート生成 |
| **期待される効果** | 計画外ダウンタイム削減、部品交換の最適タイミング予測 |

#### UC-M3: 外観検査自動化

| 項目 | 内容 |
|------|------|
| **概要** | 製造ラインの完成品をカメラで撮影し、傷・変色・寸法異常を自動検出 |
| **エッジ機材** | Raspberry Pi 5 + Logitech BRIO 4K (高解像度) |
| **データフロー** | Pi → NFS → ONTAP → FPolicy → Lambda → Rekognition Custom Labels / Bedrock |
| **ONTAP連携** | 検査画像をONTAPに保存（NFS）、SnapMirrorでFSx for ONTAPに同期、S3 APでAthena分析 |
| **AI活用** | Rekognition Custom Labels: 欠陥分類、Bedrock: 検査レポート自動生成 |
| **期待される効果** | 検査工程の自動化、人的ミス削減、トレーサビリティ確保 |

### 3.2 物流・倉庫

#### UC-L1: 在庫画像管理 + AI棚卸し

| 項目 | 内容 |
|------|------|
| **概要** | 倉庫内の棚をカメラで定期撮影し、在庫数量・配置をAIで自動認識 |
| **エッジ機材** | Raspberry Pi 5 + Logitech BRIO 4K |
| **データフロー** | Pi → NFS → ONTAP → FPolicy → Lambda → Bedrock Claude Vision |
| **ONTAP連携** | 在庫マスターデータをONTAP NFS上で管理、FlexCacheでエッジ拠点に配信 |
| **AI活用** | Claude Vision: 棚の在庫数カウント、欠品検知、配置異常検出 |
| **期待される効果** | 棚卸し工数削減、リアルタイム在庫可視化、欠品アラート |

#### UC-L2: 入出庫トラッキング

| 項目 | 内容 |
|------|------|
| **概要** | 入出庫ゲートのカメラで荷物ラベルを読み取り、自動記録 |
| **エッジ機材** | Raspberry Pi 5 + カメラ |
| **データフロー** | Pi → NFS → ONTAP → FPolicy → Lambda → Rekognition (OCR) → DynamoDB |
| **ONTAP連携** | 出荷伝票PDFをONTAPに保存、FPolicyで新規ファイル検知→自動OCR処理 |
| **AI活用** | Rekognition: テキスト検出(バーコード/QR/ラベル)、Bedrock: 伝票内容の構造化 |
| **期待される効果** | 手入力ミス削減、入出庫リードタイム短縮、トレーサビリティ |

### 3.3 農業・環境

#### UC-A1: 環境センサーモニタリング

| 項目 | 内容 |
|------|------|
| **概要** | 圃場の温湿度・土壌水分・照度を定期収集し、生育環境を最適化 |
| **エッジ機材** | Raspberry Pi 5 + DHT22 + 土壌水分センサー + SORACOM SIM |
| **データフロー** | Pi → NFS → ONTAP → SnapMirror → FSx for ONTAP → S3 AP → Athena |
| **ONTAP連携** | 過去の気象データ・収穫データをONTAPに蓄積、SnapMirrorでFSx for ONTAPに同期しAthena分析 |
| **AI活用** | SageMaker: 収穫量予測モデル、Bedrock: 栽培アドバイス生成 |
| **期待される効果** | 収穫量最適化、水・肥料の効率化、異常気象への早期対応 |

#### UC-A2: 画像による生育管理

| 項目 | 内容 |
|------|------|
| **概要** | 定点カメラで作物の生育状況を撮影し、病害虫・生育不良を早期検出 |
| **エッジ機材** | Raspberry Pi 5 + NoIR カメラ V2 (近赤外線で植生指数計測) |
| **データフロー** | Pi → NFS → ONTAP → FPolicy → Lambda → Bedrock Claude Vision |
| **ONTAP連携** | 時系列画像アーカイブをONTAPに保存、年次比較分析に活用 |
| **AI活用** | Claude Vision: 病害虫検出・生育ステージ判定、NDVI算出 |
| **期待される効果** | 病害虫の早期発見、農薬使用量最適化、収穫タイミング予測 |

### 3.4 ビル管理

#### UC-B1: 空調・電力モニタリング

| 項目 | 内容 |
|------|------|
| **概要** | ビル各フロアの温湿度・電力消費をリアルタイム収集し、空調制御を最適化 |
| **エッジ機材** | Raspberry Pi 5 + 温湿度センサー + CT電流センサー + SORACOM SIM |
| **データフロー** | Pi → NFS → ONTAP → SnapMirror → FSx for ONTAP → S3 AP → Athena + QuickSight |
| **ONTAP連携** | BMS(ビル管理システム)のログをONTAPに集約、長期トレンド分析 |
| **AI活用** | SageMaker: 電力需要予測、Bedrock: 省エネレポート自動生成 |
| **期待される効果** | 電力コスト削減(10-30%)、快適性維持、カーボンフットプリント可視化 |

#### UC-B2: 設備異常検知（音声）

| 項目 | 内容 |
|------|------|
| **概要** | 空調機器・エレベーター等の動作音をマイクで収集し、異常音を検知 |
| **エッジ機材** | Raspberry Pi 5 + USBマイク |
| **データフロー** | Pi (エッジ推論: 異常スコア算出) → NFS → ONTAP → SnapMirror → FSx for ONTAP → S3 AP → SageMaker |
| **ONTAP連携** | 音声データアーカイブをONTAPに保存、正常/異常パターンの学習データとして活用 |
| **AI活用** | エッジ: TensorFlow Lite (異常スコア)、クラウド: SageMaker (モデル再学習) |
| **期待される効果** | 設備故障の予兆検知、保守コスト削減、テナント満足度向上 |

---

## 4. ONTAP 機能の IoT/エッジ文脈での活用パターン

### 4.1 SnapMirror: エッジ→クラウドデータ同期

| 特性 | IoT/エッジ文脈での価値 |
|------|----------------------|
| ブロックレベル差分転送 | 帯域制約のあるエッジ拠点から効率的にデータ同期 |
| スケジュール制御 | 夜間バッチ同期でセルラー帯域を節約 |
| 複数宛先 | 1つのエッジONTAPから複数リージョンのFSx for ONTAPに同期可能 |
| Snapshot連携 | 任意時点のデータセットでAI学習データを固定 |

**活用シナリオ**: 工場のONTAPで日中に蓄積された検査画像・センサーCSVを、夜間にSnapMirrorでFSx for ONTAPに同期。翌朝にはAthena/SageMakerで分析可能。

> **RPO目安**: スケジュール設定により RPO 1時間〜24時間で調整可能。セルラー回線経由の場合、帯域制約から RPO 8-24時間が現実的。有線接続環境では RPO 1時間以下も可能。

### 4.2 FlexCache: エッジでの低遅延データアクセス

| 特性 | IoT/エッジ文脈での価値 |
|------|----------------------|
| 読み取りキャッシュ | クラウドのAI推論結果をエッジで低遅延参照 |
| 書き込み透過 | エッジからの書き込みが自動的にオリジンに反映 |
| グローバル一貫性 | 複数拠点で同一データセットを参照可能 |

**活用シナリオ**: クラウドで学習したAIモデルの推論結果（良品/不良品判定閾値等）をFlexCacheでエッジONTAPに配信。エッジのRaspberry Piがリアルタイムに参照。

> **注意**: FlexCache の書き込みはオリジンボリュームへの write-around 動作となるため、書き込みにはWANレイテンシが発生する。IoTの書き込み主体ワークロードでは、ローカルボリュームへの書き込み + SnapMirror同期の方が適切な場合がある。FlexCache は読み取り主体のユースケース（モデル配信、マスターデータ参照）に最適。

### 4.3 FPolicy: イベント駆動データ連携

| 特性 | IoT/エッジ文脈での価値 |
|------|----------------------|
| ファイル操作通知 | 新規ファイル到着を即座に検知し処理パイプライン起動 |
| フィルタリング | 拡張子・パス・操作種別で通知対象を絞り込み |
| 外部サーバー連携 | Raspberry PiをFPolicyサーバーとして動作させ、軽量な前処理を実行 |

**活用シナリオ**: 検査装置がONTAP NFS共有に画像を保存 → FPolicyがファイル作成を検知 → Lambda をトリガー → Bedrock分析。

> **注意**: FPolicy は対象ファイル操作にレイテンシを追加する（同期モードで数ms〜数十ms）。高頻度書き込み環境では非同期モードの使用、またはフィルタリングによる通知対象の絞り込みが必要。

### 4.4 Multi-Protocol (NFS/SMB/S3)

| 特性 | IoT/エッジ文脈での価値 |
|------|----------------------|
| NFS + S3 同時アクセス | エッジデバイスはNFSで書き込み、AWSサービスはS3 APで読み取り |
| SMB + NFS | Windows検査装置(SMB)とLinuxエッジデバイス(NFS)が同一データにアクセス |
| プロトコル変換不要 | データコピーなしで異なるワークロードが同一データを利用 |

**活用シナリオ**: 3Dプリンターの制御PC(Windows/SMB)が保存したGコードを、Raspberry Pi(NFS)が読み取って印刷状態を監視。同じボリュームのS3 APからAthenaで印刷履歴を分析。

### 4.5 ARP/AI (Autonomous Ransomware Protection)

| 特性 | IoT/エッジ文脈での価値 |
|------|----------------------|
| AI異常検知 | IoTデバイスが侵害された場合のランサムウェア拡散を即座に検知 |
| 自動Snapshot | 攻撃検知時に自動でSnapshotを取得しデータを保護 |
| FSx for ONTAP対応 | クラウド側のFSx for ONTAPでも同等の保護を提供 |

**活用シナリオ**: IoTデバイスが侵害されONTAP上のデータを暗号化しようとした場合、ARP/AIが異常な書き込みパターンを検知し、自動的にSnapshotを作成してデータを保護。

---

## 5. 技術的制約と考慮事項

### 5.1 FSx for ONTAP S3 Access Points の制約

親プロジェクト（fsxn-lakehouse-integrations）で検証済みの制約:

📋 **[FSx for ONTAP S3 AP 互換性マトリクス（完全版）](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/blob/main/docs/en/compatibility-matrix.md)** — AWS サポート確認済み (2026年5月)

| 制約 | 影響 | 回避策 |
|------|------|--------|
| 条件付き書き込み非対応 (If-None-Match) | Delta Lake/Iceberg/Hudi のトランザクション書き込み不可 | 読み取り専用分析、または DataSync → S3 で書き込みワークロード対応 |
| S3 イベント通知非対応 | Snowpipe 自動取り込み、Auto Loader ファイル通知モード不可 | FPolicy → Lambda、スケジュールポーリング、または REST API |
| SnapMirror S3 非対応 | ONTAP S3 バケットから AWS S3 へのレプリケーション不可 | DataSync (NFS → S3) を検証済み同期手段として使用 |
| ListObjectsV2 高レイテンシ | 小ディレクトリでネイティブ S3 比 30-80倍遅い | ファイルリスト事前生成、大きいファイルサイズ使用、結果キャッシュ |
| SSE-FSX 暗号化のみ | SSE-S3, SSE-KMS, SSE-C 非対応 | デフォルト SSE-FSX を使用（透過的、AWS KMS 管理） |
| オブジェクトバージョニング非対応 | S3 バージョニング利用不可 | ONTAP Snapshot でポイントインタイムリカバリ |
| Presigned URL: 公式未サポート | 実際には動作するが保証なし | 非クリティカルパスのみ使用、IAM ベースアクセスを推奨 |
| **ONTAP 9.17.1+ 必須** | S3 Access Points の最小バージョン | デプロイ前に FSx ファイルシステムの ONTAP バージョンを確認 |

プラットフォーム別互換性（Athena, Glue, EMR, Databricks, Snowflake, Bedrock）の詳細は[完全版ドキュメント](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/blob/main/docs/en/compatibility-matrix.md)を参照。

### 5.2 SORACOM セルラー通信の制約

| 制約 | 影響 | 対策 |
|------|------|------|
| 帯域制限 (LTE: 数Mbps〜数十Mbps) | 高解像度画像のリアルタイム転送に制約 | エッジでリサイズ・圧縮、差分転送 |
| データ量課金 | 大量データ転送はコスト増 | エッジ前処理で転送量削減、夜間バッチ |
| レイテンシ (数十ms〜数百ms) | リアルタイム制御には不向き | エッジ推論 + クラウドは非同期 |
| 接続安定性 | 電波状況による切断 | ローカルバッファリング + 再送制御 |

### 5.3 Raspberry Pi 5 の制約

| 制約 | 影響 | 対策 |
|------|------|------|
| 計算能力 (ARM Cortex-A76) | 大規模AIモデルのエッジ推論は困難 | TensorFlow Lite / ONNX Runtime で軽量モデル |
| メモリ (16GB) | 大きな画像バッチ処理に制限 | ストリーミング処理、1枚ずつ処理 |
| ストレージ (NVMe SSD 128-256GB) | 長期データ保存には不十分 | ONTAPへの定期転送、ローカルは一時バッファ |
| 電源 (27W) | UPS不要だが停電時のデータ保護必要 | ジャーナリングFS + 定期同期 |

### 5.4 エッジ接続オプション（有線LANがない場合）

> **注意**: 本アーキテクチャの主経路は Pi → NFS/SMB → ONTAP（有線LAN）です。以下の SORACOM サービスは、有線LANが利用できない現場でのフォールバック接続オプションとして位置づけます。

| サービス | 用途 | プロトコル | 特徴 |
|----------|------|-----------|------|
| **Beam** | 汎用プロトコル変換 | MQTT→MQTTS, HTTP→HTTPS | デバイス側の暗号化処理をオフロード、任意のエンドポイントに転送可能 |
| **Funnel** | クラウドサービス直接連携 | UDP/TCP → AWS Kinesis, S3等 | 設定のみでAWSサービスに直接送信、デバイス側コード最小化 |
| **Harvest** | データ蓄積・可視化 | HTTP/UDP | SORACOM上でデータ保存・グラフ表示、プロトタイプに最適 |
| **Flux** | AI統合ワークフロー | カメラ画像 + GenAI | 低コードでカメラ→AI分析→通知のパイプライン構築 |

**選択指針（有線LANがない場合のみ）**:
- プロトタイプ/検証: **Harvest** (即座に可視化)
- センサーデータ→AWS: **Funnel** (設定のみ、コード不要)
- カメラ画像→AI: **Flux** (低コード、GenAI統合)
- カスタム連携: **Beam** (柔軟なプロトコル変換)

**有線LANがある場合の推奨経路**:
- 画像データ: Pi → NFS → ONTAP → FPolicy → Lambda → Bedrock
- センサーデータ: Pi → NFS → ONTAP → SnapMirror → FSx for ONTAP → S3 AP → Athena/SageMaker
- 遠隔管理: SORACOM Napter（SSH アクセス用、データ転送には使用しない）

### 5.5 セキュリティアーキテクチャ考慮事項

| 懸念事項 | リスク | 対策 |
|----------|--------|------|
| FPolicy サーバー (Pi) の侵害 | ONTAP管理プレーンへのアクセス経路となる | ネットワークセグメンテーション: FPolicy通信用VLANを分離、Pi→ONTAPはFPolicy用ポートのみ許可 |
| Pi → ONTAP 間の通信 (NFS) | NFS v3 は暗号化なし | NFS v4.1 + Kerberos、または専用ネットワークセグメントで物理的に分離 |
| SORACOM 認証 | SIM ベース認証のみでは不十分な場合 | SORACOM Endorse (デバイス証明書) + VPG (閉域網) の併用 |
| 画像データの機密性 | 製品設計情報を含む可能性 | S3 暗号化 (SSE-KMS)、ONTAP Volume Encryption (NVE)、転送時 TLS |
| IoT デバイスのハードニング | デフォルト設定のPiは攻撃対象 | 不要サービス無効化、ファイアウォール (ufw)、SSH鍵認証のみ、自動セキュリティアップデート |

### 5.6 概算コスト見積（PoC #1: 3Dプリント品質監視、月額）

| 項目 | 概算コスト | 前提条件 |
|------|-----------|----------|
| SORACOM Air (plan-D) | ¥300-500/月 | オプション: 有線LANがない場合のフォールバック |
| S3 ストレージ | $1-3/月 | ~30GB/月 (画像アーカイブ) |
| Bedrock (Claude Vision) | $5-20/月 | ~2,880回/日 × 30日、入力トークン課金 |
| Lambda (FPolicy トリガー) | $0-2/月 | FPolicy イベント処理 |
| Athena | $1-5/月 | 数GB/月のスキャン |
| **合計** | **約 ¥1,500-4,000/月** | PoC規模、1デバイス、有線LAN環境 |

> **注意**: 上記は PoC 規模の概算。有線LAN環境ではセルラー通信費が不要のため、SORACOM 費用は発生しない。本番環境ではデバイス数・撮影頻度・保存期間に応じてスケール。正確な見積もりには AWS Pricing Calculator での試算を推奨。

### 5.7 前提条件（PoC 開始に必要なもの）

| カテゴリ | 必要なもの | 備考 |
|----------|-----------|------|
| **AWS** | AWSアカウント、IAMユーザー/ロール | Bedrock モデルアクセスの有効化が必要 |
| **SORACOM** | SORACOMアカウント、IoT SIM (plan-D) | オプション: 有線LANがない場合のみ |
| **ハードウェア** | Raspberry Pi 5 (16GB)、カメラモジュール、NVMe SSD | microSD でも動作するが SSD 推奨 |
| **ONTAP** | ONTAP 9.13.1+ (FPolicy外部サーバー、REST API)。S3 AP 利用時は **9.17.1+** 必須 | FSx for ONTAP の場合は S3 AP 対応バージョンを確認 |
| **ネットワーク** | Pi ↔ ONTAP 間のLAN接続、Pi のセルラー接続 | 10GbE スイッチ推奨（大容量画像転送時） |
| **開発環境** | Python 3.12、Git、AWS CLI v2 | Pi 上で直接開発 or リモート開発 |

---

## 6. 推奨する最初のPoC候補

### 評価マトリクス

| # | PoC候補 | 実現容易性 | インパクト | 機材入手性 | ONTAP活用度 | 総合スコア |
|---|---------|-----------|-----------|-------------|-------------|-----------|
| 1 | 3Dプリント品質監視 | ★★★★★ | ★★★★ | ★★★★★ | ★★★ | **22/25** |
| 2 | ONTAPテレメトリ収集→予測分析 | ★★★★ | ★★★★ | ★★★★ | ★★★★★ | **21/25** |
| 3 | FPolicy→画像自動分析パイプライン | ★★★ | ★★★★★ | ★★★★ | ★★★★★ | **21/25** |
| 4 | 環境センサー→リアルタイムダッシュボード | ★★★★★ | ★★★ | ★★★ | ★★ | **18/25** |
| 5 | 在庫画像AI棚卸し | ★★★ | ★★★★ | ★★★ | ★★★ | **16/25** |

### PoC #1 推奨: 3Dプリント品質監視（UC-M1）

#### なぜ既存のプリンター内蔵カメラではなく外部監視か？

多くの FDM 3Dプリンターは内蔵カメラとクラウド監視機能を持つ。本 PoC が外部カメラ + 独自パイプラインを構築する理由:

| 観点 | プリンター内蔵機能 | 本アーキテクチャ |
|------|------------------|----------------|
| AI分析 | タイムラプス録画のみ（リアルタイム異常検知なし） | Claude Vision によるリアルタイム欠陥検出 |
| アクション連携 | 通知のみ | 印刷停止API呼び出し、ONTAP連携、業務ワークフロー統合 |
| データ蓄積・分析 | ベンダークラウドに閉じる | 自社S3/ONTAP に蓄積、Athena/SageMaker で横断分析 |
| マルチプリンター | プリンター毎に別管理 | 統一ダッシュボードで複数台を一元監視 |
| カスタマイズ性 | ベンダー仕様に依存 | プロンプト・閾値・通知先を自由に変更可能 |
| 横展開 | 同一ベンダー機のみ | 任意のプリンター・製造設備に適用可能 |

#### 通信経路の設計

```
[ラボ/工場内ネットワーク]                    [クラウド]
Pi ──Ethernet──→ ONTAP (NFS: ローカル保存)
Pi ──Ethernet──→ 10GbE Switch ──→ Internet ──→ AWS (通常時)
Pi ──Cellular──→ SORACOM ──→ AWS (Ethernet障害時のフォールバック)
```

| 経路 | 用途 | 理由 |
|------|------|------|
| Ethernet (有線) | Pi ↔ ONTAP 間のデータ読み書き | 高帯域・低遅延・無課金 |
| Ethernet → Internet | Pi → AWS (S3/Bedrock) への通常アップロード | 帯域制約なし、コスト最小 |
| Cellular (SORACOM) | フォールバック通信 + 遠隔管理 | 有線障害時の冗長性、SORACOM Napter による遠隔SSH |

> **設計判断**: ラボ/工場内に有線ネットワークがある場合、データ転送は有線を優先する。セルラーは「現場にネットワークがない」場合、または「有線障害時のフォールバック」として位置づける。SORACOM の価値はフォールバック通信に加え、Napter（遠隔アクセス）とデバイス管理にある。

#### アラート後のアクションワークフロー

```
[異常検出] → [重要度判定] → [アクション]

severity: low    → ログ記録のみ、次回キャプチャで再確認
severity: medium → Slack/Teams 通知 + オペレーター確認待ち
severity: high   → 通知 + プリンター一時停止API呼び出し（自動）
severity: critical → 即時停止 + 緊急通知（電話/PagerDuty）
```

| アクション | 実装方法 | Phase |
|-----------|---------|-------|
| ログ記録 | S3 + CloudWatch Logs | Phase 1 |
| Slack/Teams 通知 | SNS → Chatbot or Webhook | Phase 1 |
| プリンター一時停止 | プリンターAPI呼び出し (Lambda) | Phase 2 |
| 緊急通知 | PagerDuty / 電話 | Phase 3 (本番) |

#### 成功基準 (Go/No-Go)

| 指標 | Phase 1 目標 | Go/No-Go 基準 |
|------|-------------|---------------|
| 異常検出精度 | ≥80% | 70%未満なら プロンプト改善 or モデル変更 |
| キャプチャ→アラート | ≤60秒 | 120秒超なら アーキテクチャ見直し |
| 誤検知率 | ≤10% | 20%超なら 閾値調整 or 学習データ追加 |
| システム稼働率 | ≥95% | 90%未満なら ハードウェア/ネットワーク見直し |
| 月間運用コスト | ≤¥5,000 | ¥10,000超なら 撮影頻度/解像度の最適化 |

#### 実装ステップ（改訂版）

```
Phase 1 (1週間): 最小構成で動かす ← "小さく作って動かす"
  目標: カメラ→ONTAP保存→AI分析→通知が動くことを確認
  構成: Pi + カメラ + ONTAP NFS + Lambda + Bedrock
  手順:
    1. Pi + USB カメラのセットアップ、有線LAN接続
    2. 定期撮影スクリプト (Python, 60秒間隔)
    3. NFS マウント → ONTAP ボリュームに画像書き込み
    4. FPolicy 設定 → Lambda トリガー → Bedrock 分析 → Slack通知
    5. 1日運転して精度・安定性を確認
  SORACOM: 不要（有線LAN環境）
  Go/No-Go: 精度70%以上 & 安定動作 → Phase 2 へ

Phase 2 (1-2週間): カスタマイズ + 分析精度向上
  目標: 分析精度向上 + アクションワークフロー構築
  構成: Phase 1 + Lambda (カスタム分析) + アクション分岐
  手順:
    1. Lambda 関数最適化（プロンプト改善、severity分岐）
    2. FPolicy フィルタリング最適化（対象拡張子・パス）
    3. アクションワークフロー実装（severity別対応）
    4. 2段階AI分析（Haiku スクリーニング + Sonnet 詳細）
  Go/No-Go: 精度80%以上 & アクション連携動作 → Phase 3 へ

Phase 3 (2週間): 分析基盤 + 本番準備
  目標: データ分析 + 運用体制構築
  構成: Phase 2 + SnapMirror → FSx for ONTAP + Athena + QuickSight
  手順:
    1. SnapMirror: ONTAP → FSx for ONTAP 同期設定
    2. FSx for ONTAP S3 AP → Athena 分析（印刷成功率、失敗パターン）
    3. QuickSight ダッシュボード
    4. 運用手順書作成（デバイス交換、障害対応）
    5. 死活監視設定（Pi heartbeat → CloudWatch）
```

#### PoC → パイロット → 本番 ロードマップ

```
PoC (4週間)          Pilot (4-8週間)         Production
─────────────────→ ─────────────────────→ ──────────────→
1台のプリンター      3-5台に横展開           全プリンター
ラボ環境             実運用環境              24/7運用
手動監視             半自動運用              完全自動化
FPolicy + 手動確認   Lambda + 自動アクション  自動停止 + 復旧
```

### PoC #2 推奨: ONTAPテレメトリ収集→予測分析

**選定理由**:
1. ONTAP REST API は即座に利用可能（追加機材不要）で、ストレージ運用の知見を活かせる
2. 既存 ONTAP 環境で即座に検証可能
3. AIOps/予知保全のトレンドに合致

**実装ステップ**:

```
Phase 1 (1週間): テレメトリ収集
  - ONTAP REST API ポーリングスクリプト (Python)
    - /api/cluster/metrics (IOPS, レイテンシ, スループット)
    - /api/storage/volumes (容量, 使用率)
    - /api/cluster/nodes (CPU, メモリ)
  - Raspberry Pi 5 で定期実行 (1分間隔)
  - NFS 書き込み → ONTAP ボリュームに CSV 蓄積

Phase 2 (1週間): 分析基盤
  - SnapMirror → FSx for ONTAP 同期設定
  - FSx for ONTAP S3 AP → Glue Crawler でデータカタログ作成
  - Athena でアドホック分析
  - CloudWatch ダッシュボード (リアルタイム)

Phase 3 (2週間): AI予測
  - SageMaker: 容量予測モデル (いつ満杯になるか)
  - SageMaker: 異常検知モデル (レイテンシスパイク予測)
  - Bedrock: 自然言語での健全性レポート自動生成
```

---

## 7. 参考リンク・情報源

### AWS 公式

- [FSx for ONTAP S3 Access Points × Athena チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html)
- [FSx for ONTAP S3 Access Points × Glue ETL チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html)
- [FSx for ONTAP × AWS サービス連携](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)
- [AWS IoT Greengrass + Raspberry Pi カメラ推論](https://docs.aws.amazon.com/greengrass/v2/developerguide/ml-tutorial-image-classification-camera.html)
- [AWS IoT Core + Raspberry Pi 接続ガイド](https://docs.aws.amazon.com/iot/latest/developerguide/connecting-to-existing-device.html)
- [Kinesis Video Streams + RTSP カメラ](https://aws.amazon.com/jp/awstv/watch/a3bff86453f/)
- [AWS IoT 予知保全ブログ](https://aws.amazon.com/blogs/iot/using-aws-iot-for-predictive-maintenance/)
- [Bedrock マルチモーダル予知保全](https://aws.amazon.com/blogs/machine-learning/build-a-multimodal-generative-ai-assistant-for-root-cause-diagnosis-in-predictive-maintenance-using-amazon-bedrock/)
- [IoT センサーデータのイベント駆動アーキテクチャ](https://aws.amazon.com/blogs/architecture/building-event-driven-architectures-with-iot-sensor-data/)
- [Guidance for Predictive Maintenance with SAP using AWS IoT](https://aws.amazon.com/solutions/guidance/predictive-maintenance-with-sap-using-aws-iot/)

### NetApp 公式

- [NetApp and AWS: Industry 4.0](https://www.netapp.com/blog/netapp-aws-meet-challenges-of-industry-4-0/)
- [Synchronize Manufacturing Operational Data – AWS Cloud](https://netapp.com/blog/synchronize-manufacturing-operational-data-aws-cloud/)
- [Bridging the OT-IT Divide in Manufacturing](https://netapp.com/blog/bridging-the-ot-it-divide-in-manufacturing)
- [ONTAP REST API パフォーマンスメトリクス](https://docs.netapp.com/us-en/ontap-automation/rest/performance_metrics.html)
- [FPolicy ドキュメント](https://docs.netapp.com/us-en/ontap-restapi-991/ontap/post-protocols-fpolicy.html)
- [FlexCache 概要](https://www.netapp.com/data-storage/what-is-flex-cache/)
- [SnapMirror データレプリケーション × AWS](https://www.netapp.com/blog/snapmirror-data-replication-aws/)
- [ARP/AI for FSx for ONTAP](https://www.netapp.com/blog/fsx-ontap-autonomous-ransomware-protection)
- [FSx for ONTAP S3 AP × Athena 直接分析 (Tech ONTAP Blog)](https://community.netapp.com/t5/Tech-ONTAP-Blogs/Run-advanced-analytics-with-Amazon-Athena-directly-on-data-in-Amazon-FSx-for/m-p/466956)
- [NetApp on AWS Outposts](https://community.netapp.com/t5/Tech-ONTAP-Blogs/NetApp-on-premises-enterprise-storage-arrays-for-AWS-Outposts/ba-p/456976)

### SORACOM 公式（オプション: セルラー接続時）

- [SORACOM × AWS IoT 統合](https://soracom.io/aws/)
- [SORACOM Flux 概要](https://developers.soracom.io/en/docs/flux/)
- [Flux AI画像分析 Getting Started](https://developers.soracom.io/en/docs/flux/getting-started/ai-image-analysis/)
- [AI-Powered Inventory Monitoring with Raspberry Pi and Soracom Flux](https://soracom.io/blog/ai-powered-inventory-monitoring-with-raspberry-pi-and-soracom-flux/)
- [Beam → AWS IoT Core 接続](https://developers.soracom.io/en/start/aws/beam-iotcore)
- [Funnel → Kinesis → S3](https://developers.soracom.io/en/start/aws/funnel-kinesis-s3)
- [Beam → SageMaker AI予測](https://developers.soracom.io/en/start/aws/beam-sagemaker)
- [Beam → Lambda 連携](https://developers.soracom.io/en/start/aws/beam-lambda)
- [Flux → AWS IoT Webhook](https://developers.soracom.io/en/start/aws/soracom-flux-webhook-aws-iot)
- [Beam/Funnel/Funk 選択ガイド](https://www.soracom.io/blog/solving-iot-issues-how-to-choose-between-soracom-beam-funnel-and-funk/)
- [SORACOM AWS ケーススタディ](https://aws.amazon.com/solutions/case-studies/soracom/)

### コミュニティ・事例

- [River Monitoring with IoT Flow Meter (Hackster.io)](https://hackster.io/rhammell/river-monitoring-with-an-iot-flow-meter-9af852)
- [Raspberry Pi + AWS Rekognition 画像認識](https://github.com/MatthiasGemelli/IntelliCam)
- [Kinesis Video Streams + Rekognition 火災検知](https://community.aws/content/2hTnRBhcqWU1nO7pHUw8fVKqQlN/how-to-detect-forest-fires-using-kinesis-video-streams-and-amazon-rekognition)
- [Smart 3D Printing Surveillance (SCALE 21x)](https://www.socallinuxexpo.org/scale/21x/presentations/smart-3d-printing-surveillance-detecting-failures-computer-vision-and)
- [Industrial Monitoring with Raspberry Pi (Industrial Shields)](https://www.industrialshields.com/blog/raspberry-pi-for-industry-26/industrial-monitoring-and-data-extraction-with-raspberry-pi-how-gateberry-raspberry-plc-and-touchberry-are-redefining-the-edge-675)

---

## 付録: リファレンス構成（最小ハードウェア）

| 機材 | PoC での役割 | 対応ユースケース |
|------|-------------|-----------------|
| ONTAP ストレージ (エントリー機) | エッジONTAP: データ蓄積、FPolicy、REST API テレメトリ | UC-M1, M2, M3, L2 |
| Raspberry Pi 5 (16GB) ×2 | エッジコンピュート: センサー収集、カメラ撮影、前処理 | 全UC |
| NVMe SSD (M.2 2280, 128-256GB) | Pi ローカルバッファ: 一時データ保存、エッジ推論モデル格納 | 全UC |
| カメラモジュール (近赤外線対応) | 暗所撮影、植生指数計測 | UC-A2 |
| USB カメラ (4K対応) | 高解像度撮影: 外観検査、在庫画像、3Dプリント監視 | UC-M1, M3, L1 |
| FDM 3Dプリンター | 監視対象: 印刷品質監視のデモ対象 | UC-M1 |
| 10GbE L3 スイッチ | ネットワーク: ONTAP ↔ Pi 間の高速通信 | 全UC |
| ONTAP Mid-Range (将来拡張) | 大規模データ蓄積、SnapMirror元 | パターンD |

---

## 付録: アクションリスト（ハードウェア到着前 / 到着後）

### 今すぐできること（ハードウェア不要）

| # | アクション | ステータス | 備考 |
|---|-----------|-----------|------|
| 1 | AWS インフラデプロイ (CloudFormation) | ✅ 完了 | S3, Kinesis, Lambda, IAM, Glue |
| 2 | Bedrock モデルアクセス有効化 | ✅ 完了 | Claude Sonnet 4.5 |
| 3 | SNS アラートメール登録 | ✅ 完了 | 確認メールのクリック待ち |
| 4 | SORACOM Operator ID 取得 → CFn 更新 | 📋 待ち | オプション: セルラー接続時のみ必要 |
| 5 | SORACOM Flux アプリ作成（コンソール） | 📋 待ち | オプション: 有線LANがない場合のみ |
| 6 | カメラマウント設計 → 3Dプリントで自作 | 📋 待ち | プリンター到着後に印刷 |
| 7 | Bedrock プロンプトの事前テスト | 📋 可能 | サンプル3Dプリント画像で精度確認 |

### Pi 到着後にやること

| # | アクション | 所要時間 | 依存 |
|---|-----------|---------|------|
| 1 | OS書き込み + 初回セットアップ | 1時間 | Pi + SSD |
| 2 | カメラ接続 + テスト撮影 | 30分 | Pi + カメラ |
| 3 | SORACOM SIM セットアップ | 30分 | オプション: セルラー接続時のみ |
| 4 | simple_capture.py 動作確認 | 15分 | Step 1-2 完了 |
| 5 | NFS マウント + ONTAP 書き込みテスト | 30分 | Step 4 + ONTAP NFS設定済み |
| 6 | カメラ設置 + 画角調整 | 1時間 | Pi + カメラ + プリンター |
| 7 | 24時間連続運転テスト | 24時間 | Step 6 完了 |
| 8 | Go/No-Go 判定 → Phase 2 移行 | — | Step 7 の結果次第 |
