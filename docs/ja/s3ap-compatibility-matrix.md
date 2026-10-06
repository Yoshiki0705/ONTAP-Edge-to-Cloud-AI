> 🌐 Language: **日本語** | [English](../en/s3ap-compatibility-matrix.md)

# FSx for ONTAP S3 Access Points の互換性と制約

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

**この表は閉じた一覧として読んでください。** ここに無いサービスは「使えない」ではなく
「AWS が S3 AP 経由の手順を公開していない」状態です。S3 に対応していることは、access point の
ARN または alias を扱えることを意味しません。全体アーキテクチャ図が Amazon SageMaker AI に
※6 を付けているのはこの理由で、S3 AP から実線で結んだ他のサービスとは根拠の強さが違います。

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

### 認可の 2 層評価

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
| S3 イベント通知非対応 | オブジェクト作成イベントを起点にした自動取り込みができない | NFS / SMB で書く経路では FPolicy → Lambda。S3 Access Points 経由の書き込みでは FPolicy の通知が出ない（[実測](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns/blob/main/docs/errata-fpolicy-s3ap-coverage.md)、2026-08-26、ap-northeast-1、ONTAP 9.18.1P3D1）ため、§5 の S3 API で書く経路ではスケジュールポーリングか ONTAP REST API | プロジェクト検証 |
| SnapMirror S3 非対応 | ONTAP S3 バケットから S3 へのレプリケーションができない | AWS DataSync (NFS → S3) | プロジェクト検証 |
| ListObjectsV2 のレイテンシ | 10〜1,000 オブジェクトでネイティブ S3 の 1.3〜1.4 倍（中央値の比）。5,000 オブジェクトのフラット配置では 0.9 倍（[測定記録](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/blob/main/verification-pack/s3ap-list-latency/evidence/2026-08-05/benchmark-result.yaml)、2026-08-05） | ファイルリストの事前生成、ファイルサイズを大きくする、結果のキャッシュ | プロジェクト検証 |
| SSE-FSX のみ | SSE-S3 / SSE-KMS / SSE-C は使えない | 既定の SSE-FSX を使う | プロジェクト検証 |
| オブジェクトバージョニング非対応 | S3 バージョニングが使えない | ONTAP Snapshot | プロジェクト検証 |
| Presigned URL | 公式の[対応表](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-object-api-support.html)は 2026-10-06 の確認時点で `Presign` を Supported と記載。別プロジェクトの 2026-08-19 の記録は、当時の同表が Not supported と記載していたとしたうえで、presigned URL の `PutObject` / `HeadObject` / `GetObject` が成功したと記録している（[測定記録](https://github.com/Yoshiki0705/S3-Burst-on-ONTAP-Files/blob/main/docs/ja/verification/s3ap-operations.md)、ap-northeast-1、AWS 外のクライアント） | 表の記載が変わっているため、重要な経路では IAM ベースのアクセスを使うか、自環境で確認してから依存する | 公式 |

対応 S3 API の網羅的な一覧は公式の
[Access point compatibility](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-points-service-api-support.html) を参照。
S3 AP 経由のファイルは `StorageClass` が `FSX_ONTAP` として返る
（[出典](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-points-for-fsxn-usage-examples.html)）。

> **数値について**: 別プロジェクトに以前記録されていた倍率は、同プロジェクトが 2026-08-05 の
> 再測定で再現できず、撤回している。上の 1.3〜1.4 倍はその再測定の値で、条件は
> ap-northeast-1、SINGLE_AZ_1 / 128 MBps、VPC 外の端末からインターネット経由、
> 1 ファイルシステム・1 日・最大 5,000 オブジェクト。絶対値にはインターネットの往復が含まれる。
> このプロジェクトの構成では測っていないので、自分の構成で測ること（§7 の 4）。

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

## 5. このリポジトリで該当する経路

書き込みの向きが 2 つあり、S3 AP の位置づけが逆になります。

| 経路 | 向き | S3 AP の役割 | 標準バケット |
|------|------|-------------|-------------|
| エッジ → NFS → ONTAP → 分析 | ファイルプロトコルで書く | 読み取り側の入口 | 使わない |
| AWS IoT Core → Lambda → ONTAP（[`cloud/iot_ingestion/`](../../cloud/iot_ingestion/)） | S3 API で書く | 書き込み側の入口 | 使わない |
| SORACOM → Kinesis → Firehose → Glue（[`cloud/ingestion/`](../../cloud/ingestion/)） | S3 API で書く | 使わない | **使う**（§4 の Firehose） |
| 判定結果の保存（3 つの usecase スタック） | S3 API で書く | 未配線 | **使う**（`RESULT_BUCKET`） |

2 行目の形は
[S3 Burst on ONTAP Files](https://github.com/Yoshiki0705/s3-burst-on-ontap-files)
と同じで、S3 API で収集して ONTAP を正本データとし、ファンアウト先の利用拠点へ NFS / SMB で
配る構成です。クラウド API から始まるパイプライン、つまり本リポジトリのセルラー経路や
MQTT 経路のような入口には、この向きが素直に当てはまります。

4 行目は現時点でテンプレートが標準バケットを渡しています。`boto3` の `Bucket` は access point
ARN をそのまま受けるのでハンドラ側の変更は不要と見込んでいますが、実機では確認していません
（[検証状態](verification-status.md)）。

## 6. 影響を受ける構成と代替経路

| 構成 | 代替経路 | 代替の制約 |
|------|---------|-----------|
| Greengrass から S3 AP へ直接送る | カスタムコンポーネントで boto3 PutObject | Stream Manager のオフラインバッファ、リトライ、帯域制御、マルチパート管理を自前で実装する |
| IoT Core テレメトリを S3 AP に直接保存 | Lambda ルールアクション経由 | Lambda の呼び出しコストとレイテンシが加わる |
| Firehose の Parquet 変換を S3 AP に配信 | Lambda で集約して PutObject、または MSK Express brokers の streaming tables で Iceberg テーブルに materialize | Firehose のマネージド変換とバッファリングは使えない |
| SiteWise の時系列データを S3 AP に保存 | S3 バケット経由 + DataSync | ストレージの二重持ちと遅延 |
| 外部パートナーへのファイル受け渡し | AWS Transfer Family（S3 AP 経由、**公式**） | 該当なし |

---

## 7. 未確認の項目

このプロジェクトで確認できていない項目。埋まったらこの表から消す。

| # | 項目 | 確認方法 |
|---|------|---------|
| 1 | §4 の 6 サービスで access point ARN / alias が通るか | 各サービスの設定に指定して結果を記録する |
| 2 | Presigned URL がこのリポジトリの経路で動くか | 自環境で実測する（公式表の記載と別プロジェクトの実測は §3） |
| 3 | Unity Catalog の External Location に S3 AP を登録できるか | 登録を試す（[Databricks 連携](./databricks-integration.md) 参照） |
| 4 | ListObjectsV2 のレイテンシがこの構成でどの程度か | 自環境で測定し、測定条件とともに記録する |

---

## 関連ドキュメント

- [IoT Greengrass + FlexCache 連携シナリオ](./iot-greengrass-flexcache-integration.md)：書き込み経路と FlexCache
- [Databricks 連携設計](./databricks-integration.md)：Unity Catalog との接続パス
- [デプロイガイド](./deployment-guide.md)：実際の構築手順
- [AWS パターンカタログ](./aws-patterns/README.md)：この制約が各構成にどう効くか
- [FAQ](./faq.md)
