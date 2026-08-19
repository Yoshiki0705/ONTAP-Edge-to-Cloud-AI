> 🌐 Language: **日本語** | [English](../en/s3ap-service-gap-analysis-and-feature-request.md)

# S3 Access Points (FSx for ONTAP) — IoT/エッジサービス対応ギャップ分析 & 機能改善要望

> 作成日: 2026-07-27
> プロジェクト: edge-to-cloud-ai
> 目的: S3 標準バケットをサポートしているが S3 Access Points (特に FSx for ONTAP S3 AP) を未サポートの AWS IoT/エッジサービスを特定し、AWS サポートに機能改善要望を提出する

---

## 1. ギャップ分析結果

### 1.1 対象サービス一覧

以下の IoT / エッジ / データストリーミングサービスについて、S3 標準バケット対応と S3 Access Points (FSx for ONTAP) 対応を調査した。

| # | サービス | S3 標準バケット対応 | S3 AP ARN 対応 | S3 AP Alias 対応 | 備考 |
|---|---------|:---:|:---:|:---:|------|
| 1 | **AWS IoT Greengrass Stream Manager** | ✅ (S3 Export destination) | ❌ | 未検証 | S3ExportTaskDefinition は bucketName を要求。ARN 形式非対応 |
| 2 | **Amazon Data Firehose (旧 Kinesis Data Firehose)** | ✅ (S3 Destination) | ❌ | 未検証 | ExtendedS3DestinationConfiguration の BucketARN は `arn:aws:s3:::example-bucket` 形式のみ |
| 3 | **AWS IoT Core ルールエンジン (S3 Action)** | ✅ (bucket パラメータ) | ❌ | 未検証 | S3 ルールアクションは `bucket` (バケット名文字列) を要求 |
| 4 | **AWS IoT SiteWise (Cold Tier Storage)** | ✅ (S3 バケット指定) | ❌ | 未検証 | `put-storage-configuration` の `s3ResourceArn` は S3 バケット ARN のみ |
| 5 | **AWS IoT SiteWise (Buffered Destination)** | ✅ (S3 バケット) | ❌ | 未検証 | エッジデータの一時バッファとして S3 バケット指定 |
| 6 | **AWS IoT SiteWise (Bulk Export)** | ✅ (S3 バケット) | ❌ | 未検証 | アセットモデル/データのバルクエクスポート先は S3 バケット |

### 1.2 S3 AP Alias による回避可能性

AWS は 2021 年に [S3 Access Points Aliases](https://aws.amazon.com/about-aws/whats-new/2021/07/amazon-s3-access-points-aliases-allow-application-requires-s3-bucket-name-easily-use-access-point/) を発表しており、S3 バケット名を要求するアプリケーションで Access Point Alias を代替使用できる場合がある。ただし:

- **FSx for ONTAP S3 AP の Alias は `{ap-name}-{random}-s3alias` 形式** — 一部サービスではバケット名のバリデーションが通らない可能性
- **Alias はすべてのサービスで動作保証されていない** — AWS ドキュメントには「Amazon EMR, Amazon Storage Gateway, Amazon Athena で動作確認済み」と記載あり。IoT サービスでの動作は未確認
- **FSx for ONTAP S3 AP は一部 S3 API のみサポート** — AbortMultipartUpload, CompleteMultipartUpload, CreateMultipartUpload, DeleteObject, GetObject, HeadObject, ListMultipartUploads, ListObjectsV2, ListParts, PutObject, UploadPart が対応

### 1.3 影響範囲

| 影響を受けるアーキテクチャパターン | 回避策 | 回避策のデメリット |
|----------------------------------|--------|-------------------|
| Greengrass → 直接 FSx for ONTAP へデータ送信 | カスタムコンポーネントで boto3 PutObject | Stream Manager のオフラインバッファ/リトライ機能が使えない。自前実装が必要 |
| IoT Core テレメトリ → FSx for ONTAP 直接保存 | Lambda ルールアクション経由 | Lambda コスト追加、レイテンシ増加 |
| Firehose Parquet 変換 → FSx for ONTAP 直接配信 | Lambda 集約 + PutObject、または S3 バケット経由 (非推奨) | Firehose のマネージド Parquet 変換/バッファリング機能が使えない |
| SiteWise 時系列データ → FSx for ONTAP 直接保存 | S3 バケット経由 + DataSync | ストレージ二重持ち、遅延増加 |

---

## 2. AWS サポート 機能改善要望 (ドラフト)

以下は AWS サポートケースとして提出する機能改善要望のドラフト。

---

### Case 1: AWS IoT Greengrass Stream Manager — S3 Access Points 対応

**Case Type**: Technical Support
**Service**: AWS IoT Greengrass
**Severity**: General Guidance
**Subject**: Feature Request — S3 Access Points (FSx for ONTAP) support in Stream Manager S3 Export

---

**Description:**

#### Current Behavior

AWS IoT Greengrass Stream Manager の S3ExportTaskDefinition では、エクスポート先として S3 バケット名 (`bucket`) のみ指定可能です。S3 Access Point ARN (`arn:aws:s3:region:account-id:accesspoint/name`) や S3 AP Alias を指定する方法がありません。

#### Requested Behavior

Stream Manager の S3 Export destination に、S3 Access Point ARN (FSx for ONTAP / FSx for OpenZFS / 標準 S3 バケット AP) を指定できるようにしていただきたい。

#### Business Impact / Use Case

IoT/エッジデバイスから収集したデータを **FSx for ONTAP** に直接集約し、S3 Access Points 経由で AWS 分析サービス (Athena, Glue, SageMaker, Bedrock) に供給するアーキテクチャを構築しています。

**S3 標準バケットを経由する問題:**
- IoT ワークロードは大量の小ファイル (1KB-1MB) を高頻度で生成 → S3 PUT 課金が膨大 ($0.005/1000 requests × 数百万 writes/月)
- FSx for ONTAP 上のデータと S3 バケットのデータが二重持ちになり、DataSync 同期コスト + 遅延が発生
- S3 バケットは LIST 操作でオブジェクト数に応じてレスポンスが劣化。FSx for ONTAP の B-tree ベースディレクトリは数百万ファイルでも高速

**S3 AP 直接書き込みのメリット:**
- 単一ストレージ (FSx for ONTAP) にデータ集約 → NFS/SMB/S3 マルチプロトコルアクセス
- FlexCache によるマルチサイト低遅延データ配信が即座に利用可能
- ONTAP インライン重複排除/圧縮により IoT 小ファイルのストレージ効率 40-60% 改善
- 容量課金 (SSD/HDD) のため、API コール数に依存しないコスト構造

**具体的なユースケース:**
1. 製造品質検査: Raspberry Pi + カメラ → Greengrass Stream Manager → FSx for ONTAP S3 AP → Bedrock Vision 分析 → FlexCache でオンプレ QA チームに配信
2. 予知保全テレメトリ: 振動/温度センサー → Parquet バッチ → FSx for ONTAP → S3 AP 経由 SageMaker 学習
3. エッジ AI モデル配信: SageMaker 学習済みモデル → FSx for ONTAP Origin → FlexCache → エッジ GPU デバイスに NFS 配信

**現在の回避策と問題:**
カスタムコンポーネントで boto3 PutObject を S3 AP ARN に対して実行していますが、Stream Manager が持つ以下の機能が利用できません:
- マネージドなオフラインバッファリング (ネットワーク断時のローカルキューイング)
- 自動リトライとエクスポネンシャルバックオフ
- バンド幅制御とスロットリング
- S3 マルチパートアップロードの自動管理

これらを自前で実装するコストと品質リスクが大きく、Stream Manager が S3 AP ARN をネイティブサポートすれば大幅に開発工数を削減できます。

#### Environment

- AWS Region: ap-northeast-1
- IoT Greengrass V2 (latest)
- FSx for ONTAP (ONTAP 9.15.1+)
- S3 Access Points for FSx for ONTAP

---

### Case 2: Amazon Data Firehose — S3 Access Points 対応

**Case Type**: Technical Support
**Service**: Amazon Data Firehose
**Severity**: General Guidance
**Subject**: Feature Request — S3 Access Points (FSx for ONTAP) as delivery destination

---

**Description:**

#### Current Behavior

Amazon Data Firehose の S3 Destination Configuration (`BucketARN`) は `arn:aws:s3:::example-bucket` 形式の S3 バケット ARN のみ受け付けます。FSx for ONTAP S3 Access Point ARN (`arn:aws:s3:region:account-id:accesspoint/name`) は指定できません。

#### Requested Behavior

Firehose の S3 Destination に S3 Access Point ARN を指定可能にし、FSx for ONTAP / FSx for OpenZFS ボリュームへの直接配信をサポートしていただきたい。

#### Business Impact / Use Case

IoT Core MQTT → Firehose → S3 は IoT データレイク構築の標準パターンですが、FSx for ONTAP をデータプラットフォームとして採用している場合、S3 バケットが不要な中間層になります。

**現在の問題:**
- Firehose の Parquet 変換 + バッファリングは優れた機能だが、出力先が S3 バケットに限定されるため FSx for ONTAP に到達するまでに追加のデータ移動 (DataSync) が必要
- 100+ IoT デバイス × 1msg/sec × 30日 = 約 2.6 億メッセージ。S3 PUT 課金 + DataSync 転送コスト + FSx for ONTAP ストレージ = 3 層のコスト発生
- Firehose → FSx for ONTAP S3 AP に直接配信できれば、S3 バケット層を排除しストレージコスト 50% 削減、レイテンシ数分→即時

**具体的なユースケース:**
- IoT Core MQTT → Firehose (Parquet 変換 + 60s バッファ) → FSx for ONTAP S3 AP → FlexCache でオンプレ GPU/HPC に配信
- FSx for ONTAP の FabricPool により、30日超のデータを自動的に容量プールへ階層化

#### Environment

- AWS Region: ap-northeast-1
- Amazon Data Firehose (IoT Core as source)
- FSx for ONTAP (ONTAP 9.15.1+)
- S3 Access Points for FSx for ONTAP

---

### Case 3: AWS IoT Core ルールエンジン S3 Action — S3 Access Points 対応

**Case Type**: Technical Support
**Service**: AWS IoT Core
**Severity**: General Guidance
**Subject**: Feature Request — S3 Access Points (FSx for ONTAP) support in IoT Core S3 rule action

---

**Description:**

#### Current Behavior

IoT Core ルールエンジンの S3 アクションは `bucket` パラメータとして S3 バケット名 (文字列) を受け付けます。S3 Access Point ARN や Alias を指定する方法がドキュメントに記載されていません。

#### Requested Behavior

IoT Core S3 ルールアクションの destination パラメータに、S3 Access Point ARN を指定できるようにしていただきたい（または `bucket` フィールドに S3 AP Alias を受け付けるバリデーション緩和）。

#### Business Impact / Use Case

IoT デバイスのテレメトリ (MQTT メッセージ) を Lambda を介さず直接 FSx for ONTAP に保存したい。

**現在の問題:**
- IoT Core → S3 ルールアクションはサーバーレスでシンプルだが、FSx for ONTAP S3 AP に書けない
- 回避策として Lambda ルールアクション経由で PutObject を実行 → Lambda の呼び出しコスト + コールドスタートレイテンシが追加
- 100デバイス × 1msg/sec = 8.64万 Lambda 呼び出し/日。S3 ルールアクションなら Lambda コスト $0 で済むパターン

**具体的なユースケース:**
- 低頻度テレメトリ (温湿度、5分間隔) → IoT Core S3 Action → FSx for ONTAP S3 AP → Athena 分析

#### Environment

- AWS Region: ap-northeast-1
- AWS IoT Core (MQTT)
- FSx for ONTAP (ONTAP 9.15.1+)
- S3 Access Points for FSx for ONTAP

---

### Case 4: AWS IoT SiteWise — Cold Tier / Buffered Destination / Bulk Export の S3 AP 対応

**Case Type**: Technical Support
**Service**: AWS IoT SiteWise
**Severity**: General Guidance
**Subject**: Feature Request — S3 Access Points (FSx for ONTAP) support for SiteWise storage configuration

---

**Description:**

#### Current Behavior

AWS IoT SiteWise の以下の機能は S3 バケット ARN のみ受け付けます:
1. Cold Tier Storage (`put-storage-configuration` → `s3ResourceArn`)
2. Buffered Destination (エッジデータの S3 バッファ)
3. Bulk Export (アセットデータの S3 エクスポート)

#### Requested Behavior

上記 3 機能の S3 destination に S3 Access Point ARN (FSx for ONTAP) を指定可能にしていただきたい。

#### Business Impact / Use Case

製造現場の OPC-UA データを SiteWise で収集し、同じ FSx for ONTAP ボリュームに時系列テレメトリと品質画像/ドキュメントを統合保存したい。

**現在の問題:**
- SiteWise Cold Tier → S3 バケット → DataSync → FSx for ONTAP のパイプラインが必要
- OPC-UA テレメトリと NFS 経由のファイルデータが別ストレージに分散 → 統合分析にはデータ移動コストが発生
- FSx for ONTAP S3 AP に直接エクスポートできれば、FlexCache で他工場に OT データを即座に配信可能

**具体的なユースケース:**
- Ignition SCADA + SiteWise Edge → SiteWise Cloud → Cold Tier → FSx for ONTAP S3 AP → FlexCache → 他工場のエンジニアリング部門

#### Environment

- AWS Region: ap-northeast-1
- AWS IoT SiteWise
- FSx for ONTAP (ONTAP 9.15.1+)
- S3 Access Points for FSx for ONTAP

---

## 3. 要望提出の推奨手順

[AWS re:Post ガイド](https://repost.aws/de/articles/ARU82W8PxQTzeF3j6AlxJwiA) および [AWS サポートケース ベストプラクティス](https://repost.aws/articles/ARF5I10rw-R7uXnfC2MRvz4Q/following-best-practices-to-create-and-manage-your-aws-support-cases) に基づく推奨手順:

### Step 1: AWS Support Center でケース作成

1. [AWS Support Center](https://console.aws.amazon.com/support/home) にアクセス
2. **Create case** → **Technical support** を選択
3. **Service**: 該当サービス (IoT Greengrass / Amazon Data Firehose / IoT Core / IoT SiteWise)
4. **Severity**: General guidance
5. **Subject**: `Feature Request — S3 Access Points (FSx for ONTAP) support in [Service Name]`
6. **Description**: 上記ドラフトの内容を記載

### Step 2: 効果的な記述のポイント

| ポイント | 詳細 |
|----------|------|
| 現在の動作を明確に | 何がサポートされていて、何が欠けているか |
| 要望する動作を具体的に | パラメータ名やフィールドレベルで指定 |
| ビジネスインパクトを定量化 | コスト削減額、レイテンシ改善値、開発工数削減 |
| ユースケースを複数提示 | 1 つのユースケースでなく、業界横断的な適用例 |
| 回避策と問題を併記 | 代替手段の存在と、それが不十分な理由 |
| 環境情報を添付 | リージョン、サービスバージョン、関連リソース |

### Step 3: 追加のエスカレーション経路

- **AWS Account Manager / TAM**: Enterprise Support 契約がある場合、TAM 経由でサービスチームへ直接フィードバック
- **AWS re:Post**: 公開ディスカッションとして投稿し、コミュニティの upvote を集める
- **AWS IoT / FSx for ONTAP ロードマップ (GitHub)**: 該当する公開ロードマップがあればイシューを作成

### Step 4: 4 ケースの提出優先順

| 優先度 | サービス | 理由 |
|--------|---------|------|
| 1 | Amazon Data Firehose | IoT データレイクの最も一般的なパイプライン。影響範囲が最大 |
| 2 | IoT Core S3 ルールアクション | サーバーレス IoT の基本パターン。Lambda 回避による即効的コスト削減 |
| 3 | Greengrass Stream Manager | エッジ書き込みの中核機能。オフラインバッファが自前実装困難 |
| 4 | IoT SiteWise | 製造業ユースケース限定だが、OT/IT 統合の重要パス |

---

## 4. 補足: S3 AP Alias での動作検証計画

Feature Request の提出と並行して、S3 AP Alias がこれらのサービスで「バケット名」として受け付けられるか検証する価値がある。

| 検証項目 | 方法 | 期待結果 |
|----------|------|----------|
| Greengrass Stream Manager + S3 AP Alias | S3ExportTaskDefinition の `bucket` に Alias を指定 | バリデーション通過 or エラー |
| IoT Core S3 Action + S3 AP Alias | ルールの `bucket` に Alias を指定 | バケット名バリデーション通過 or エラー |
| Firehose + S3 AP Alias | BucketARN に `arn:aws:s3:::{alias}` を指定 | 配信成功 or エラー |
| SiteWise + S3 AP Alias | s3ResourceArn に Alias 形式 ARN を指定 | ストレージ設定成功 or エラー |

検証結果はサポートケースに追記し、「Alias で動作しないことを確認した」旨を伝えることで、Feature Request の正当性を補強する。

---

## Related Documents

- [IoT Greengrass + FlexCache 連携シナリオ](./iot-greengrass-flexcache-integration.md)
- [S3 AP + FlexCache / SnapMirror 設計考慮事項](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/blob/main/docs/ja/s3ap-flexcache-snapmirror-considerations.md)
