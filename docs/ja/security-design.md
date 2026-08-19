# セキュリティ設計

> 作成日: 2026-05-29
> 対象: PoC #1 (3Dプリント品質監視) / PoC #2 (ONTAPテレメトリ)
> ステータス: Draft

---

## 1. 設計方針

| 方針 | 理由 |
|------|------|
| 最小権限の原則 (Least Privilege) | 各コンポーネントは必要最小限の権限のみ保持 |
| デバイス認証は NFS/Kerberos + 証明書 | PoC 段階: NFSv3 (sys 認証) で迅速に開始。Phase 6 で NFS v4.1 + Kerberos に段階的移行 |
| 転送中・保存時の暗号化を必須とする | LAN/セルラー回線経由のデータ保護、S3/ONTAP 上のデータ保護 |
| シークレットはコードに含めない | 環境変数 / AWS Secrets Manager で管理 |
| ネットワークセグメンテーション | ONTAP管理プレーンとIoTデータプレーンを分離 |

---

## 2. 認証・認可フロー全体像

```
[Raspberry Pi]                    [ONTAP]                   [AWS]
┌─────────────┐                  ┌──────────────┐          ┌─────────────────────┐
│              │                  │              │          │                     │
│ NFS v4.1    │──有線LAN────→    │ FPolicy ─────│──────→   │ Lambda              │
│ + Kerberos   │  (主経路)        │              │          │   ↓                 │
│              │                  │ SnapMirror ──│──────→   │ Bedrock / Athena    │
│              │                  │              │          │                     │
└─────────────┘                  └──────────────┘          └─────────────────────┘
       │
       │ (オプション: 有線LANがない場合)
       ▼
┌─────────────┐                  ┌──────────┐             ┌─────────────────────┐
│ SIM認証      │──セルラー接続──→│ SORACOM  │──IAM Role──→│ S3 / Kinesis        │
│ (自動)       │                  │ Air/Beam │ (AssumeRole)│                     │
└─────────────┘                  └──────────┘             └─────────────────────┘
```

---

## 3. IAM ロール設計

### 3.1 ロール一覧

| ロール名 | 信頼エンティティ | 用途 |
|---------|----------------|------|
| `EdgeToCloud-SoracomIngestion` | SORACOM (外部アカウント) | (オプション: セルラー接続時のみ) Funnel/Beam からの S3/Kinesis 書き込み |
| `EdgeToCloud-KinesisProcessor` | Lambda | Kinesis ストリームからのデータ処理 |
| `EdgeToCloud-ImageAnalyzer` | Lambda | S3 画像取得 + Bedrock 呼び出し |
| `EdgeToCloud-GlueETL` | Glue | S3 読み書き + Data Catalog 更新 |
| `EdgeToCloud-AthenaQuery` | IAM User/Role | Athena クエリ実行 + S3 結果書き込み |
| `EdgeToCloud-BedrockInvoke` | Lambda | Bedrock モデル呼び出し専用 |

### 3.2 ポリシー詳細

#### EdgeToCloud-SoracomIngestion (オプション: セルラー接続時のみ)

SORACOM Funnel/Beam が AssumeRole で使用するロール:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowKinesisWrite",
      "Effect": "Allow",
      "Action": [
        "kinesis:PutRecord",
        "kinesis:PutRecords"
      ],
      "Resource": "arn:aws:kinesis:${AWS_REGION}:${ACCOUNT_ID}:stream/edge-to-cloud-*"
    },
    {
      "Sid": "AllowS3Write",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/raw/*"
    }
  ]
}
```

信頼ポリシー (SORACOM の AWS アカウントを信頼):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::762707677580:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "${SORACOM_OPERATOR_ID}"
        }
      }
    }
  ]
}
```

> **注**: `762707677580` は SORACOM の公開 AWS アカウント ID（[公式ドキュメント](https://developers.soracom.io/en/docs/funnel/)に記載）。ExternalId には SORACOM オペレーター ID を設定。

#### EdgeToCloud-ImageAnalyzer

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3Read",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/raw/image_capture/*"
    },
    {
      "Sid": "AllowBedrockInvoke",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "arn:aws:bedrock:${AWS_REGION}::foundation-model/anthropic.claude-*"
    },
    {
      "Sid": "AllowResultWrite",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/processed/image_analysis/*"
    },
    {
      "Sid": "AllowSNSPublish",
      "Effect": "Allow",
      "Action": [
        "sns:Publish"
      ],
      "Resource": "arn:aws:sns:${AWS_REGION}:${ACCOUNT_ID}:edge-to-cloud-alerts"
    }
  ]
}
```

#### EdgeToCloud-GlueETL

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3ReadWrite",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::${BUCKET_NAME}/raw/*",
        "arn:aws:s3:::${BUCKET_NAME}/processed/*",
        "arn:aws:s3:::${BUCKET_NAME}/curated/*"
      ]
    },
    {
      "Sid": "AllowS3List",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}"
    },
    {
      "Sid": "AllowGlueCatalog",
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetTable",
        "glue:GetPartitions",
        "glue:CreatePartition",
        "glue:UpdateTable"
      ],
      "Resource": [
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:catalog",
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:database/edge_to_cloud_ai",
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:table/edge_to_cloud_ai/*"
      ]
    }
  ]
}
```

---

## 4. ネットワークセキュリティ

### 4.1 ネットワークセグメント設計

```
┌─────────────────────────────────────────────────────────┐
│ エッジネットワーク                                        │
│                                                         │
│  VLAN 10: IoT データプレーン                              │
│  ┌──────────┐     ┌──────────┐                          │
│  │ Pi (eth0)│────→│ ONTAP    │  NFS v4.1 (データ読み書き) │
│  │          │     │ data LIF │                          │
│  └──────────┘     └──────────┘                          │
│       │                                                 │
│  VLAN 20: ONTAP 管理プレーン (Pi からアクセス不可)         │
│  ┌──────────┐     ┌──────────┐                          │
│  │ 管理PC    │────→│ ONTAP    │  HTTPS (System Manager)  │
│  │          │     │ mgmt LIF │                          │
│  └──────────┘     └──────────┘                          │
│                                                         │
│  VLAN 30: FPolicy / REST API (制限付きアクセス)           │
│  ┌──────────┐     ┌──────────┐                          │
│  │ Pi (eth0)│────→│ ONTAP    │  FPolicy通知 + REST API   │
│  │ :限定ポート│     │ data LIF │  (ポート制限あり)         │
│  └──────────┘     └──────────┘                          │
│                                                         │
│  セルラー (SORACOM Air)                                  │
│  ┌──────────┐                                           │
│  │ Pi (usb0)│────→ インターネット → SORACOM → AWS        │
│  └──────────┘                                           │
└─────────────────────────────────────────────────────────┘
```

### 4.2 ファイアウォールルール (Pi 側: ufw)

```bash
# デフォルト: すべて拒否
sudo ufw default deny incoming
sudo ufw default deny outgoing

# ONTAP NFS (VLAN 10 のみ)
sudo ufw allow out to <ONTAP_DATA_LIF_IP> port 2049 proto tcp  # NFS
sudo ufw allow out to <ONTAP_DATA_LIF_IP> port 111 proto tcp   # portmapper

# ONTAP REST API (VLAN 30、テレメトリ収集用)
sudo ufw allow out to <ONTAP_DATA_LIF_IP> port 443 proto tcp   # HTTPS

# SORACOM (セルラーインターフェース) — オプション: セルラー接続時のみ
sudo ufw allow out on usb0 to any port 443 proto tcp   # HTTPS (Beam/Funnel)
sudo ufw allow out on usb0 to any port 8883 proto tcp  # MQTTS (IoT Core)

# DNS
sudo ufw allow out to any port 53

# SSH (管理用、特定IPのみ)
sudo ufw allow in from <ADMIN_NETWORK> to any port 22 proto tcp

sudo ufw enable
```

### 4.3 S3 バケットポリシー

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUnencryptedTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::${BUCKET_NAME}",
        "arn:aws:s3:::${BUCKET_NAME}/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    },
    {
      "Sid": "DenyIncorrectEncryptionHeader",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/*",
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-server-side-encryption": "aws:kms"
        }
      }
    }
  ]
}
```

---

## 5. 暗号化設計

| レイヤー | 方式 | 詳細 |
|---------|------|------|
| **転送中 (Pi → ONTAP)** | NFS v4.1 + Kerberos (推奨) or 専用VLAN | 主経路。PoC では専用VLAN で代替可。本番は Kerberos 必須 |
| **転送中 (Pi → SORACOM)** | TLS 1.2+ | オプション: セルラー接続時のみ。SORACOM Beam が TLS 終端 |
| **転送中 (SORACOM → AWS)** | TLS 1.2+ | オプション: セルラー接続時のみ。SORACOM → AWS 間は常に TLS |
| **保存時 (S3)** | SSE-KMS (AWS managed key) | バケットデフォルト暗号化で強制 |
| **保存時 (ONTAP)** | NVE (NetApp Volume Encryption) | AES-256、ボリューム単位で有効化 |
| **保存時 (Kinesis)** | SSE-KMS | ストリーム作成時に有効化 |

---

## 6. ONTAP 認証設計

### 6.1 REST API アクセス

| 項目 | 設定 |
|------|------|
| 認証方式 | ローカルユーザー + HTTPS 証明書認証 |
| ユーザー名 | `svc-iot-telemetry` (サービスアカウント) |
| ロール | `readonly` (カスタムロール: metrics/volumes/nodes の GET のみ) |
| アクセス元制限 | Pi の IP アドレスのみ許可 (data-interface の firewall-policy) |

```bash
# ONTAP CLI: サービスアカウント作成例
security login create -vserver svm-iot \
  -user-or-group-name svc-iot-telemetry \
  -application http \
  -authentication-method password \
  -role iot-readonly

# カスタムロール作成
security login role create -vserver svm-iot \
  -role iot-readonly \
  -cmddirname "volume show" \
  -access readonly
```

### 6.2 FPolicy 外部サーバー

| 項目 | 設定 |
|------|------|
| 通信プロトコル | TCP (FPolicy プロトコル) |
| 認証 | 相互 SSL 証明書 (ONTAP 9.13.1+) |
| Pi 側ポート | 動的割り当て (ONTAP が接続) |
| 通信方向 | ONTAP → Pi (ONTAP がクライアント) |

---

## 7. シークレット管理

| シークレット | 保管場所 | ローテーション |
|------------|---------|--------------|
| ONTAP REST API パスワード | Pi: 環境変数 (systemd EnvironmentFile) | 90日ごと |
| SORACOM API Key/Token | 使用しない (SIM認証のみ) | — |
| AWS 認証情報 | 使用しない (FPolicy→Lambda は ONTAP 側で処理、セルラー時は SORACOM AssumeRole) | — |
| FPolicy SSL 証明書 | Pi: /etc/fpolicy/certs/ (600 permission) | 1年ごと |
| SSH 鍵 (Pi 管理用) | 管理者のローカルマシン | 1年ごと |

> **重要**: Pi 上に AWS Access Key / Secret Key を配置しない。AWS アクセスは FPolicy → Lambda（ONTAP 経由）で行うか、セルラー接続時は SORACOM 経由の AssumeRole で行う。

---

## 8. デバイスハードニング (Raspberry Pi)

```bash
# 1. 不要サービスの無効化
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon
sudo systemctl disable cups

# 2. 自動セキュリティアップデート
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades

# 3. SSH ハードニング (/etc/ssh/sshd_config)
PermitRootLogin no
PasswordAuthentication no
MaxAuthTries 3
AllowUsers iot-operator

# 4. ファイルシステム保護
# /tmp を noexec でマウント
echo "tmpfs /tmp tmpfs defaults,noexec,nosuid,nodev 0 0" >> /etc/fstab

# 5. ログ監視
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

---

## 9. インシデント対応

| シナリオ | 検知方法 | 対応 |
|---------|---------|------|
| Pi の侵害 (不正プロセス) | fail2ban アラート、異常な通信パターン | Pi をネットワークから隔離、ONTAP FPolicy を無効化、SIM を一時停止 |
| ONTAP への不正書き込み | ARP/AI アラート | 自動 Snapshot → 管理者通知 → 書き込み元の特定と遮断 |
| AWS 認証情報の漏洩 | CloudTrail 異常検知 | IAM ロールの一時無効化、SORACOM ExternalId のローテーション |
| セルラー回線の不正利用 | SORACOM コンソールの通信量異常 | SIM の一時停止、通信ログの確認 |

---

## 10. データ分類

| 分類レベル | 定義 | 本プロジェクトでの例 | 保護要件 |
|-----------|------|---------------------|---------|
| **公開** | 外部公開可能 | アーキテクチャ図、公開ドキュメント | 改ざん防止のみ |
| **社内** | 社内関係者のみ | センサーデータ、テレメトリ | アクセス制御 + 暗号化 |
| **機密** | 業務上必要な者のみ | 検査画像（製品設計情報を含む可能性）| 暗号化 + 監査ログ + アクセス制限 |
| **極秘** | 特定の承認者のみ | — (本PoCでは該当なし) | 上記 + 多要素認証 + 物理的制御 |

### 本プロジェクトのデータ分類

| データ種別 | 分類 | 根拠 | 保存先 |
|-----------|------|------|--------|
| 3Dプリント画像 | 社内〜機密 | 製品形状が映る可能性 | S3 (SSE-KMS) / ONTAP (NVE) |
| センサーデータ (温湿度等) | 社内 | 環境情報、直接的な機密性は低い | S3 (SSE-KMS) |
| ONTAP テレメトリ | 社内 | インフラ構成情報を含む | S3 (SSE-KMS) |
| AI 分析結果 | 社内 | 元画像への参照を含む | S3 (SSE-KMS) |
| フィードバック記録 | 社内 | オペレーター判断の記録 | S3 (SSE-KMS) |
| 3Dモデルファイル (STL/3MF) | 機密 | 製品設計の知的財産 | ONTAP (NVE) |

> **注意**: 顧客環境で実施する場合、顧客のデータ分類ポリシーに従うこと。上記は自社ラボ環境での分類。

---

## 11. プライバシー影響評価（カメラ設置時）

カメラを設置する際は、以下のチェックを実施すること:

| チェック項目 | 対応 |
|------------|------|
| 撮影範囲に人が映り込む可能性があるか | 設置前に確認。可能性がある場合は PIA 実施 |
| 撮影対象は製品/設備のみか | カメラ画角を製品/設備に限定 |
| 従業員への事前告知は必要か | 社内規定に従い、必要に応じて掲示・説明 |
| 画像の保持期間は適切か | データ分類に基づき設定（raw: 90日→IA→Glacier） |
| 画像へのアクセス権限は最小か | IAM + S3 バケットポリシーで制限 |
| 不要になった画像の削除手順はあるか | S3 ライフサイクルポリシー + 手動削除手順 |

> **PoC（自社ラボ）**: 撮影対象は 3D プリンターのみ。人は映らない設置位置。PIA 不要。
> **顧客環境**: 顧客のプライバシーポリシーに従い、必要に応じて PIA を実施。

---

## 12. コンプライアンスチェックリスト

| 項目 | PoC | 本番 |
|------|-----|------|
| S3 暗号化 (SSE-KMS) | ✅ 必須 | ✅ 必須 |
| HTTPS 強制 (バケットポリシー) | ✅ 必須 | ✅ 必須 |
| IAM 最小権限 | ✅ 必須 | ✅ 必須 |
| CloudTrail 有効化 | ○ 推奨 | ✅ 必須 |
| VPC Flow Logs | — 不要 (VPC未使用) | ✅ 必須 |
| GuardDuty | ○ 推奨 | ✅ 必須 |
| ONTAP 監査ログ | ○ 推奨 | ✅ 必須 |
| Pi ファイアウォール (ufw) | ✅ 必須 | ✅ 必須 |
| NFS 暗号化 | ○ 専用VLAN で代替 | ✅ Kerberos 必須 |
| シークレットローテーション | ○ 手動 | ✅ 自動化 |

---

## 13. OT/IT 境界

§4 のセグメント設計は IT 側のネットワーク分離を扱っている。本節は、
そのエッジネットワークが**製造設備（OT）と同じフロアに置かれる場合**に
追加で必要になる考慮を扱う。IT 側の分離だけでは足りない理由は、
OT 側の可用性要件と障害の影響範囲が IT 側と異なることにある。

> **適用範囲の注記**: 本節は設計上の考慮事項であり、IEC 62443 の適合宣言ではない。
> 規制対象の設備に接続する場合、認証・適合性の判断は本ドキュメントの範囲外。

### 13.1 データフローは一方向に保つ

このアーキテクチャでは、エッジからクラウドへの**送信のみ**が発生する。
クラウド側から OT ネットワークへ到達する経路を作らない。

| 経路 | 方向 | 実装 |
|------|------|------|
| Pi → IoT Core (MQTT) | 送信のみ | Pi が発行する。IoT Core からの購読は行わない |
| Pi → ONTAP (NFS) | 双方向（同一 LAN 内） | VLAN 10 に閉じる |
| ONTAP → AWS (SnapMirror) | 送信のみ | ONTAP 側から開始 |
| Lambda → FSx for ONTAP S3 AP | 書き込みのみ | クラウド側から OT には届かない |

**設けない経路**: クラウドからエッジへのコマンド送信（IoT Jobs、
MQTT サブスクライブによるリモート制御、SSH のインターネット公開）。
遠隔からプリンターを停止させる機能は、同じ経路が侵害時の制御経路になる。
必要になった場合は、OT 側の独立した安全機構（物理停止、PLC 側インターロック）を
前提に設計し、クラウド経路を唯一の制御手段にしない。

### 13.2 デバイス識別はペイロードを信用しない

MQTT で認証されているのは**クライアント証明書とクライアント ID**であり、
ペイロードの中の `device_id` フィールドではない。ペイロードは発行者が
自由に書ける。

```
# IoT Core ルール SQL: 認証済みの識別子をペイロードと衝突しない名前で付与する
SELECT *, clientid() as client_id, topic(2) as topic_device_id FROM 'edge/+/telemetry'
```

Lambda 側は `client_id` → `topic_device_id` → ペイロードの `device_id` の
順に採用する（`cloud/iot_ingestion/identifiers.py`）。

**実測した問題**: 修正前は `device_id` をペイロードから取り、そのまま
S3 キーに補間していた。`device_id = "../../../etc/shadow"` を送ると
キーは `ingest/../../../etc/shadow/year=2026/...` になる。S3 は `..` を
正規化しないため、そのキーでオブジェクトが作られる。正規化するのは
**消費側**である。FSx for ONTAP S3 AP はキーを実ファイルシステムの
パスにマップし、Athena / Glue は `ingest/<device_id>/year=.../` を
Hive パーティションとして読む。つまり `..` は見た目の問題ではなく、
意図したプレフィックスの外に出る経路になる。CR/LF を含む値は
`PutObject` の metadata ヘッダに入る。

IoT ポリシーは Thing 単位に絞る。ワイルドカードの publish を許可すると、
1 台の侵害が全デバイスのデータ空間に書き込める。

```json
{
  "Effect": "Allow",
  "Action": "iot:Publish",
  "Resource": "arn:aws:iot:<region>:<account>:topic/edge/${iot:Connection.Thing.ThingName}/telemetry"
}
```

参照: [Thing policy variables](https://docs.aws.amazon.com/iot/latest/developerguide/thing-policy-variables.html)

### 13.3 障害の影響範囲を OT 側に広げない

| 障害 | エッジ側の挙動 | OT 側への影響 |
|------|--------------|--------------|
| クラウド到達不能 | ローカル SQLite バッファに蓄積（`edge/greengrass/s3ap_client/buffer.py`） | なし。設備は稼働を継続 |
| バッファ満杯 | 古いエントリから退避。`BufferFullError` | なし。監視が欠測するだけ |
| ONTAP 到達不能 | NFS 書き込み失敗 → セルラー経路へフォールバック | なし |
| Pi 障害 | 収集停止 | なし。Pi は観測のみで制御しない |

**設計上の前提**: Pi は観測専用であり、設備の制御系に入らない。
この前提が崩れる（Pi から PLC に書き込む等）場合、上表の「OT 側への影響: なし」は
すべて再評価が必要になる。

### 13.4 エッジ側に置くべきでないもの

| 置かない | 理由 | 代わりに |
|---------|------|---------|
| 長期保持の AWS 静的クレデンシャル | 物理アクセスで持ち出される | IoT Core の証明書認証、SORACOM Beam の AssumeRole |
| 平文の ONTAP 管理者資格情報 | 管理プレーンへの侵入経路 | 読み取り専用のカスタムロール（§6.1） |
| インターネットに開いた SSH | 総当たり・脆弱性の対象 | 管理 VLAN 内の特定 IP のみ（§4.2） |
| 世界書き込み可能なバッファパス | 同一ホストの他ユーザに先取り・シンボリックリンクされる | `~/.local/state/` 配下。`KAFKA_BUFFER_PATH` で明示 |

### 13.5 未対応・確認していないこと

- **NFS の暗号化**: PoC は NFSv4.1 + 専用 VLAN で代替している。
  回線が共有される環境では Kerberos が必要（§5、§12）。
- **OT プロトコルの直接収集**: Modbus / OPC-UA からの直接読み取りは
  このリポジトリでは実装していない。実装する場合、OT プロトコルは
  概して認証を持たないため、収集点をどのセグメントに置くかが
  そのまま権限境界になる。
- **IEC 62443 / NIST SP 800-82 への適合**: 評価していない。
  規制対象設備への接続は本ドキュメントの範囲外。

## 関連ドキュメント

- [品質ゲート](../agent/quality-gates.md) — この設計を検証するゲート
- [運用設計](operations-design.md)
- [データスキーマ設計](data-schema-design.md)
- [IoT Greengrass / FlexCache 統合](iot-greengrass-flexcache-integration.md)
