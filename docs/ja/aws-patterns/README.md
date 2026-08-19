> 🌐 Language: **日本語** | [English](../../en/aws-patterns/README.md)

# AWS パターンカタログ

> 最終確認: 2026-08-19

エッジで生まれたデータを AWS の分析・AI サービスにつなぐ構成を、同じ型式で 9 本並べています。
自分の要件に近いものを選び、前提と制約を読んでから採用してください。

## 読み方

各パターンの冒頭に**成熟度**があります。3 値です。

| ラベル | 意味 |
|--------|------|
| **実装あり** | このリポジトリにデプロイできるコードがある。経路の段ごとの有無は各 doc の実装状況表に書いてある |
| **設計のみ** | 設計は書いたが、このリポジトリにコードはない。AWS 公式の手順がある場合はそう明記している |
| **概念** | 構成案のみ。公式の裏付けがない部分を含む |

**このカタログに金額は書きません。** 費用を駆動する要素だけを挙げ、金額の見積りは
[デプロイガイド](../deployment-guide.md) に集約しています。測定していない性能値も書きません。

## パターン一覧

| # | パターン | 経路 | 成熟度 |
|---|---------|------|--------|
| [01](01-edge-ai-bedrock.md) | エッジ AI + Amazon Bedrock | エッジ → ローカルストレージ → FSx for ONTAP → Bedrock → エージェント処理 | 実装あり（一部） |
| [02](02-edge-ai-sagemaker.md) | エッジ AI + SageMaker | エッジカメラ → ONTAP → FSx for ONTAP → SageMaker 学習 → 推論 | 設計のみ |
| [03](03-industrial-iot-analytics.md) | 産業 IoT 分析 | センサー → Kafka → MSK → データレイク → Glue → Athena | 実装あり（一部） |
| [04](04-near-realtime-manufacturing.md) | 準リアルタイム製造分析 | Kafka → ClickHouse → オブジェクトストレージ → Databricks | 実装あり（一部） |
| [05](05-agentic-rag.md) | エージェント型 RAG | 文書 → ONTAP → FSx for ONTAP → Bedrock Knowledge Bases → 検索 | 設計のみ（公式手順あり） |
| [06](06-video-analytics.md) | 映像分析 | エッジカメラ → ONTAP → FSx for ONTAP → Rekognition → OpenSearch | 設計のみ |
| [07](07-digital-twin.md) | デジタルツイン | IoT デバイス → IoT Core → 時系列 DB → Bedrock → 可視化 | 実装あり（一部） |
| [08](08-unified-namespace.md) | 統合名前空間 / 産業データファブリック | OT 機器 → 単一メッセージバス → クラウド | 設計のみ |
| [09](09-edge-agentic-ai.md) | エッジ側エージェント AI | デバイス群 → ローカル SLM → クラウド LLM への委譲 | 設計のみ（公式 Guidance あり） |

## 選び方

判断は「何を最初に解きたいか」で分かれます。

| 最初に解きたいこと | 見るパターン |
|---|---|
| 画像から品質判定を出したい | [01](01-edge-ai-bedrock.md)（生成 AI で判定）/ [02](02-edge-ai-sagemaker.md)（自前モデルを学習）/ [06](06-video-analytics.md)（映像と検索） |
| センサーデータを溜めて SQL で分析したい | [03](03-industrial-iot-analytics.md) |
| ダッシュボードの遅延を秒単位にしたい | [04](04-near-realtime-manufacturing.md) |
| 既存の文書資産を AI に参照させたい | [05](05-agentic-rag.md) |
| 設備の状態を時系列で持ち、説明を生成したい | [07](07-digital-twin.md) |
| OT 側のデータが機器ごとにバラバラで、名前空間から整えたい | [08](08-unified-namespace.md) |
| ネットワークが不安定で、判断をエッジで完結させたい | [09](09-edge-agentic-ai.md) |

**判断の順序**: 先に [08](08-unified-namespace.md) を読む価値があるのは、収集そのものが
未整備な場合です。すでにデータが集まっているなら 01 / 03 から入るほうが早く動きます。

## 横断する前提

すべてのパターンに共通する制約です。各 doc で再掲しません。

- **S3 Access Point の制約**: 条件付き書き込み・イベント通知・オブジェクトバージョニングが
  使えず、ONTAP 9.17.1 以降が必要。同一リージョン・同一アカウント・junction path 必須。
  一覧と根拠は [S3 AP 互換性と制約](../s3ap-compatibility-matrix.md)
- **セキュリティ統制**: IAM、ネットワーク分離、暗号化、監査は
  [セキュリティ設計](../security-design.md) に集約
- **イベントスキーマ**: [データスキーマ設計](../data-schema-design.md)
- **エージェント処理の設計論点**: [Agentic AI on AWS](../agentic-ai-on-aws.md)
- **将来の構成候補**: [Flexible AI Data Layer](../flexible-ai-data-layer.md)

## リポジトリ構造との対応

このカタログは設計を扱います。動くものの所在は次のとおりです。

| 探しているもの | 場所 |
|---|---|
| CloudFormation / SAM テンプレート | [`cloud/`](../../../cloud/) — 共有基盤、FSx for ONTAP、IoT 取り込み、AI |
| デプロイできるユースケース一式 | [`usecases/`](../../../usecases/) |
| エッジ側のコード | [`edge/`](../../../edge/) |
| ClickHouse のスキーマ | [`cloud/clickhouse/ddl/`](../../../cloud/clickhouse/ddl/) |
| 物理機材なしで動かすデモ | [`local-demo/`](../../../local-demo/) |
| Terraform | 未実装。ロードマップ項目 |

## 未確認の項目

各パターンの「前提と制約」にも書いていますが、横断して残っているものを挙げます。

| 項目 | 影響するパターン |
|---|---|
| S3 AP に対する Greengrass Stream Manager / Data Firehose / IoT Core S3 アクション / SiteWise の対応 | 01, 03, 07, 08 |
| Unity Catalog の External Location に S3 AP を登録できるか | 04 |
| FlexCache のブロック単位キャッシュがモデル配信でどう効くか | 02, 09 |
| ListObjectsV2 のレイテンシがこの構成でどの程度か | 03, 05, 06 |
