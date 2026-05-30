🌐 **日本語** | [English](TESTING_en.md)

# End-to-End Testing Guide

> ハードウェア到着後に実行する統合テスト手順。全ステップを順番に実行し、Go/No-Go を判定する。

## 実行順序

```
Day 1 (2-3時間):
  Phase A: ネットワーク + ONTAP ─── 本ドキュメント Step 1-3
  Phase B: Raspberry Pi セットアップ ─── edge/raspberry-pi/SETUP.md

Day 2 (1-2時間):
  Phase C: NFS 接続 + カメラ確認 ─── 本ドキュメント Step 4-5
  Phase D: エンドツーエンド動作確認 ─── 本ドキュメント Step 6-8

Day 3-7:
  Phase E: 24時間連続運転 ─── 本ドキュメント Step 9
  Phase F: Go/No-Go 判定 ─── 本ドキュメント Step 10
```

## 関連ドキュメント

| ドキュメント | 内容 | いつ参照するか |
|------------|------|--------------|
| [edge/raspberry-pi/SETUP.md](edge/raspberry-pi/SETUP.md) | Pi OS 書き込み〜基本設定 | Phase B |
| [edge/raspberry-pi/HARDWARE.md](edge/raspberry-pi/HARDWARE.md) | 各機器の詳細設定・参考リンク | 問題発生時 |
| [usecases/3d-print-quality/demo-guide.md](usecases/3d-print-quality/demo-guide.md) | PoC #1 デモ手順 | Phase D |
| [usecases/3d-print-quality/ontap-setup.sh](usecases/3d-print-quality/ontap-setup.sh) | ONTAP CLI コマンド | Phase A |

> **注意**: テスト時は本番データを使用しないこと。テスト用の 3D モデル（公開 STL）やダミーセンサーデータを使用する。

---

## Step 1: ネットワーク確認 (FS.com スイッチ)

```bash
# スイッチに console 接続し、VLAN が設定済みか確認
Switch# show vlan brief

# 期待: VLAN 10 (IoT-Data) が存在すること
# 未設定の場合 → edge/raspberry-pi/HARDWARE.md の FS.com セクション参照
```

**確認項目:**
- [ ] VLAN 10 (IoT-Data) が作成されている
- [ ] ONTAP ポートが trunk (VLAN 10,20,30)
- [ ] Pi 用ポートが access (VLAN 10)
- [ ] リンクアップ LED が点灯

---

## Step 2: ONTAP 基本確認

```bash
# ONTAP CLI に SSH 接続
ssh admin@<ONTAP_MGMT_IP>

# クラスタ状態確認
cluster show
system health status show

# SVM 確認（なければ作成）
vserver show
# svm-iot が存在すること

# NFS が有効か確認
vserver nfs show -vserver svm-iot
# NFS v4.1 が enabled であること
```

**確認項目:**
- [ ] クラスタが healthy
- [ ] SVM (svm-iot) が存在し running
- [ ] NFS v4.1 が有効

---

## Step 3: ONTAP ボリューム + Export Policy 作成

```bash
# ontap-setup.sh のコマンドを実行
# → usecases/3d-print-quality/ontap-setup.sh 参照

# 確認
vol show -vserver svm-iot -fields junction-path,size
export-policy rule show -vserver svm-iot
```

**確認項目:**
- [ ] vol_images が作成され junction-path /vol_images
- [ ] vol_results が作成され junction-path /vol_results
- [ ] export policy に Pi の IP が許可されている

---

## Step 4: Raspberry Pi → ONTAP NFS 接続

```bash
# Pi 上で実行

# ONTAP の NFS エクスポート確認
showmount -e <ONTAP_DATA_LIF_IP>
# /vol_images, /vol_results が表示されること

# マウント
sudo mkdir -p /mnt/ontap/images /mnt/ontap/results
sudo mount -t nfs -o vers=4.1 <ONTAP_DATA_LIF_IP>:/vol_images /mnt/ontap/images
sudo mount -t nfs -o vers=4.1 <ONTAP_DATA_LIF_IP>:/vol_results /mnt/ontap/results

# 書き込みテスト
echo "NFS test $(date)" > /mnt/ontap/images/test.txt
cat /mnt/ontap/images/test.txt
rm /mnt/ontap/images/test.txt

# マウント状態確認
df -h /mnt/ontap/images /mnt/ontap/results
mount | grep ontap
```

**確認項目:**
- [ ] showmount でエクスポートが見える
- [ ] NFS v4.1 でマウント成功
- [ ] ファイル書き込み・読み取り・削除が成功
- [ ] df でボリュームサイズが正しい

---

## Step 5: カメラ動作確認

```bash
# USB カメラ接続確認
v4l2-ctl --list-devices
# Logitech BRIO が表示されること

# テスト撮影 → ONTAP に保存
python3 -c "
import cv2
cam = cv2.VideoCapture(0)
cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
ret, frame = cam.read()
cam.release()
if ret:
    cv2.imwrite('/mnt/ontap/images/camera_test.jpg', frame)
    print(f'OK: saved to ONTAP ({frame.shape})')
else:
    print('FAIL: camera capture failed')
"

# ONTAP 上にファイルが存在するか確認
ls -la /mnt/ontap/images/camera_test.jpg
```

**確認項目:**
- [ ] カメラが認識される (/dev/video0)
- [ ] 1080p で撮影成功
- [ ] ONTAP NFS に画像が保存される
- [ ] 画像を手元に転送して目視確認（ピンボケ、暗すぎないか）

---

## Step 6: simple_capture.py 単発テスト

```bash
cd /opt/edge-camera/edge/raspberry-pi/camera
source .venv/bin/activate

# 環境変数設定
export ONTAP_NFS_PATH=/mnt/ontap/images
export ONTAP_RESULT_PATH=/mnt/ontap/results
export DEVICE_ID=rpi5-001
export S3_BUCKET=edge-to-cloud-ai-poc-<ACCOUNT_ID>
export LAMBDA_FUNCTION_NAME=edge-to-cloud-image-analyzer
export AWS_REGION=ap-northeast-1

# 単発実行
python simple_capture.py
```

**期待される出力:**
```
[20260601T100000Z] Captured: 312000 bytes
[20260601T100000Z] Saved to ONTAP: /mnt/ontap/images/2026/06/01/20260601T100000Z_rpi5-001.jpg
[20260601T100000Z] Analysis: status=normal, alert_sent=False
```

**確認項目:**
- [ ] 撮影成功（bytes 表示）
- [ ] ONTAP に保存成功（パス表示）
- [ ] Lambda 分析成功（status 表示）
- [ ] S3 にも画像がある: `aws s3 ls s3://<BUCKET>/raw/image_capture/`

---

## Step 7: Lambda + Bedrock 分析確認

```bash
# CloudWatch Logs で Lambda 実行を確認
aws logs tail /aws/lambda/edge-to-cloud-image-analyzer \
  --since 5m --region ap-northeast-1

# 分析結果が ONTAP に保存されているか
ls /mnt/ontap/results/
cat /mnt/ontap/results/2026/06/01/*.json | python3 -m json.tool
```

**確認項目:**
- [ ] Lambda が正常実行（エラーなし）
- [ ] Bedrock が応答（status: normal or anomaly_detected）
- [ ] 結果 JSON が ONTAP に保存されている
- [ ] confidence 値が妥当（0.8-1.0）

---

## Step 8: CloudWatch 確認

```bash
# ダッシュボード確認
# → AWS Console: CloudWatch → Dashboards → edge-to-cloud-ai-poc

# アラーム状態確認
aws cloudwatch describe-alarms \
  --alarm-name-prefix edge-to-cloud \
  --query 'MetricAlarms[].{Name:AlarmName,State:StateValue}' \
  --output table --region ap-northeast-1

# カスタムメトリクスが発行されているか
aws cloudwatch get-metric-data \
  --metric-data-queries '[{"Id":"m1","MetricStat":{"Metric":{"Namespace":"EdgeToCloud/PrintQuality","MetricName":"QualityScore"},"Period":300,"Stat":"Average"}}]' \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --region ap-northeast-1
```

**確認項目:**
- [ ] ダッシュボードに Lambda メトリクスが表示
- [ ] アラームが OK 状態（INSUFFICIENT_DATA でないこと）
- [ ] カスタムメトリクス (QualityScore) にデータポイントがある

---

## Step 9: 24時間連続運転

```bash
# 連続撮影開始
python simple_capture.py --loop

# または systemd サービスとして
# (SETUP.md Step 7 参照)
```

**24時間後に確認:**
```bash
# 画像数カウント
find /mnt/ontap/images/$(date +%Y/%m/%d) -name "*.jpg" | wc -l
# 期待: ~1440 (60秒間隔 × 24時間)

# エラー数確認
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=edge-to-cloud-image-analyzer \
  --start-time $(date -u -v-24H +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 --statistics Sum \
  --region ap-northeast-1

# ONTAP ボリューム使用量
df -h /mnt/ontap/images
```

**確認項目:**
- [ ] 画像数が期待値の 95% 以上（~1368枚以上）
- [ ] Lambda エラー数が 0 または極少
- [ ] ONTAP ボリュームが満杯になっていない
- [ ] Pi が安定動作（再起動なし、メモリリークなし）

---

## Step 10: Go/No-Go 判定

| 指標 | 目標 | 実測値 | 判定 |
|------|------|--------|------|
| キャプチャ成功率 | ≥ 99.5% | ___% | ☐ |
| NFS 書き込み成功率 | ≥ 99.0% | ___% | ☐ |
| AI 検出精度 | ≥ 70% (Phase 1) | ___% | ☐ |
| キャプチャ→アラート | ≤ 60秒 | ___秒 | ☐ |
| 誤検知率 | ≤ 20% | ___% | ☐ |
| システム稼働率 (24h) | ≥ 95% | ___% | ☐ |
| 月間コスト見込み | ≤ ¥5,000 | ¥___ | ☐ |

### 判定基準

| 判定 | 条件 | 次のアクション |
|------|------|--------------|
| **Go** | 全指標達成 | Phase 2 へ（FPolicy、アクションワークフロー） |
| **Conditional Go** | 5/7 以上達成 | 未達項目の改善計画を立てて Phase 2 へ |
| **No-Go** | 4/7 以下 | 根本原因分析、アーキテクチャ見直し |

---

## トラブルシューティング

| 症状 | 確認 | 参考 |
|------|------|------|
| NFS マウント失敗 | `showmount -e <IP>`, export policy | [HARDWARE.md #NetApp](edge/raspberry-pi/HARDWARE.md#netapp-ontap) |
| カメラ認識しない | `v4l2-ctl --list-devices`, USB ポート変更 | [HARDWARE.md #USB Camera](edge/raspberry-pi/HARDWARE.md#usb-camera) |
| Lambda AccessDenied | IAM ロール確認、S3 バケットポリシー | [usecases/3d-print-quality/demo-guide.md](usecases/3d-print-quality/demo-guide.md) |
| Bedrock ValidationException | インファレンスプロファイル ID 確認 | [docs/ja/faq.md](docs/ja/faq.md) |
| Pi が不安定 | 電源 (27W 確認)、温度 (`vcgencmd measure_temp`) | [HARDWARE.md #Pi](edge/raspberry-pi/HARDWARE.md#raspberry-pi-5) |
| NVMe ブート失敗 | EEPROM バージョン確認 (≥2024-05-17) | [HARDWARE.md #NVMe](edge/raspberry-pi/HARDWARE.md#nvme-ssd-geekworm-x1004) |
