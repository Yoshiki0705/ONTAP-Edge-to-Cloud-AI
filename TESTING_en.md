🌐 [日本語](TESTING.md) | **English**

# End-to-End Testing Guide

> Integration test procedures to run after hardware arrives. Execute all steps in order to make a Go/No-Go decision.

## Execution Order

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

## Related Documents

| Document | Contents | When to Reference |
|----------|----------|-------------------|
| [edge/raspberry-pi/SETUP.md](edge/raspberry-pi/SETUP.md) | Pi OS flashing through basic configuration | Phase B |
| [edge/raspberry-pi/HARDWARE.md](edge/raspberry-pi/HARDWARE.md) | Detailed device setup & reference links | When issues arise |
| [usecases/3d-print-quality/demo-guide.md](usecases/3d-print-quality/demo-guide.md) | PoC #1 demo procedures | Phase D |
| [usecases/3d-print-quality/ontap-setup.sh](usecases/3d-print-quality/ontap-setup.sh) | ONTAP CLI commands | Phase A |

> **Note**: Do not use production data during testing. Use test 3D models (public STL files) and dummy sensor data.

---

## Step 1: Network Verification (FS.com Switch)

```bash
# スイッチに console 接続し、VLAN が設定済みか確認
Switch# show vlan brief

# 期待: VLAN 10 (IoT-Data) が存在すること
# 未設定の場合 → edge/raspberry-pi/HARDWARE.md の FS.com セクション参照
```

**Checklist:**
- [ ] VLAN 10 (IoT-Data) has been created
- [ ] ONTAP port is set to trunk (VLAN 10,20,30)
- [ ] Pi port is set to access (VLAN 10)
- [ ] Link-up LED is lit

---

## Step 2: ONTAP Basic Verification

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

**Checklist:**
- [ ] Cluster is healthy
- [ ] SVM (svm-iot) exists and is running
- [ ] NFS v4.1 is enabled

---

## Step 3: ONTAP Volume + Export Policy Creation

```bash
# ontap-setup.sh のコマンドを実行
# → usecases/3d-print-quality/ontap-setup.sh 参照

# 確認
vol show -vserver svm-iot -fields junction-path,size
export-policy rule show -vserver svm-iot
```

**Checklist:**
- [ ] vol_images is created with junction-path /vol_images
- [ ] vol_results is created with junction-path /vol_results
- [ ] Export policy allows the Pi's IP address

---

## Step 4: Raspberry Pi → ONTAP NFS Connection

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

**Checklist:**
- [ ] Exports are visible via showmount
- [ ] NFS v4.1 mount succeeds
- [ ] File write, read, and delete all succeed
- [ ] df shows correct volume sizes

---

## Step 5: Camera Verification

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

**Checklist:**
- [ ] Camera is recognized (/dev/video0)
- [ ] 1080p capture succeeds
- [ ] Image is saved to ONTAP NFS
- [ ] Transfer image to local machine and visually confirm (check for blur, underexposure)

---

## Step 6: simple_capture.py Single-Shot Test

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

**Expected output:**
```
[20260601T100000Z] Captured: 312000 bytes
[20260601T100000Z] Saved to ONTAP: /mnt/ontap/images/2026/06/01/20260601T100000Z_rpi5-001.jpg
[20260601T100000Z] Analysis: status=normal, alert_sent=False
```

**Checklist:**
- [ ] Capture succeeds (bytes displayed)
- [ ] Saved to ONTAP successfully (path displayed)
- [ ] Lambda analysis succeeds (status displayed)
- [ ] Image also exists in S3: `aws s3 ls s3://<BUCKET>/raw/image_capture/`

---

## Step 7: Lambda + Bedrock Analysis Verification

```bash
# CloudWatch Logs で Lambda 実行を確認
aws logs tail /aws/lambda/edge-to-cloud-image-analyzer \
  --since 5m --region ap-northeast-1

# 分析結果が ONTAP に保存されているか
ls /mnt/ontap/results/
cat /mnt/ontap/results/2026/06/01/*.json | python3 -m json.tool
```

**Checklist:**
- [ ] Lambda executes successfully (no errors)
- [ ] Bedrock responds (status: normal or anomaly_detected)
- [ ] Result JSON is saved to ONTAP
- [ ] Confidence value is reasonable (0.8-1.0)

---

## Step 8: CloudWatch Verification

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

**Checklist:**
- [ ] Dashboard shows Lambda metrics
- [ ] Alarms are in OK state (not INSUFFICIENT_DATA)
- [ ] Custom metric (QualityScore) has data points

---

## Step 9: 24-Hour Continuous Operation

```bash
# 連続撮影開始
python simple_capture.py --loop

# または systemd サービスとして
# (SETUP.md Step 7 参照)
```

**Verify after 24 hours:**
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

**Checklist:**
- [ ] Image count is ≥95% of expected (~1368 or more)
- [ ] Lambda error count is 0 or minimal
- [ ] ONTAP volume is not full
- [ ] Pi is running stably (no reboots, no memory leaks)

---

## Step 10: Go/No-Go Decision

| Metric | Target | Actual | Result |
|--------|--------|--------|--------|
| Capture success rate | ≥ 99.5% | ___% | ☐ |
| NFS write success rate | ≥ 99.0% | ___% | ☐ |
| AI detection accuracy | ≥ 70% (Phase 1) | ___% | ☐ |
| Capture → Alert latency | ≤ 60s | ___s | ☐ |
| False positive rate | ≤ 20% | ___% | ☐ |
| System uptime (24h) | ≥ 95% | ___% | ☐ |
| Estimated monthly cost | ≤ ¥5,000 | ¥___ | ☐ |

### Decision Criteria

| Decision | Condition | Next Action |
|----------|-----------|-------------|
| **Go** | All metrics met | Proceed to Phase 2 (FPolicy, action workflows) |
| **Conditional Go** | 5/7 or more met | Create improvement plan for unmet items, proceed to Phase 2 |
| **No-Go** | 4/7 or fewer | Root cause analysis, architecture review |

---

## Troubleshooting

| Symptom | What to Check | Reference |
|---------|---------------|-----------|
| NFS mount fails | `showmount -e <IP>`, export policy | [HARDWARE.md #NetApp](edge/raspberry-pi/HARDWARE.md#netapp-ontap) |
| Camera not recognized | `v4l2-ctl --list-devices`, try different USB port | [HARDWARE.md #USB Camera](edge/raspberry-pi/HARDWARE.md#usb-camera) |
| Lambda AccessDenied | Check IAM role, S3 bucket policy | [usecases/3d-print-quality/demo-guide.md](usecases/3d-print-quality/demo-guide.md) |
| Bedrock ValidationException | Verify inference profile ID | [docs/ja/faq.md](docs/ja/faq.md) |
| Pi unstable | Power supply (verify 27W), temperature (`vcgencmd measure_temp`) | [HARDWARE.md #Pi](edge/raspberry-pi/HARDWARE.md#raspberry-pi-5) |
| NVMe boot failure | Check EEPROM version (≥2024-05-17) | [HARDWARE.md #NVMe](edge/raspberry-pi/HARDWARE.md#nvme-ssd-geekworm-x1004) |
