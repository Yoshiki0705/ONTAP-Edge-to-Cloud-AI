# Demo Guide: 3D Print Quality Monitoring

## 所要時間

- 初回セットアップ: 2-3時間
- デモ実行: 5分

## 事前準備

### 1. AWS インフラデプロイ

```bash
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides Environment=poc \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### 2. Raspberry Pi セットアップ

[edge/raspberry-pi/SETUP.md](../../edge/raspberry-pi/SETUP.md) に従い初回セットアップを完了する。

### 3. ONTAP NFS ボリューム作成

```bash
# ONTAP CLI (System Manager or SSH)
vol create -vserver svm-iot -volume vol_images -aggregate aggr1 -size 100GB -junction-path /vol_images
vol create -vserver svm-iot -volume vol_results -aggregate aggr1 -size 10GB -junction-path /vol_results

# Export policy (Pi の IP を許可)
export-policy rule create -vserver svm-iot -policyname default \
  -clientmatch <PI_IP> -rorule sys -rwrule sys -superuser sys
```

### 4. Pi から NFS マウント

```bash
sudo mkdir -p /mnt/ontap/images /mnt/ontap/results
sudo mount -t nfs <ONTAP_DATA_LIF_IP>:/vol_images /mnt/ontap/images
sudo mount -t nfs <ONTAP_DATA_LIF_IP>:/vol_results /mnt/ontap/results

# 永続化 (/etc/fstab)
echo "<ONTAP_DATA_LIF_IP>:/vol_images /mnt/ontap/images nfs defaults 0 0" | sudo tee -a /etc/fstab
echo "<ONTAP_DATA_LIF_IP>:/vol_results /mnt/ontap/results nfs defaults 0 0" | sudo tee -a /etc/fstab
```

### 5. 環境変数設定

```bash
cd edge/raspberry-pi/camera
cp .env.example .env
# .env を編集:
#   ONTAP_NFS_PATH=/mnt/ontap/images
#   ONTAP_RESULT_PATH=/mnt/ontap/results
#   S3_BUCKET=edge-to-cloud-ai-poc-<ACCOUNT_ID>
#   LAMBDA_FUNCTION_NAME=edge-to-cloud-image-analyzer
#   AWS_REGION=ap-northeast-1
```

## デモ実行

### 単発テスト

```bash
# 1枚撮影 → ONTAP 保存 → Lambda 分析
python simple_capture.py
```

期待される出力:
```
[20260601T100000Z] Captured: 312000 bytes
[20260601T100000Z] Saved to ONTAP: /mnt/ontap/images/2026/06/01/20260601T100000Z_rpi5-001.jpg
[20260601T100000Z] Analysis: status=normal, alert_sent=False
```

### 連続運転

```bash
# 60秒間隔で連続撮影 + 分析
python simple_capture.py --loop
```

### 異常検出のデモ

3Dプリンターで意図的に失敗を起こす（ノズル温度を下げる、フィラメントを引っ張る等）と:

```
[20260601T101500Z] Captured: 298000 bytes
[20260601T101500Z] Saved to ONTAP: /mnt/ontap/images/2026/06/01/20260601T101500Z_rpi5-001.jpg
[20260601T101500Z] Analysis: status=anomaly_detected, alert_sent=True
```

→ Slack/Email に通知が届く

### 撮影のみ（Lambda 分析なし）

```bash
# ONTAP への保存のみ確認したい場合
python simple_capture.py --loop --no-analyze
```

## 確認ポイント

| 確認項目 | 方法 |
|---------|------|
| 画像が ONTAP に保存されている | `ls /mnt/ontap/images/2026/` |
| 分析結果が ONTAP に保存されている | `cat /mnt/ontap/results/2026/.../*.json` |
| S3 にも画像がある | `aws s3 ls s3://<BUCKET>/raw/image_capture/` |
| Lambda が正常動作 | CloudWatch Logs: `/aws/lambda/edge-to-cloud-image-analyzer` |
| アラートが届く | SNS → メール/Slack |

## トラブルシューティング

| 問題 | 確認 |
|------|------|
| NFS マウント失敗 | `showmount -e <ONTAP_IP>`, export policy 確認 |
| Lambda AccessDenied | IAM ロールの S3/Bedrock 権限確認 |
| Bedrock ValidationException | インファレンスプロファイル ID を使用しているか確認 |
| 画像が暗い/ブレる | カメラ位置・照明調整、JPEG quality 確認 |
