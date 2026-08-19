> 🌐 Language: **日本語** | [English](../en/s3ap-compatibility-matrix.md)

# FSx for ONTAP S3 Access Points — 互換性と制約

> 最終確認: 2026-08-19

## この文書の位置づけ

FSx for ONTAP の S3 Access Point (S3 AP) について、**何が使えて何が使えないか**を集約した
文書。他の doc は制約を再掲せず、ここを参照する。

各項目には根拠の区分を付ける。

| 区分 | 意味 |
|------|------|
| **公式** | AWS 公式ドキュメントに記載。URL を併記 |
| **プロジェクト検証** | 別プロジェクトでの検証結果。検証時期を併記 |
| **未検証** | どちらでも確認できていない。読者は自分の環境で確認すること |

---

## 1. S3 AP 経由で使える AWS サービス

AWS が統合手順を公開しているサービス。

| サービス | 用途 | 区分 |
|----------|------|------|
| Amazon Athena | Glue Data Catalog 経由の SQL クエリ | 公式 |
| AWS Lambda | ボリューム上のファイルに対するサーバーレス処理 | 公式 |
| AWS Glue | Spark / Python shell / Ray による ETL。同じボリュームへの書き戻しも可 | 公式 |
| Amazon Bedrock Knowledge Bases | ボリューム上の文書を根拠にした RAG | 公式 |
| Amazon EMR Serverless | PySpark / Spark SQL | 公式 |
| Amazon CloudFront | HLS 動画配信 | 公式 |
| AWS Transfer Family | SFTP / FTPS / FTP エンドポイントとして外部に公開 | 公式 |

出典: [Using access points with AWS services](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html)（各サービスのチュートリアルへのリンクを含む）

Bedrock Knowledge Bases はデータソースとして **access point alias** を指定する。
bucket 名の代わりに alias を受け付ける。
出典: [Build a RAG application using Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-build-rag-with-bedrock.html)

> **補足**: Bedrock 側の S3 データソースのドキュメントには汎用 S3 バケットのみ対応と記載が
> ある一方、FSx for ONTAP ガイド側は alias 経由の手順を示している
> （[Bedrock 側の記述](https://docs.aws.amazon.com/bedrock/latest/userguide/s3-data-source-connector.html)）。
> 構築時は FSx for ONTAP ガイドの手順に従う。

Athena を使う場合、access point の network origin は **internet** である必要があり、
クエリ結果は FSx for ONTAP ボリュームではなく S3 バケットに書かれる。
出典: [Query files with SQL using Amazon Athena](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html)

---

## 2. 前提と構成上の制約

S3 バケットに付ける access point には無い、FSx for ONTAP 固有の制約。

| 制約 | 内容 | 区分 |
|------|------|------|
| ONTAP バージョン | **9.17.1 以降**のファイルシステムにのみ作成・アタッチ可能 | 公式 |
| リージョン | access point はボリュームと同一リージョンに作る | 公式 |
| アカウント | ファイルシステムと access point は同一 AWS アカウントが所有する。他アカウント所有のボリュームにはアタッチできない | 公式 |
| ボリューム | junction path を持つ（マウント済みの）ボリュームにのみアタッチ可能。DP ボリュームも同様 | 公式 |
| 公開アクセス | Block public access が既定で強制され、無効化できない | 公式 |
| 命名 | access point 名は alias 用に予約された `-ext-s3alias` で終われない | 公式 |

出典: [Access points naming rules, restrictions, and limitations](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-point-for-fsxn-restrictions-limitations-naming-rules.html) /
[Creating access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/create-access-points.html) /
[Accessing your data via Amazon S3 access points](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)

### 認可は 2 層で評価される

S3 側と ファイルシステム側の両方を通る必要がある。

1. S3 が呼び出し元の IAM ポリシー、access point のリソースポリシー、VPC エンドポイント
   ポリシー、SCP を評価する
2. 通った要求を、access point に紐づけた UNIX または Windows のファイルシステムユーザー
   の権限でファイルシステムが再評価する

つまり IAM で許可しても、そのユーザーがファイルに対する権限を持たなければ拒否される。
access point 作成時にファイルシステムユーザー ID を指定する。

出典: [Managing access point access](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/s3-ap-manage-access-fsxn.html)

### 作成に必要な権限

`fsx:CreateAndAttachS3AccessPoint` / `s3:CreateAccessPoint` / `s3:GetAccessPoint`。
ポリシーを同時に作る場合は `s3:PutAccessPointPolicy` も必要。
出典: [Creating an access point](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/fsxn-creating-access-points.html)

---

## 3. データ操作面の制約

別プロジェクト（[fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations)）で
検証された制約。検証時期は 2026 年 5 月。

| 制約 | 影響 | 回避策 | 区分 |
|------|------|--------|------|
| 条件付き書き込み非対応 (If-None-Match) | Delta Lake / Iceberg / Hudi のトランザクション書き込みができない | 読み取り専用分析、または書き込みは S3 側で行う | プロジェクト検証 |
| S3 イベント通知非対応 | オブジェクト作成イベントを起点にした自動取り込みができない | FPolicy → Lambda、スケジュールポーリング、ONTAP REST API | プロジェクト検証 |
| SnapMirror S3 非対応 | ONTAP S3 バケットから S3 へのレプリケーションができない | AWS DataSync (NFS → S3) | プロジェクト検証 |
| ListObjectsV2 のレイテンシ | 小さいディレクトリでネイティブ S3 より遅い | ファイルリストの事前生成、ファイルサイズを大きくする、結果のキャッシュ | プロジェクト検証 |
| SSE-FSX のみ | SSE-S3 / SSE-KMS / SSE-C は使えない | 既定の SSE-FSX を使う | プロジェクト検証 |
| オブジェクトバージョニング非対応 | S3 バージョニングが使えない | ONTAP Snapshot | プロジェクト検証 |
| Presigned URL | 公式にサポートが明記されていない | 重要な経路では IAM ベースのアクセスを使う | 未検証 |

対応 S3 API の網羅的な一覧は公式の
[Access point compatibility](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-service-api-support.html) を参照。
S3 AP 経由のファイルは `StorageClass` が `FSX_ONTAP` として返る
（[出典](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-usage-examples.html)）。

> **数値について**: 上の「遅い」は倍率を書いていない。別プロジェクトでは倍率が記録されている
> が、測定環境（ONTAP バージョン、ファイル数、ディレクトリ構成、スループット設定）が
> このプロジェクトと異なるため、そのまま引用しない。自分の構成で測ること。

---

## 4. S3 バケット名を要求するサービス

出力先に S3 バケット名または バケット ARN を要求し、access point ARN を受け付けない
（と観測されている）サービス。**いずれもこのプロジェクトでは未検証**。

| サービス | 要求する形式 | 区分 |
|----------|-------------|------|
| AWS IoT Greengrass Stream Manager | `S3ExportTaskDefinition` の `bucket`（バケット名） | 未検証 |
| Amazon Data Firehose | `ExtendedS3DestinationConfiguration` の `BucketARN` | 未検証 |
| AWS IoT Core ルールエンジン S3 アクション | `bucket`（バケット名） | 未検証 |
| AWS IoT SiteWise Cold Tier Storage | `put-storage-configuration` の `s3ResourceArn` | 未検証 |
| AWS IoT SiteWise Buffered Destination | S3 バケット | 未検証 |
| AWS IoT SiteWise Bulk Export | S3 バケット | 未検証 |

> **未検証をどう読むか**: 「対応していない」と断定していない。各サービスのドキュメントに
> access point ARN を受け付ける記述が見つからず、このプロジェクトで実際に試していない、
> という状態である。設計判断の根拠にする前に自分で確認すること。

### Alias による回避可能性

AWS は 2021 年に S3 バケット名を要求するアプリケーション向けに
[access point alias](https://aws.amazon.com/about-aws/whats-new/2021/07/amazon-s3-access-points-aliases-allow-application-requires-s3-bucket-name-easily-use-access-point/) を導入している。

- Bedrock Knowledge Bases は alias を bucket 名の代わりに受け付ける（**公式**、§1 参照）
- 上表 6 サービスで alias が通るかは**未検証**
- alias は `-ext-s3alias` で終わる形式で、バケット名のバリデーションを通るかは
  サービス実装に依存する

---

## 5. 影響を受ける構成と代替経路

| 構成 | 代替経路 | 代替の制約 |
|------|---------|-----------|
| Greengrass から S3 AP へ直接送る | カスタムコンポーネントで boto3 PutObject | Stream Manager のオフラインバッファ、リトライ、帯域制御、マルチパート管理を自前で実装する |
| IoT Core テレメトリを S3 AP に直接保存 | Lambda ルールアクション経由 | Lambda の呼び出しコストとレイテンシが加わる |
| Firehose の Parquet 変換を S3 AP に配信 | Lambda で集約して PutObject、または MSK Express brokers の streaming tables で Iceberg テーブルに materialize | Firehose のマネージド変換とバッファリングは使えない |
| SiteWise の時系列データを S3 AP に保存 | S3 バケット経由 + DataSync | ストレージの二重持ちと遅延 |
| 外部パートナーへのファイル受け渡し | AWS Transfer Family（S3 AP 経由、**公式**） | — |

---

## 6. 未確認の項目

このプロジェクトで確認できていない項目。埋まったらこの表から消す。

| # | 項目 | 確認方法 |
|---|------|---------|
| 1 | §4 の 6 サービスで access point ARN / alias が通るか | 各サービスの設定に指定して結果を記録する |
| 2 | Presigned URL の扱い | 公式ドキュメントの記載を探す。無ければ実測 |
| 3 | Unity Catalog の External Location に S3 AP を登録できるか | 登録を試す（[Databricks 連携](./databricks-integration.md) 参照） |
| 4 | ListObjectsV2 のレイテンシがこの構成でどの程度か | 自環境で測定し、測定条件とともに記録する |

---

## 関連ドキュメント

- [IoT Greengrass + FlexCache 連携シナリオ](./iot-greengrass-flexcache-integration.md) — 書き込み経路と FlexCache
- [Databricks 連携設計](./databricks-integration.md) — Unity Catalog との接続パス
- [デプロイガイド](./deployment-guide.md) — 実際の構築手順
- [AWS パターンカタログ](./aws-patterns/README.md) — この制約が各構成にどう効くか
- [FAQ](./faq.md)
