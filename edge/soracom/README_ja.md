# SORACOM 設定ガイド（オプション: セルラー接続）

> 🌐 日本語 | [English](./README.md)

> **注意**: このガイドは有線LANが利用できない現場向けです。有線LANがある場合、主経路は Pi → NFS → ONTAP です（メイン README 参照）。SORACOM はフォールバック/遠隔接続オプションとして位置づけます。

有線LANがない現場でのセルラー接続設定手順を説明します。

## 前提条件

- SORACOM アカウント（日本カバレッジ、plan-D）
- IoT SIM がアクティベート済み・登録済み
- AWS インフラがデプロイ済み（CloudFormation スタック `edge-to-cloud-ai-poc`）

## アーキテクチャ

```
Raspberry Pi → SORACOM Air (セルラー) → SORACOM Funnel → AWS Kinesis
                                        → SORACOM Flux  → AWS S3 + Bedrock
```

## 1. SORACOM Funnel 設定（センサーデータ → Kinesis）

Funnel はデバイスデータを AWS Kinesis に直接転送します。デバイス側のコード変更は不要です。

### Step 1: IAM ロールの ExternalId 更新

CloudFormation スタックで `EdgeToCloud-SoracomIngestion-poc` ロールは作成済みです。
実際の SORACOM オペレーター ID で ExternalId を更新してください:

```bash
# SORACOM オペレーター ID の確認
# コンソール: https://console.soracom.io → 右上のオペレーター ID

# CloudFormation スタックを実際のオペレーター ID で更新
aws cloudformation update-stack \
  --stack-name edge-to-cloud-ai-poc \
  --use-previous-template \
  --parameters \
    ParameterKey=Environment,UsePreviousValue=true \
    ParameterKey=SoracomOperatorId,ParameterValue=<YOUR_OPERATOR_ID> \
    ParameterKey=AlertEmail,UsePreviousValue=true \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### Step 2: SORACOM コンソールで Funnel を設定

1. **SORACOM コンソール** → **SIM グループ** → グループを作成または選択
2. **SORACOM Funnel** 設定に移動
3. 以下を設定:

| 設定項目 | 値 |
|---------|-----|
| 有効 | ON |
| 転送先サービス | Amazon Kinesis Data Streams |
| 認証情報 | AWS IAM ロール |
| ロール ARN | `arn:aws:iam::<ACCOUNT_ID>:role/EdgeToCloud-SoracomIngestion-poc` |
| External ID | SORACOM オペレーター ID |
| リージョン | `ap-northeast-1` |
| ストリーム名 | `edge-to-cloud-poc-ingestion` |
| コンテンツタイプ | JSON |

### Step 3: SIM をグループに割り当て

1. **SIM 管理** に移動
2. IoT SIM を選択
3. 設定済みグループに割り当て

### Step 4: 動作確認

Raspberry Pi から（SORACOM SIM 接続状態で）:

```bash
# Funnel にテストデータを送信
curl -X POST http://funnel.soracom.io \
  -H "Content-Type: application/json" \
  -d '{
    "schema_version": "1.0",
    "message_id": "test-001",
    "device_id": "rpi5-001",
    "timestamp": "2026-05-29T10:00:00Z",
    "message_type": "sensor_reading",
    "payload": {
      "readings": [{"sensor_id": "test", "sensor_type": "temperature", "values": {"temperature_celsius": 25.0}}]
    }
  }'
```

Kinesis にデータが到着したか確認:
```bash
aws kinesis get-shard-iterator \
  --stream-name edge-to-cloud-poc-ingestion \
  --shard-id shardId-000000000000 \
  --shard-iterator-type LATEST \
  --region ap-northeast-1
```

---

## 2. SORACOM Flux 設定（カメラ画像 → AI分析）

Flux はカメラ画像キャプチャ → AI分析 → 通知の低コードワークフローを提供します。

### Step 1: Flux アプリ作成

1. **SORACOM コンソール** → **Flux** → **アプリ作成**
2. 名前: `print-quality-monitor`

### Step 2: ワークフロー定義

```
[トリガー: デバイス画像アップロード]
    ↓
[アクション: S3 に保存]
    ↓
[アクション: Lambda 呼び出し]  → edge-to-cloud-image-analyzer
    ↓
[条件: anomaly_detected AND confidence >= 0.7]
    ↓
[アクション: 通知送信 (Slack/Teams)]
```

### Step 3: S3 保存アクション設定

| 設定項目 | 値 |
|---------|-----|
| 転送先 | Amazon S3 |
| バケット | `edge-to-cloud-ai-poc-<ACCOUNT_ID>` |
| キープレフィックス | `raw/image_capture/` |
| 認証情報 | Funnel と同じ IAM ロール |

### Step 4: Lambda 呼び出し設定

| 設定項目 | 値 |
|---------|-----|
| アクションタイプ | AWS Lambda |
| 関数 ARN | `arn:aws:lambda:ap-northeast-1:<ACCOUNT_ID>:function:edge-to-cloud-image-analyzer` |
| リージョン | `ap-northeast-1` |

---

## 3. SORACOM Harvest（プロトタイピング / 可視化）

AWS 設定なしで素早くプロトタイピングする場合、Harvest がデータ保存・可視化を提供します。

### Harvest Data の有効化

1. **SIM グループ** → **SORACOM Harvest Data**
2. 有効: ON

### データ送信

```bash
curl -X POST http://harvest.soracom.io \
  -H "Content-Type: application/json" \
  -d '{"temperature": 24.5, "humidity": 45.2}'
```

### ダッシュボード表示

**SORACOM コンソール** → **Harvest Data** → SIM 選択 → グラフ表示

---

## 4. ネットワークセキュリティ（オプション: VPG）

本番環境では SORACOM VPG（Virtual Private Gateway）によるプライベート接続を検討:

- SORACOM と AWS VPC 間の専用 VPN を作成
- デバイス→クラウド通信のインターネット露出を排除
- コスト増（約 $100/月）だがセキュリティ態勢を改善

---

## トラブルシューティング

| 問題 | 確認事項 |
|------|---------|
| Funnel データが到着しない | SIM が正しいグループに所属しているか確認、コンソールで Funnel ログを確認 |
| IAM 権限エラー | ExternalId がオペレーター ID と一致しているか確認、ロール信頼ポリシーを確認 |
| Flux ワークフローが起動しない | デバイスが正しいエンドポイントに送信しているか確認、Flux アプリがアクティブか確認 |
| 高レイテンシ | 電波強度を確認（SORACOM コンソール）、データ圧縮を検討 |
