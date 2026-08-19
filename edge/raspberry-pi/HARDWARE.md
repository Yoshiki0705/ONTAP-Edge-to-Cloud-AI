🌐 **日本語** | [English](HARDWARE_en.md)

# Hardware Setup Reference

> 各ベンダー機器のセットアップ手順と参考リンク集

## 機器一覧

| 機器 | 用途 | セットアップ難易度 |
|------|------|-----------------|
| [Raspberry Pi 5](#raspberry-pi-5) | エッジコンピュート | ★★☆ |
| [Geekworm X1004 + NVMe SSD](#nvme-ssd-geekworm-x1004) | Pi ストレージ高速化 | ★★☆ |
| [USB カメラ (Logitech BRIO 4K)](#usb-camera) | 画像キャプチャ | ★☆☆ |
| [CSI カメラ (NoIR V2)](#csi-camera) | 近赤外線撮影 | ★★☆ |
| [Bambu Lab P2S](#bambu-lab-p2s) | 3Dプリンター (監視対象) | ★★☆ |
| [FS.com S5860-24XMG](#fscom-switch) | 10GbE L3 スイッチ | ★★★ |
| [NetApp ONTAP](#netapp-ontap) | データ集約ストレージ | ★★★ |

---

## Raspberry Pi 5

### セットアップ手順

→ [SETUP.md](./SETUP.md) に詳細手順あり

### 参考リンク

| リンク | 内容 |
|--------|------|
| [Raspberry Pi 公式ドキュメント](https://www.raspberrypi.com/documentation/) | OS インストール、設定全般 |
| [Raspberry Pi Imager](https://www.raspberrypi.com/software/) | OS 書き込みツール |
| [Pi 5 NVMe Boot Guide](https://pidiylab.com/raspberry-pi-5-nvme-boot-guide/) | NVMe SSD からのブート設定 |
| [Pi 5 GPIO Pinout](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio) | GPIO ピン配置 |
| [picamera2 ドキュメント](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf) | CSI カメラ制御 |

---

## NVMe SSD (Geekworm X1004)

### セットアップ手順

1. X1004 ボードを Pi 5 の PCIe FPC コネクタに接続
2. NVMe SSD (M.2 2280) を X1004 に装着
3. EEPROM ブートオーダーを NVMe 優先に変更

```bash
# Pi 上で実行（初回は microSD から起動）
sudo rpi-eeprom-config --edit
# BOOT_ORDER=0xf641 に変更（NVMe → USB → SD → restart）

# ブートローダー更新
sudo rpi-eeprom-update -a
sudo reboot

# NVMe 認識確認
lsblk
# nvme0n1 が表示されること
```

### 注意事項

- X1004 は ASMedia ASM1182e PCIe スイッチ使用 → **PCIe Gen 2 速度に制限**（Gen 3 設定しても効果なし）
- Samsung 製 SSD は一部ブート非対応の報告あり → Kioxia 推奨
- ブートローダーバージョン **2024-05-17 以降**が必要

### 参考リンク

| リンク | 内容 |
|--------|------|
| [Geekworm X1004 Wiki](https://wiki.geekworm.com/X1004) | 公式セットアップガイド |
| [Pi 5 NVMe Boot (pidiylab)](https://pidiylab.com/raspberry-pi-5-nvme-boot-guide/) | EEPROM 設定詳細 |
| [X1004 + Coral TPU 共存](https://gist.github.com/TheNoobInventor/ef00bc82f3a166653a8cff744f74ec23) | デュアルデバイス構成 |

---

## USB Camera

### Logitech BRIO 4K セットアップ

```bash
# USB 接続後、認識確認
v4l2-ctl --list-devices
# Logitech BRIO が /dev/video0 等に表示

# 対応解像度確認
v4l2-ctl --list-formats-ext -d /dev/video0

# テスト撮影
python3 -c "
import cv2
cam = cv2.VideoCapture(0)
cam.set(cv2.CAP_PROP_FRAME_WIDTH, 3840)  # 4K
cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)
ret, frame = cam.read()
cam.release()
print(f'4K capture: {ret}, shape={frame.shape if ret else None}')
"
```

### 注意事項

- 4K (3840x2160) は USB 3.0 接続が必要
- 1080p で十分な場合は USB 2.0 でも動作
- 本プロジェクトでは **1080p (1920x1080)** を推奨（帯域とストレージのバランス）

### 参考リンク

| リンク | 内容 |
|--------|------|
| [Logitech BRIO 仕様](https://www.logitech.com/en-us/products/webcams/brio-4k-hdr-webcam.html) | 公式スペック |
| [v4l2-ctl マニュアル](https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/v4l2.html) | Linux カメラ制御 |

---

## CSI Camera

### Raspberry Pi NoIR Camera V2 セットアップ

```bash
# CSI ケーブル接続（15-22pin FPC、Pi 5 用）
# Pi 5 は 22pin コネクタ（Pi 4 以前の 15pin とは異なる）

# カメラ認識確認
libcamera-hello --list-cameras

# テスト撮影
libcamera-still -o /tmp/test_noir.jpg --width 3280 --height 2464

# Python (picamera2) での撮影
python3 -c "
from picamera2 import Picamera2
cam = Picamera2()
cam.start()
import time; time.sleep(2)
cam.capture_file('/tmp/test_picamera2.jpg')
cam.stop()
print('Captured with picamera2')
"
```

### 注意事項

- Pi 5 は **22pin FPC ケーブル**が必要（Pi 4 の 15pin とは非互換）
- NoIR = IR フィルターなし → 暗所/近赤外線撮影向き（通常照明下では色味が異なる）
- 通常照明下の検査には **USB カメラ (BRIO)** を推奨

### 参考リンク

| リンク | 内容 |
|--------|------|
| [Pi Camera Module 仕様](https://www.raspberrypi.com/documentation/accessories/camera.html) | 公式ドキュメント |
| [IMX219 データシート](https://www.opensourceinstruments.com/Electronics/Data/IMX219PQ.pdf) | センサー仕様 |
| [picamera2 マニュアル](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf) | Python API |

---

## Bambu Lab P2S

### ネットワーク接続 + Developer Mode

1. プリンターを有線 LAN に接続
2. **Developer Mode** を有効化（LAN モード + MQTT/FTP アクセス）

```
プリンター設定 → ネットワーク → LAN Only Mode → 有効
プリンター設定 → Developer Mode → 有効
```

3. MQTT でステータス取得（オプション）

```bash
# Python で MQTT 接続（Developer Mode 有効時）
pip install paho-mqtt
python3 -c "
import paho.mqtt.client as mqtt
import ssl, json

client = mqtt.Client()
client.tls_set(cert_reqs=ssl.CERT_NONE)
client.username_pw_set('bblp', '<ACCESS_CODE>')
client.connect('<PRINTER_IP>', 8883)
client.subscribe('device/<SERIAL>/report')
client.loop_start()
import time; time.sleep(5)
client.loop_stop()
"
```

### 注意事項

- Developer Mode は Bambu Lab の公式サポート対象外
- MQTT プロトコルは変更される可能性あり
- 本プロジェクトでは MQTT 連携はオプション（カメラ監視が主）

### 参考リンク

| リンク | 内容 |
|--------|------|
| [Bambu Lab P2S Wiki](https://wiki.bambulab.com/en/p2s) | 公式ドキュメント |
| [Developer Mode 有効化](https://wiki.bambulab.com/en/knowledge-sharing/enable-developer-mode) | MQTT/FTP アクセス設定 |
| [Third-party Integration](https://wiki.bambulab.com/en/software/third-party-integration) | API 連携ガイド |
| [OpenBambuAPI (非公式)](https://github.com/Doridian/OpenBambuAPI) | MQTT プロトコル解析 |
| [bambulabs-api (PyPI)](https://pypi.org/project/bambulabs-api/) | Python API ライブラリ |

---

## FS.com Switch

### S5860-24XMG 初期設定

```
# コンソール接続 (USB-C or RJ45 console)
# デフォルト: admin / admin

# VLAN 作成
Switch> enable
Switch# configure terminal
Switch(config)# vlan 10
Switch(config-vlan)# name IoT-Data
Switch(config-vlan)# exit
Switch(config)# vlan 20
Switch(config-vlan)# name ONTAP-Mgmt
Switch(config-vlan)# exit
Switch(config)# vlan 30
Switch(config-vlan)# name FPolicy
Switch(config-vlan)# exit

# ポート割り当て例
# Port 1-4: ONTAP (10GbE, VLAN 10+20+30 trunk)
Switch(config)# interface range te0/1-4
Switch(config-if-range)# switchport mode trunk
Switch(config-if-range)# switchport trunk allowed vlan 10,20,30
Switch(config-if-range)# exit

# Port 5-8: Raspberry Pi (VLAN 10 access)
Switch(config)# interface range te0/5-8
Switch(config-if-range)# switchport mode access
Switch(config-if-range)# switchport access vlan 10
Switch(config-if-range)# exit

# 設定保存
Switch(config)# end
Switch# write memory
```

### 参考リンク

| リンク | 内容 |
|--------|------|
| [S5860-24XMG 製品ページ](https://www.fs.com/products/189432.html) | スペック、データシート |
| [S5860 Quick Start (PDF)](https://www.manualslib.com/manual/2485038/Fs-S5860-Series.html) | 初期セットアップ |
| [FS VLAN 設定ガイド](https://www.fs.com/blog/fs-smb-switch-vlan-configuration-18075.html) | VLAN 設定詳細 |
| [S5860 User Guide](https://manuals.plus/_fs/s5860-series-switch-manual) | 全機能マニュアル |

---

## NetApp ONTAP

### 初期設定

→ 各ユースケースの `ontap-setup.sh` に詳細コマンドあり:
- [3d-print-quality/ontap-setup.sh](../../usecases/3d-print-quality/ontap-setup.sh)
- [ontap-telemetry-analytics/ontap-setup.sh](../../usecases/ontap-telemetry-analytics/ontap-setup.sh)

### FPolicy 外部サーバー設定

```bash
# 1. イベント定義
fpolicy policy event create -vserver svm-iot \
  -event-name img-create \
  -protocol nfs \
  -file-operations create \
  -filters first-write

# 2. 外部エンジン定義
fpolicy policy external-engine create -vserver svm-iot \
  -engine-name pi-engine \
  -primary-servers <PI_IP> \
  -port 9999 \
  -extern-engine-type asynchronous

# 3. ポリシー作成
fpolicy policy create -vserver svm-iot \
  -policy-name print-monitor \
  -events img-create \
  -engine pi-engine \
  -is-mandatory false

# 4. 有効化
fpolicy enable -vserver svm-iot -policy-name print-monitor
```

### 参考リンク

| リンク | 内容 |
|--------|------|
| [ONTAP REST API ドキュメント](https://docs.netapp.com/us-en/ontap-automation/rest/performance_metrics.html) | パフォーマンスメトリクス |
| [FPolicy 設定手順](https://docs.netapp.com/us-en/ontap/nas-audit/steps-setup-fpolicy-config-concept.html) | FPolicy 全体フロー |
| [FPolicy 外部エンジン作成](https://docs.netapp.com/us-en/ontap/nas-audit/create-fpolicy-external-engine-task.html) | 外部サーバー設定 |
| [FPolicy イベント設計](https://docs.netapp.com/us-en/ontap/nas-audit/plan-fpolicy-event-config-concept.html) | イベント設計ガイド |
| [FPolicy REST API (9.15.1)](https://docs.netapp.com/us-en/ontap-restapi-9151/manage_fpolicy_engine_configuration.html) | REST API リファレンス |
| [FPolicy ベストプラクティス](https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Cloud_Insights_Workload_Security__Fpolicy_Best_Practice_and_Recommendations) | パフォーマンス推奨 |
| [NFS Export Policy](https://docs.netapp.com/us-en/workload-fsx-ontap/manage-nfs-export-policy.html) | エクスポートポリシー管理 |

---

## AWS サービス接続ユースケースまとめ

### FSx for ONTAP S3 Access Points 経由

| AWS サービス | 接続方法 | 用途 | 参考リンク |
|-------------|---------|------|-----------|
| Amazon Athena | S3 AP → Athena テーブル | SQL 分析 | [チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html) |
| AWS Glue | S3 AP → Glue Crawler/ETL | データカタログ、ETL | [チュートリアル](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html) |
| Amazon Bedrock | S3 AP → Lambda → Bedrock | 画像AI、レポート生成 | [AWS ブログ](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/) |
| Amazon SageMaker | S3 AP → SageMaker | ML モデル学習・推論 | [FSx for ONTAP × AWS サービス](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html) |
| Amazon Quick Sight | Athena → Quick Sight | BI ダッシュボード | Athena 経由で接続 |

### Lambda 直接連携

| AWS サービス | 接続方法 | 用途 | 本プロジェクトでの使用 |
|-------------|---------|------|---------------------|
| Amazon Bedrock | Lambda → InvokeModel | 画像分析 (Claude Vision) | ✅ `usecases/3d-print-quality/` |
| Amazon SNS | Lambda → Publish | アラート通知 | ✅ 全ユースケース |
| Amazon DynamoDB | Lambda → PutItem | 結果保存 | 計画中 |
| Amazon CloudWatch | Lambda → PutMetricData | ビジネスメトリクス | ✅ `usecases/3d-print-quality/` |

### データパイプライン

| パターン | フロー | 用途 |
|---------|--------|------|
| リアルタイム分析 | ONTAP → FPolicy → Lambda → Bedrock → SNS | 即時異常検知 |
| バッチ分析 | ONTAP → SnapMirror → FSx for ONTAP → S3 AP → Athena | 日次/週次レポート |
| ML 学習 | FSx for ONTAP → S3 AP → SageMaker Training | モデル学習 |
| ETL | FSx for ONTAP → S3 AP → Glue → Parquet → Athena | データ変換 |
