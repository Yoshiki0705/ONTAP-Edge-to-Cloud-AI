# Demo Guide: ONTAP Telemetry Analytics

## 所要時間

- 初回セットアップ: 1時間
- デモ実行: 5分（収集開始）、翌日以降に分析

## 事前準備

### 1. ONTAP サービスアカウント作成

```bash
# ONTAP CLI
security login create -vserver svm-iot \
  -user-or-group-name svc-iot-telemetry \
  -application http \
  -authentication-method password \
  -role iot-readonly

security login role create -vserver svm-iot \
  -role iot-readonly \
  -cmddirname "volume show" \
  -access readonly
```

### 2. NFS ボリューム作成 + マウント

```bash
# ONTAP CLI
vol create -vserver svm-iot -volume vol_telemetry -aggregate aggr1 -size 50GB -junction-path /vol_telemetry

# Pi 側
sudo mkdir -p /mnt/ontap/telemetry
sudo mount -t nfs <ONTAP_DATA_LIF_IP>:/vol_telemetry /mnt/ontap/telemetry
```

### 3. 環境変数設定

```bash
cd edge/raspberry-pi/sensors
cp .env.example .env
# .env を編集:
#   ONTAP_HOST=<ONTAP_DATA_LIF_IP>
#   ONTAP_USER=svc-iot-telemetry
#   ONTAP_PASSWORD=<PASSWORD>
#   OUTPUT_PATH=/mnt/ontap/telemetry
```

## デモ実行

### テレメトリ収集開始

```bash
cd edge/raspberry-pi/sensors
python ontap_telemetry.py
```

期待される出力:
```
Starting ONTAP telemetry collector: host=192.0.2.10, user=svc-iot-telemetry, interval=60s, output=/mnt/ontap/telemetry
Connected to cluster: edge-cluster-01 (NetApp Release 9.15.1)
Collections: 10, volumes tracked: 3
```

### 収集データ確認

```bash
ls /mnt/ontap/telemetry/2026/06/01/
# 20260601T100000Z_rpi5-001.json
# 20260601T100100Z_rpi5-001.json
# ...

cat /mnt/ontap/telemetry/2026/06/01/20260601T100000Z_rpi5-001.json | python3 -m json.tool
```

### Athena で分析（SnapMirror + S3 AP 設定後）

```sql
SELECT
  volume_name,
  avg(iops_total) AS avg_iops,
  max(latency_write_us) AS max_write_latency_us,
  max(capacity_used_pct) AS max_capacity_pct
FROM processed_ontap_metrics
WHERE year = '2026' AND month = '06'
GROUP BY volume_name;
```

## 確認ポイント

| 確認項目 | 方法 |
|---------|------|
| JSON が ONTAP に保存されている | `ls /mnt/ontap/telemetry/2026/` |
| メトリクスが正しい | JSON 内の iops/latency/capacity 値を確認 |
| 1分間隔で収集されている | ファイルのタイムスタンプ差を確認 |
| SnapMirror 同期 | ONTAP CLI: `snapmirror show` |

## トラブルシューティング

| 問題 | 確認 |
|------|------|
| REST API 接続失敗 | `curl -k -u svc-iot-telemetry https://<ONTAP>/api/cluster` |
| Permission denied | サービスアカウントのロール確認 |
| NFS 書き込み失敗 | `df -h /mnt/ontap/telemetry`, export policy 確認 |
| データが空 | ONTAP にワークロードがあるか確認（IOPS=0 は正常） |
