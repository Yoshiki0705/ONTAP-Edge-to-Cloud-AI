🌐 [日本語](HARDWARE.md) | **English**

# Hardware Setup Reference

> Setup procedures and reference links for each vendor device

## Device List

| Device | Purpose | Setup Difficulty |
|--------|---------|-----------------|
| [Raspberry Pi 5](#raspberry-pi-5) | Edge compute | ★★☆ |
| [Geekworm X1004 + NVMe SSD](#nvme-ssd-geekworm-x1004) | Pi storage acceleration | ★★☆ |
| [USB Camera (Logitech BRIO 4K)](#usb-camera) | Image capture | ★☆☆ |
| [CSI Camera (NoIR V2)](#csi-camera) | Near-infrared imaging | ★★☆ |
| [Bambu Lab P2S](#bambu-lab-p2s) | 3D printer (monitoring target) | ★★☆ |
| [FS.com S5860-24XMG](#fscom-switch) | 10GbE L3 switch | ★★★ |
| [NetApp ONTAP](#netapp-ontap) | Data aggregation storage | ★★★ |

---

## Raspberry Pi 5

### Setup Procedure

→ See [SETUP.md](./SETUP.md) for detailed steps

### Reference Links

| Link | Contents |
|------|----------|
| [Raspberry Pi Official Documentation](https://www.raspberrypi.com/documentation/) | OS installation, general configuration |
| [Raspberry Pi Imager](https://www.raspberrypi.com/software/) | OS flashing tool |
| [Pi 5 NVMe Boot Guide](https://pidiylab.com/raspberry-pi-5-nvme-boot-guide/) | NVMe SSD boot configuration |
| [Pi 5 GPIO Pinout](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio) | GPIO pin layout |
| [picamera2 Documentation](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf) | CSI camera control |


---

## NVMe SSD (Geekworm X1004)

### Setup Procedure

1. Connect the X1004 board to the Pi 5's PCIe FPC connector
2. Install the NVMe SSD (M.2 2280) into the X1004
3. Change the EEPROM boot order to prioritize NVMe

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

### Notes

- X1004 uses the ASMedia ASM1182e PCIe switch → **limited to PCIe Gen 2 speed** (setting Gen 3 has no effect)
- Some Samsung SSDs have reported boot incompatibility → Kioxia recommended
- Bootloader version **2024-05-17 or later** is required

### Reference Links

| Link | Contents |
|------|----------|
| [Geekworm X1004 Wiki](https://wiki.geekworm.com/X1004) | Official setup guide |
| [Pi 5 NVMe Boot (pidiylab)](https://pidiylab.com/raspberry-pi-5-nvme-boot-guide/) | EEPROM configuration details |
| [X1004 + Coral TPU Coexistence](https://gist.github.com/TheNoobInventor/ef00bc82f3a166653a8cff744f74ec23) | Dual-device configuration |


---

## USB Camera

### Logitech BRIO 4K Setup

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

### Notes

- 4K (3840x2160) requires a USB 3.0 connection
- If 1080p is sufficient, USB 2.0 also works
- This project recommends **1080p (1920x1080)** (balancing bandwidth and storage)

### Reference Links

| Link | Contents |
|------|----------|
| [Logitech BRIO Specs](https://www.logitech.com/en-us/products/webcams/brio-4k-hdr-webcam.html) | Official specifications |
| [v4l2-ctl Manual](https://www.kernel.org/doc/html/latest/userspace-api/media/v4l/v4l2.html) | Linux camera control |


---

## CSI Camera

### Raspberry Pi NoIR Camera V2 Setup

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

### Notes

- Pi 5 requires a **22-pin FPC cable** (incompatible with the 15-pin cable used on Pi 4 and earlier)
- NoIR = No IR filter → designed for low-light/near-infrared imaging (colors appear different under normal lighting)
- For inspection under normal lighting, the **USB camera (BRIO)** is recommended

### Reference Links

| Link | Contents |
|------|----------|
| [Pi Camera Module Specs](https://www.raspberrypi.com/documentation/accessories/camera.html) | Official documentation |
| [IMX219 Datasheet](https://www.opensourceinstruments.com/Electronics/Data/IMX219PQ.pdf) | Sensor specifications |
| [picamera2 Manual](https://datasheets.raspberrypi.com/camera/picamera2-manual.pdf) | Python API |


---

## Bambu Lab P2S

### Network Connection + Developer Mode

1. Connect the printer to wired LAN
2. Enable **Developer Mode** (LAN mode + MQTT/FTP access)

```
プリンター設定 → ネットワーク → LAN Only Mode → 有効
プリンター設定 → Developer Mode → 有効
```

3. Retrieve status via MQTT (optional)

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

### Notes

- Developer Mode is not officially supported by Bambu Lab
- The MQTT protocol may change without notice
- In this project, MQTT integration is optional (camera monitoring is primary)

### Reference Links

| Link | Contents |
|------|----------|
| [Bambu Lab P2S Wiki](https://wiki.bambulab.com/en/p2s) | Official documentation |
| [Enable Developer Mode](https://wiki.bambulab.com/en/knowledge-sharing/enable-developer-mode) | MQTT/FTP access setup |
| [Third-party Integration](https://wiki.bambulab.com/en/software/third-party-integration) | API integration guide |
| [OpenBambuAPI (Unofficial)](https://github.com/Doridian/OpenBambuAPI) | MQTT protocol analysis |
| [bambulabs-api (PyPI)](https://pypi.org/project/bambulabs-api/) | Python API library |


---

## FS.com Switch

### S5860-24XMG Initial Configuration

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

### Reference Links

| Link | Contents |
|------|----------|
| [S5860-24XMG Product Page](https://www.fs.com/products/189432.html) | Specs, datasheet |
| [S5860 Quick Start (PDF)](https://www.manualslib.com/manual/2485038/Fs-S5860-Series.html) | Initial setup |
| [FS VLAN Configuration Guide](https://www.fs.com/blog/fs-smb-switch-vlan-configuration-18075.html) | VLAN configuration details |
| [S5860 User Guide](https://manuals.plus/_fs/s5860-series-switch-manual) | Full feature manual |


---

## NetApp ONTAP

### Initial Configuration (FAS2820, etc.)

→ Detailed commands are in each use case's `ontap-setup.sh`:
- [3d-print-quality/ontap-setup.sh](../../usecases/3d-print-quality/ontap-setup.sh)
- [ontap-telemetry-analytics/ontap-setup.sh](../../usecases/ontap-telemetry-analytics/ontap-setup.sh)

### FPolicy External Server Configuration

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

### Reference Links

| Link | Contents |
|------|----------|
| [ONTAP REST API Documentation](https://docs.netapp.com/us-en/ontap-automation/rest/performance_metrics.html) | Performance metrics |
| [FPolicy Configuration Steps](https://docs.netapp.com/us-en/ontap/nas-audit/steps-setup-fpolicy-config-concept.html) | FPolicy overall flow |
| [FPolicy External Engine Creation](https://docs.netapp.com/us-en/ontap/nas-audit/create-fpolicy-external-engine-task.html) | External server setup |
| [FPolicy Event Design](https://docs.netapp.com/us-en/ontap/nas-audit/plan-fpolicy-event-config-concept.html) | Event design guide |
| [FPolicy REST API (9.15.1)](https://docs.netapp.com/us-en/ontap-restapi-9151/manage_fpolicy_engine_configuration.html) | REST API reference |
| [FPolicy Best Practices](https://kb.netapp.com/on-prem/ontap/da/NAS/NAS-KBs/Cloud_Insights_Workload_Security__Fpolicy_Best_Practice_and_Recommendations) | Performance recommendations |
| [NFS Export Policy](https://docs.netapp.com/us-en/workload-fsx-ontap/manage-nfs-export-policy.html) | Export policy management |


---

## AWS Service Integration Use Case Summary

### Via FSx for ONTAP S3 Access Points

| AWS Service | Connection Method | Purpose | Reference Link |
|-------------|-------------------|---------|----------------|
| Amazon Athena | S3 AP → Athena table | SQL analytics | [Tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html) |
| AWS Glue | S3 AP → Glue Crawler/ETL | Data catalog, ETL | [Tutorial](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-transform-data-with-glue.html) |
| Amazon Bedrock | S3 AP → Lambda → Bedrock | Image AI, report generation | [AWS Blog](https://aws.amazon.com/blogs/storage/enabling-ai-powered-analytics-on-enterprise-file-data-configuring-s3-access-points-for-amazon-fsx-for-netapp-ontap-with-active-directory/) |
| Amazon SageMaker | S3 AP → SageMaker | ML model training & inference | [FSx for ONTAP × AWS Services](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/using-access-points-with-aws-services.html) |
| Amazon QuickSight | Athena → QuickSight | BI dashboards | Connected via Athena |

### Direct Lambda Integration

| AWS Service | Connection Method | Purpose | Used in This Project |
|-------------|-------------------|---------|---------------------|
| Amazon Bedrock | Lambda → InvokeModel | Image analysis (Claude Vision) | ✅ `usecases/3d-print-quality/` |
| Amazon SNS | Lambda → Publish | Alert notifications | ✅ All use cases |
| Amazon DynamoDB | Lambda → PutItem | Result storage | Planned |
| Amazon CloudWatch | Lambda → PutMetricData | Business metrics | ✅ `usecases/3d-print-quality/` |

### Data Pipelines

| Pattern | Flow | Purpose |
|---------|------|---------|
| Real-time analysis | ONTAP → FPolicy → Lambda → Bedrock → SNS | Immediate anomaly detection |
| Batch analysis | ONTAP → SnapMirror → FSx for ONTAP → S3 AP → Athena | Daily/weekly reports |
| ML training | FSx for ONTAP → S3 AP → SageMaker Training | Model training |
| ETL | FSx for ONTAP → S3 AP → Glue → Parquet → Athena | Data transformation |
