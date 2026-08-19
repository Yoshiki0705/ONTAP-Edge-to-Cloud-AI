# SORACOM Flux App Specification: print-quality-monitor (Option)

> **注意**: このドキュメントは有線LANが利用できない現場で SORACOM Flux を使用する場合の設定仕様書です。
> 有線LAN環境では、主経路（Pi → NFS → ONTAP → FPolicy → Lambda → Bedrock）を使用してください。
> SIM がなくてもアプリ定義は作成可能です。

## App 基本情報

| 項目 | 値 |
|------|-----|
| App 名 | `print-quality-monitor` |
| 説明 | 3Dプリント品質監視 - カメラ画像をAI分析し異常時に通知 |

## ワークフロー定義

### Channel 1: Image Input (トリガー)

| 項目 | 値 |
|------|-----|
| Channel 名 | `image-input` |
| タイプ | SORACOM デバイス |
| プロトコル | HTTP (unified endpoint) |
| Content-Type | `image/jpeg` |
| 受信条件 | Header `X-Device-Id` が存在する |

### Channel 2: AI Analysis (アクション)

| 項目 | 値 |
|------|-----|
| Channel 名 | `ai-analysis` |
| タイプ | AI (生成AI) |
| AI プロバイダー | Amazon Bedrock |
| モデル | Claude Sonnet 4.5 |
| リージョン | ap-northeast-1 |

**プロンプト設定:**

```
あなたは3Dプリント品質検査員です。この画像を分析してください。

以下の欠陥をチェック:
- ストリンギング（糸引き）
- 層間剥離
- 反り
- 押出不足
- 押出過多
- ノズル詰まり
- レイヤーシフト
- スパゲッティ（完全失敗）

JSON形式で回答:
{"status": "normal"|"anomaly_detected", "confidence": 0.0-1.0, "severity": "low|medium|high|critical", "description": "簡潔な説明", "recommendation": "推奨アクション"}

明確な欠陥のみ報告。軽微な外観差異は無視。
```

### Channel 3: Condition (条件分岐)

| 項目 | 値 |
|------|-----|
| Channel 名 | `anomaly-check` |
| タイプ | 条件分岐 |
| 条件 | `$.status == "anomaly_detected" AND $.confidence >= 0.7` |
| True → | Channel 4 (通知) + Channel 5 (S3保存) |
| False → | Channel 5 (S3保存のみ) |

### Channel 4: Notification (通知)

| 項目 | 値 |
|------|-----|
| Channel 名 | `alert-notification` |
| タイプ | Webhook |
| URL | Slack Incoming Webhook URL (設定時に入力) |
| Method | POST |
| Content-Type | application/json |

**Payload テンプレート:**

```json
{
  "text": "🔴 3Dプリント異常検出\n*Severity*: {{severity}}\n*Description*: {{description}}\n*Recommendation*: {{recommendation}}\n*Confidence*: {{confidence}}\n*Device*: {{headers.X-Device-Id}}\n*Time*: {{timestamp}}"
}
```

### Channel 5: S3 Storage (保存)

| 項目 | 値 |
|------|-----|
| Channel 名 | `s3-storage` |
| タイプ | AWS 連携 (S3) |
| バケット | `edge-to-cloud-ai-poc-<ACCOUNT_ID>` |
| キープレフィックス | `raw/image_capture/year={{now.year}}/month={{now.month}}/day={{now.day}}/device={{headers.X-Device-Id}}/` |
| IAM Role ARN | `arn:aws:iam::<ACCOUNT_ID>:role/EdgeToCloud-SoracomIngestion-poc` |
| External ID | SORACOM Operator ID |

## データフロー図

```
[Device: Pi + Camera]
       │
       │ HTTP POST (image/jpeg)
       │ Headers: X-Device-Id, X-Timestamp
       ▼
[Channel 1: image-input]
       │
       ▼
[Channel 2: ai-analysis] ← Bedrock Claude Sonnet 4.5
       │
       ▼
[Channel 3: anomaly-check]
       │
       ├── anomaly_detected (conf >= 0.7)
       │       │
       │       ├──→ [Channel 4: Slack通知]
       │       └──→ [Channel 5: S3保存]
       │
       └── normal
               └──→ [Channel 5: S3保存]
```

## コンソール設定手順

1. https://console.soracom.io にログイン
2. 左メニュー → **Flux** → **アプリ一覧** → **新規作成**
3. アプリ名: `print-quality-monitor`
4. **チャンネル追加** で上記 Channel 1-5 を順に作成
5. 各チャンネル間の接続（矢印）を設定
6. **保存** → **有効化**

## テスト方法（SIM なし）

Flux アプリ作成後、SORACOM CLI または API でテストデータを送信可能:

```bash
# SORACOM CLI でテスト（要: soracom CLI インストール + 認証設定）
# 実際のデバイスからの送信をシミュレート
soracom devices send-data \
  --device-id rpi5-001 \
  --content-type image/jpeg \
  --data @/path/to/test-image.jpg
```

> **注意**: Flux の AI 分析機能は SORACOM プラットフォーム上で実行されるため、
> 自前の Lambda とは独立して動作します。Phase 1 では Flux のみ使用し、
> Phase 2 で Lambda に切り替える（またはFlux → Lambda 呼び出しに変更する）判断をします。

## Phase 1 → Phase 2 切り替え判断基準

| 条件 | Phase 1 (Flux のみ) | Phase 2 (Lambda に移行) |
|------|---------------------|------------------------|
| プロンプトのカスタマイズ頻度 | 月1回以下 | 週1回以上 |
| 分析後のアクション | 通知のみ | プリンター停止API、ONTAP連携 |
| コスト最適化の必要性 | 不要（低頻度） | 必要（2段階分析） |
| データ加工の複雑さ | シンプル（そのまま保存） | 複雑（メタデータ付与、変換） |
| 複数デバイス対応 | 1-3台 | 4台以上 |
