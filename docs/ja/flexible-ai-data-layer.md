> 🌐 Language: **日本語** | [English](../en/flexible-ai-data-layer.md)

# Flexible AI Data Layer Patterns

> 最終確認: 2026-08-19

AI が読むデータ層を、どのエンジンからも同じデータを読める形に保つための構成を扱います。
**今使えるもの、preview のもの、構想に留まるものを混ぜません。**

## 可用性ラベル

すべての項目にラベルを付けます。ラベルのない記述はこの doc に置きません。

| ラベル | 意味 | 書き方の義務 |
|--------|------|------------|
| **Supported today** | 公式ドキュメントに一般提供として記載 | URL を併記する |
| **Public preview** | 公式に preview と明示されている | URL + preview である旨を書く |
| **Conceptual** | 公式の裏付けがない構成案 | 「構成案」と明記し、実現手段を断定しない |

**この doc に性能値・コスト削減率を書きません。** 測定していないため、書けば読者を誤らせます。

## 1. ファイルストレージを AI のデータ層にする

**Supported today.** ファイル共有上のデータに、コピーを作らずに S3 API でアクセスできます。
利用できる AWS サービスは公式に一覧化されています
（[出典](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)）。

| できること | 可用性 | 出典 |
|---|---|---|
| SQL クエリ（Glue Data Catalog 経由） | Supported today | [Athena チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html) |
| ETL（読み・変換・同じボリュームへの書き戻し） | Supported today | [Glue チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html) |
| RAG のデータソース | Supported today | [Knowledge Bases チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html) |
| Spark ワークロード | Supported today | 上記一覧 |
| SFTP / FTPS でのファイル受け渡し | Supported today | [Transfer Family](https://docs.aws.amazon.com/en_us/transfer/latest/userguide/fsx-s3-access-points.html) |
| 映像配信 | Supported today | 上記一覧 |

**制約も Supported today の事実です。** 条件付き書き込み非対応のため、この層に
Iceberg / Delta のテーブルを直接置いて更新することはできません
（[制約一覧](s3ap-compatibility-matrix.md)）。**この 1 点が、以下の節の構成を分けます。**

## 2. オープンテーブルフォーマット

「Iceberg」を一括で語らないでください。仕様バージョンと、マネージド提供の有無で
できることが変わります。

| 項目 | 可用性 | 出典 |
|---|---|---|
| Iceberg テーブルをオブジェクトストレージに置き、複数エンジンから読む | Supported today | — |
| S3 Tables（Iceberg 対応を内蔵したテーブル用バケット） | Supported today | [出典](https://docs.aws.amazon.com/sagemaker-lakehouse-architecture/latest/userguide/lakehouse-s3-tables-integration.html) |
| Iceberg V3 の deletion vectors / row lineage（Glue Data Catalog 側） | Supported today | [出典](https://aws.amazon.com/sagemaker/lakehouse/features/) |
| Iceberg V3 の Variant 型（S3 Tables） | Supported today | [出典](https://aws.amazon.com/about-aws/whats-new/2026/07/amazon-s3-tables-variant-iceberg-v3/) |
| Kafka トピックを Iceberg テーブルとして継続的に materialize | Supported today | [MSK Express brokers](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables-streaming-msk.html) |
| ファイルストレージ上に Iceberg テーブルを直接置いて更新 | **できない**（条件付き書き込み非対応） | [制約一覧](s3ap-compatibility-matrix.md) |

**このアーキテクチャでの帰結**: テーブル形式のデータはオブジェクトストレージ側に置き、
ファイルストレージ側は原本（画像、文書、波形）の置き場にする。両者を S3 API で
同じように読む、という分担になります。

## 3. カタログの相互運用

**単一プラットフォームの優劣ではなく、エンジン選択の自由度の話です。**

Iceberg REST カタログの仕様を実装したカタログ同士では、一方が管理するテーブルを
他方から読み書きする federation が成立しつつあります。

| 項目 | 可用性 | 出典 |
|---|---|---|
| Iceberg REST 仕様に沿った外部エンジンからの読み取り | Supported today（各カタログの実装に依存） | [Snowflake 側の解説](https://www.snowflake.com/en/blog/engineering/snowflake-horizon-vs-databricks-unity-catalog-comparison/) |
| 外部カタログが管理する Iceberg テーブルへの書き込み | Supported today（提供元の記載による） | [外部管理テーブルへの書き込み](https://docs.snowflake.com/user-guide/tables-iceberg-externally-managed-writes) |
| カタログ間の双方向 federation | Supported today（構成手順が公開されている） | [双方向アクセスの手順](https://docs.snowflake.com/en/user-guide/tutorials/tables-iceberg-set-up-bidirectional-access-to-unity-catalog) |

**選び方**は「どのエンジンで何をするか」で決まります。対称に書きます。

| 条件 | 向く形 | trade-off |
|---|---|---|
| 単一のエンジンで完結する | カタログを 1 つに寄せる | 後からエンジンを増やすと移行が必要 |
| 複数のエンジンで同じデータを読む | Iceberg REST での federation | カタログ間の権限モデルの差を運用で埋める |
| エンジンを将来変える可能性がある | オープンな形式 + 外部カタログ | 各カタログの機能差を前提にできない |

**このリポジトリでの状態**: Unity Catalog の External Location に S3 Access Point を
登録できるかは**未検証**です（[databricks-integration](databricks-integration.md)）。
この判定次第で、ファイルストレージから直接読むか、エクスポートを経由するかが変わります。

## 4. ハイブリッド推論

推論をエッジとクラウドに振り分ける構成です。

| 項目 | 可用性 | 出典 |
|---|---|---|
| エッジでの ML 推論（デバイス上での実行） | Supported today | [Greengrass ML inference](https://docs.aws.amazon.com/greengrass/v2/developerguide/perform-machine-learning-inference.html) |
| デバイス群へのエージェント配布（ローカル小型モデル利用） | Supported today（Guidance が公開されている） | [出典](https://docs.aws.amazon.com/solutions/deploying-ai-agents-to-device-fleets-using-aws-iot-greengrass/) |
| ストレージをまたぐハイブリッド推論の構成 | Supported today（構成例が公開されている） | [出典](https://aws.amazon.com/blogs/storage/hybrid-ml-inferencing-on-amazon-eks-with-amazon-fsx-for-netapp-ontap-and-on-premises-netapp/) |
| データ所在要件下での RAG | Supported today（構成例が公開されている） | [出典](https://aws.amazon.com/blogs/machine-learning/implement-rag-while-meeting-data-residency-requirements-using-aws-hybrid-and-edge-services/) |
| 入力の難易度を推定して自動でモデルを振り分ける | **Conceptual** | 学術的な検討はある（[survey](https://arxiv.org/html/2507.16731v1)）が、このアーキテクチャでの実装・検証はない |

**判断軸**は 4 つです。詳細は [Pattern 09](aws-patterns/09-edge-agentic-ai.md) にあります。
レイテンシ、データの機密性、モデルの能力、コスト。**機密性で先に切ります。**
他の 3 つは調整で埋められますが、機密性は埋められません。

## 5. エッジ-クラウド同期

**同期には 2 つの軸があります。** 混ぜると設計が破綻します。

| 軸 | 何を運ぶか | 手段の例 | 可用性 |
|---|---|---|---|
| ファイル / ブロックの同期 | 画像、文書、波形の実体 | FlexCache、SnapMirror、DataSync | Supported today |
| イベントストリームの同期 | 「いつ何が起きたか」のメタデータ | MQTT、Kafka | Supported today |

この 2 つは独立に設計できます。ペイロードはファイル同期で運び、イベントはストリームで
運ぶ、という分担がこのリポジトリの構成です（[README](../../README.md)）。

**片方だけでは足りません。** ファイル同期だけだと「何が届いたか」を知る手段がなく、
イベントだけだと実体が届きません。

エッジ側の書き込みをローカルで確定させる構成には、バージョン要件と本番向けの注意があります
（[FlexCache write-back](iot-greengrass-flexcache-integration.md)）。

## 6. 構想に留まる構成

**以下は Conceptual です。一般提供されている機能として書きません。**

| 構成案 | なぜ Conceptual か |
|---|---|
| ファイルストレージ上のデータを、コピーせずに複数のカタログから同時に管理する | 条件付き書き込みができないため、テーブル形式の管理をこの層に置けない（§1） |
| 推論要求を自動でエッジ / クラウドに振り分ける | 判断軸は整理できるが、このアーキテクチャでの実装がない（§4） |
| エージェントの記憶と真実の源を自動で整合させる | 設計していない（[Agentic AI on AWS](agentic-ai-on-aws.md) §7） |
| OT 側の名前空間からカタログのスキーマを自動生成する | 名前空間設計そのものが未実装（[Pattern 08](aws-patterns/08-unified-namespace.md)） |

## 7. 未確認の項目

| 項目 | 影響 |
|---|---|
| Unity Catalog の External Location に S3 AP を登録できるか | §3 の構成が変わる |
| ListObjectsV2 のレイテンシがこの構成でどの程度か | §1 のクロール性能 |
| FlexCache のブロック単位キャッシュがモデル配信でどう効くか | §4 のモデル配信方式 |
| カタログ間 federation の権限モデルの差 | §3 の運用負荷 |

## 参考

- [Using access points with AWS services](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)
- [S3 Tables in the SageMaker lakehouse architecture](https://docs.aws.amazon.com/sagemaker-lakehouse-architecture/latest/userguide/lakehouse-s3-tables-integration.html)
- [Streaming tables with Amazon MSK](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-tables-streaming-msk.html)
- [Hybrid ML inferencing with FSx for ONTAP and on-premises NetApp](https://aws.amazon.com/blogs/storage/hybrid-ml-inferencing-on-amazon-eks-with-amazon-fsx-for-netapp-ontap-and-on-premises-netapp/)
- 関連: [パターンカタログ](aws-patterns/README.md) /
  [Agentic AI on AWS](agentic-ai-on-aws.md) /
  [S3 AP 互換性と制約](s3ap-compatibility-matrix.md)
