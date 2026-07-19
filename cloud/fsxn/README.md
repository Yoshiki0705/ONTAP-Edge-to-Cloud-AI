# FSx for ONTAP Infrastructure

> ⚠️ **Cost Warning**: FSx for ONTAP costs ~$500+/month (Multi-AZ, 128 MBps, 1 TiB). Deploy only when needed for testing.

## ONTAP プラットフォーム選択ガイド

本プロジェクトのアーキテクチャはどの ONTAP プラットフォームでも動作します。用途に応じて選択してください。

| プラットフォーム | 配置 | 特徴 | 適したケース |
|----------------|------|------|-------------|
| **FAS/AFF** | オンプレミス | ハードウェアアプライアンス。高性能・大容量 | 既存 NAS、本番データ集約 |
| **ONTAP Select** | オンプレミス / VM | ソフトウェア定義。汎用サーバーや VM 上で動作 | 小規模検証、仮想環境 |
| **FSx for ONTAP** | AWS クラウド | フルマネージド。SnapMirror 先として最適。S3 AP 対応 | AWS AI 連携、SnapMirror DR |

**選び方:**
- エッジ側のデータ集約先として → **FAS/AFF** or **ONTAP Select**（オンプレ側）
- AWS AI サービスとの連携先として → **FSx for ONTAP**（S3 AP でデータコピー不要）
- SnapMirror で オンプレ → クラウドの DR/分析 → **FSx for ONTAP** をデスティネーションに

本リポジトリの CloudFormation テンプレートは **FSx for ONTAP** をデプロイします。

## Purpose

SnapMirror destination for on-premises ONTAP data. Provides S3 Access Points for AWS AI/analytics services to access aggregated data without copying.

## Architecture

```
[On-premises ONTAP] --SnapMirror--> [FSx for ONTAP] --S3 AP--> [Athena/Bedrock/SageMaker]
```

## Deploy

```bash
aws cloudformation deploy \
  --template-file cloud/fsxn/template.yaml \
  --stack-name edge-to-cloud-fsxn \
  --parameter-overrides Environment=poc \
  --region ap-northeast-1
```

## After Deployment

### 1. Create Volume (AWS CLI)

```bash
aws fsx create-volume \
  --volume-type ONTAP \
  --name vol_images_dp \
  --ontap-configuration '{
    "StorageVirtualMachineId": "<SVM_ID>",
    "JunctionPath": "/vol_images_dp",
    "SizeInMegabytes": 102400,
    "StorageEfficiencyEnabled": true,
    "OntapVolumeType": "DP"
  }'
```

### 2. Configure SnapMirror (On-premises ONTAP CLI)

```bash
# Peer clusters
cluster peer create -address-family ipv4 \
  -peer-addrs <FSX_INTERCLUSTER_IP>

# Peer SVMs
vserver peer create -vserver svm-iot \
  -peer-vserver svm-edge-to-cloud \
  -peer-cluster <FSX_CLUSTER_NAME> \
  -applications snapmirror

# Create SnapMirror relationship
snapmirror create \
  -source-path svm-iot:vol_images \
  -destination-path svm-edge-to-cloud:vol_images_dp \
  -type XDP -policy MirrorAllSnapshots

# Initialize
snapmirror initialize \
  -destination-path svm-edge-to-cloud:vol_images_dp
```

### 3. Create S3 Access Point

Configure via AWS Console or FSx for ONTAP API after volume is synced.

## Enterprise AD Demo Setup (SMB Authentication)

企業環境でのデモでは、FSx for ONTAP の SVM を Active Directory に参加させ、SMB 共有経由で認証付きファイルアクセスを実現します。

### AD パターン選択

| パターン | テンプレートパラメータ | 用途 | コスト |
|---------|---------------------|------|--------|
| **A: AWS Managed AD** | `ADPattern=ManagedAD` | PoC 最速。AD 運用不要 | ~$0.15/hr (~$110/月) |
| **B: Self-managed EC2** | `ADPattern=SelfManagedEC2` | オンプレ AD 想定の検証 | EC2 インスタンス料金 |
| **C: Existing AD** | `ADPattern=ExistingAD` | 既存ドメインに参加 | 追加コストなし |

### Step 1: AD 環境デプロイ

```bash
# パラメータをカスタマイズ
cp params/demo-ad-environment.example.json params/demo-ad-environment.local.json
# vi params/demo-ad-environment.local.json
#   - VpcId/SubnetId1/SubnetId2: FSx for ONTAP と同じ VPC・サブネットを指定
#   - AdminPassword: 強力なパスワードに変更
#   - ADPattern: 上記 A/B/C から選択

# デプロイ（Managed AD の場合 ~15-20 分）
aws cloudformation create-stack \
  --template-body file://infrastructure/demo-ad-environment.yaml \
  --stack-name edge-to-cloud-demo-ad \
  --parameters file://params/demo-ad-environment.local.json \
  --capabilities CAPABILITY_NAMED_IAM

aws cloudformation wait stack-create-complete --stack-name edge-to-cloud-demo-ad

# Outputs 確認（DNS IP、Secret ARN を取得）
aws cloudformation describe-stacks --stack-name edge-to-cloud-demo-ad \
  --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' --output table
```

### Step 2: SVM を AD ドメインに参加

```bash
# DNS IP と Secret ARN は Step 1 の Outputs から取得
./scripts/demo-ad-join-svm.sh \
  --svm-id <SVM_ID_FROM_FSXN_STACK> \
  --domain demo.edge-to-cloud.local \
  --dns-ips <DNS_IPS_FROM_AD_STACK> \
  --secret-arn <SECRET_ARN_FROM_AD_STACK>

# ドライランで確認のみ（実行しない）
./scripts/demo-ad-join-svm.sh \
  --svm-id svm-0123456789abcdef0 \
  --domain demo.edge-to-cloud.local \
  --dns-ips 198.51.100.10,198.51.100.11 \
  --secret-arn arn:aws:secretsmanager:ap-northeast-1:123456789012:secret:xxx \
  --dry-run
```

### Step 3: SMB 共有の作成とテスト

```bash
# ONTAP REST API で SMB 共有作成
MGMT_IP=$(aws fsx describe-file-systems --file-system-ids <FS_ID> \
  --query 'FileSystems[0].OntapConfiguration.Endpoints.Management.IpAddresses[0]' \
  --output text)

curl -sk -u fsxadmin:<PASSWORD> -X POST \
  "https://${MGMT_IP}/api/protocols/cifs/shares" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "edge_data",
    "path": "/vol_images",
    "svm": {"name": "svm-edge-to-cloud"}
  }'

# ドメイン参加済み Windows クライアントから接続テスト
# net use Z: \\SVMEDGETOCLOUD.demo.edge-to-cloud.local\edge_data
```

### デモシナリオでの利用

AD 参加済み SMB 共有は以下のデモで活用:
- **3D プリント品質監視**: カメラ画像を SMB 経由で FSx for ONTAP に書き込み → AI 分析
- **外観検査**: 製造ラインのカメラが Windows PC 経由で SMB 書き込み
- **ONTAP テレメトリ**: ONTAP FPolicy イベントのユーザー識別が AD ユーザー名で記録される

### Windows クライアントの AD 参加（SSM 経由）

Pattern A（Managed AD）では、SSM Association によるタグベースの自動ドメイン参加が設定されます。
新しい Windows EC2 に以下のタグを付けるだけで自動的にドメイン参加します:

```yaml
Tags:
  - Key: DomainJoin
    Value: demo.edge-to-cloud.local  # ← AD ドメイン名
```

EC2 インスタンスの IAM ロールには以下のポリシーが必須:
```yaml
ManagedPolicyArns:
  - arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  - arn:aws:iam::aws:policy/AmazonSSMDirectoryServiceAccess
```

> **既知の落とし穴**: EC2 の `SsmAssociations` プロパティにカスタム SSM Document（`aws:domainJoin` アクション）を指定する方式は **デプロイ時に失敗します**（`Document schema version, 2.2, is not supported by association that is created with instance id`）。
> 正しい方式は、`AWS::SSM::Association` リソースで AWS 管理ドキュメント `AWS-JoinDirectoryServiceDomain` を参照することです。本テンプレートはこの正しいパターンを実装済みです。

### AD 環境のクリーンアップ

```bash
# SVM から CIFS サーバーを削除（AD join 解除）
curl -sk -u fsxadmin:<PASSWORD> -X DELETE \
  "https://${MGMT_IP}/api/protocols/cifs/services/<SVM_UUID>" \
  -H "Content-Type: application/json" \
  -d '{"ad_domain": {"user": "Admin", "password": "<AD_PASSWORD>"}}'

# AD スタック削除
aws cloudformation delete-stack --stack-name edge-to-cloud-demo-ad
aws cloudformation wait stack-delete-complete --stack-name edge-to-cloud-demo-ad
```

---

## Teardown (to stop costs)

```bash
# AD 環境を先に削除（SVM が AD 参加中の場合は上記の手順で CIFS 削除してから）
aws cloudformation delete-stack --stack-name edge-to-cloud-demo-ad

# FSx for ONTAP スタック削除
aws cloudformation delete-stack --stack-name edge-to-cloud-fsxn
```
