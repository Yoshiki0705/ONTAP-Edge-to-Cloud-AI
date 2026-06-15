# Kafka 統合設計

> 作成日: 2026-06-15
> ステータス: 準備中（Managed Kafka デプロイ待ち）

---

## 1. 概要

エッジデバイス (Raspberry Pi) → Kafka → ClickHouse の接続を設計する。
Kafka + ClickHouse は managed open source platform (オンプレミス VM デプロイ) として提供される。

---

## 2. デプロイメントトポロジー

```
[Tokyo Lab LAN]
+------------------------------------------------------+
|                                                      |
|  [Pi 5]        [ESXi Host (DL380G10)]               |
|  10.x.x.x     +---------------------------+         |
|     |          | Kafka VM    (managed)     |         |
|     |          | ClickHouse VM (managed)   |         |
|     |          +---------------------------+         |
|     |                    |                           |
|     +----[LAN]-----------+                           |
|                          |                           |
|  [ONTAP FAS2750]         |                           |
|  NFS: vol_images   ------+                           |
|  S3: backup bucket (ClickHouse backup)               |
|                                                      |
+------------------------------------------------------+
```

### ネットワーク要件

| 接続 | Protocol | Port | 方向 |
|------|----------|------|------|
| Pi → Kafka | TCP | 9092 (plaintext) or 9093 (TLS) | outbound |
| Pi → ONTAP NFS | TCP | 2049 | outbound |
| Kafka → ClickHouse | TCP | 9000/8123 | internal (VM間) |
| ClickHouse → ONTAP S3 | TCP | 443 (HTTPS) | backup |

---

## 3. エッジ側 Kafka 設定

### 3.1 接続設定 (.env)

```bash
# Kafka broker が利用可能になったら以下を設定
KAFKA_ENABLED=true
KAFKA_BOOTSTRAP_SERVERS=<kafka-vm-ip>:9092

# TLS が有効な場合 (推奨)
# KAFKA_SECURITY_PROTOCOL=SSL
# KAFKA_SSL_CA_LOCATION=/etc/ssl/certs/kafka-ca.pem
```

### 3.2 Topic 設計

| Topic | Partition Key | 内容 |
|-------|--------------|------|
| `factory.events.raw` | `site_id-equipment_id` | 全イベント (primary) |
| `factory.events.quality` | `event_id` | AI 分析結果 |
| `factory.events.anomaly` | `event_id` | 異常検知 |
| `factory.events.dlq` | — | 処理失敗 |

### 3.3 イベントフロー

```
Pi: simple_capture.py
  → ONTAP NFS に画像保存
  → Kafka (factory.events.raw) に payload_arrival event publish
  → (optional) Lambda invoke で AI 分析
  → Kafka (factory.events.quality) に quality_event publish

ClickHouse:
  → kafka_events_raw テーブルで consume
  → Materialized View で rollup / anomaly detection
  → payload_manifest テーブルで ONTAP 上のファイル参照を管理
```

---

## 4. 切断時の動作 (Disconnection Resilience)

| 状態 | 動作 |
|------|------|
| Kafka 正常 | イベントを即時 publish |
| Kafka 到達不能 | ローカルバッファ (`/tmp/kafka-buffer/`) に JSON 保存 |
| Kafka 復旧後 | `replay_buffer()` で時系列順に再送 |
| ONTAP 正常 | 画像/結果は常に ONTAP NFS に保存（Kafka 状態に依存しない） |

**重要**: ONTAP への書き込みは Kafka の状態に依存しない。ペイロード保存は常に成功し、メタデータイベントのみが Kafka 依存。

---

## 5. ONTAP S3 (ClickHouse バックアップ用)

ClickHouse のバックアップ先として ONTAP S3 protocol を使用:

```
# ONTAP 側設定 (FAS2750)
# 1. S3 用 SVM 作成
vserver create -vserver svm-s3 -subtype default

# 2. S3 サービス有効化
vserver object-store-server create -vserver svm-s3 -object-store-server s3-backup

# 3. バケット作成
vserver object-store-server bucket create -vserver svm-s3 -bucket clickhouse-backup

# 4. ユーザー + ポリシー作成
vserver object-store-server user create -vserver svm-s3 -user clickhouse-backup-user
vserver object-store-server bucket policy statement create ...
```

---

## 6. 検証計画

### Phase 1: 接続確認 (Kafka デプロイ後)

```bash
# Pi から Kafka broker への接続テスト
python3 -c "
from confluent_kafka import Producer
p = Producer({'bootstrap.servers': '<kafka-vm-ip>:9092'})
p.produce('test-topic', key='test', value='hello from pi')
p.flush()
print('OK')
"
```

### Phase 2: E2E テスト

```bash
# Pi でキャプチャ → Kafka publish → ClickHouse 確認
KAFKA_ENABLED=true KAFKA_BOOTSTRAP_SERVERS=<ip>:9092 \
  python3 simple_capture.py --no-analyze

# ClickHouse で確認
clickhouse-client --query "SELECT count() FROM kafka_events_raw WHERE source_id = 'rpi5-001'"
```

### Phase 3: 異常検知デモ

```bash
# 連続キャプチャ → AI分析 → 異常検知 → ClickHouse ダッシュボード
KAFKA_ENABLED=true S3_BUCKET=<bucket> \
  python3 simple_capture.py --loop
```

---

## 7. 未決事項

| 項目 | 状態 | 依存 |
|------|------|------|
| Kafka VM IP アドレス | 待ち | Instaclustr デプロイ |
| TLS 証明書 | 待ち | PoC ドキュメント承認後 |
| ONTAP S3 バケット作成 | 進行中 | FAS2750 アクセス |
| ClickHouse テーブル DDL | Lakehouse プロジェクトで設計中 | v3 schema 確定 |
