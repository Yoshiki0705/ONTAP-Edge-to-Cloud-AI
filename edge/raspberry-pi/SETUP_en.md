🌐 [日本語](SETUP.md) | **English**

# Raspberry Pi Initial Setup Playbook

> What to do on the day your Pi arrives. Estimated time: about 1-2 hours.

## Prerequisites

- Raspberry Pi 5 (16GB)
- NVMe SSD (M.2 2280) + Geekworm X1004 expansion board
- USB camera (Logitech BRIO 4K)
- SORACOM IoT SIM (plan-D) + USB dongle or HAT
- Ethernet cable + 10GbE switch connection
- 27W USB-C power adapter
- microSD card (for initial OS flashing only)

## Step 1: OS Flashing (from macOS)

```bash
# Raspberry Pi Imager をインストール
brew install --cask raspberry-pi-imager

# または公式サイトからダウンロード
# https://www.raspberrypi.com/software/
```

1. Launch Raspberry Pi Imager
2. OS: Select **Raspberry Pi OS Lite (64-bit)** (no desktop needed)
3. Storage: Select the NVMe SSD (connected via USB through X1004)
4. Settings (gear icon):
   - Hostname: `rpi5-001`
   - Enable SSH: Password authentication → switch to key-based later
   - Username: `iot-operator`
   - Password: Set initial password (will be disabled later)
   - Wi-Fi: Do not configure (using wired LAN)
   - Locale: Asia/Tokyo, JP keyboard

## Step 2: First Boot + SSH Connection

```bash
# Pi に電源投入、有線LAN接続
# ルーターの DHCP リースまたは arp-scan で IP を確認
arp-scan --localnet | grep -i "raspberry\|dc:a6:32\|e4:5f:01\|2c:cf:67\|d8:3a:dd"

# SSH 接続
ssh iot-operator@<PI_IP>
```

## Step 3: Basic Configuration

```bash
# システム更新
sudo apt update && sudo apt upgrade -y

# 必要パッケージ
sudo apt install -y \
  python3-pip python3-venv \
  git ufw fail2ban \
  v4l-utils  # カメラ確認用

# NVMe SSD からのブート確認
lsblk
df -h /

# ホスト名確認
hostname
```

## Step 4: Security Hardening

```bash
# SSH 鍵認証に切り替え（macOS から）
ssh-copy-id -i ~/.ssh/id_ed25519.pub iot-operator@<PI_IP>

# Pi 側: パスワード認証を無効化
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# ファイアウォール設定
sudo ufw default deny incoming
sudo ufw default deny outgoing
sudo ufw allow out to any port 53        # DNS
sudo ufw allow out to any port 443       # HTTPS
sudo ufw allow out to any port 80        # HTTP (SORACOM)
sudo ufw allow out to any port 2049      # NFS
sudo ufw allow in from 192.168.0.0/16 to any port 22  # SSH (LAN only)
sudo ufw enable

# 不要サービス無効化
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon

# 自動セキュリティアップデート
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

## Step 5: Camera Verification

```bash
# USB カメラ接続確認
v4l2-ctl --list-devices

# テスト撮影
python3 -c "
import cv2
cam = cv2.VideoCapture(0)
cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
ret, frame = cam.read()
cam.release()
print(f'Capture: {ret}, Shape: {frame.shape if ret else None}')
if ret:
    cv2.imwrite('/tmp/test.jpg', frame)
    print('Saved: /tmp/test.jpg')
"

# 画像を手元に転送して確認
# (macOS から)
scp iot-operator@<PI_IP>:/tmp/test.jpg ~/Desktop/pi-test.jpg
```

## Step 6: SORACOM SIM Setup

```bash
# USB ドングル接続確認
lsusb | grep -i "huawei\|sierra\|quectel\|soracom"

# ネットワークインターフェース確認
ip link show

# SORACOM 接続テスト (接続後)
curl -s http://metadata.soracom.io/v1/subscriber | python3 -m json.tool

# Funnel テスト
curl -X POST http://funnel.soracom.io \
  -H "Content-Type: application/json" \
  -d '{"test": true, "device_id": "rpi5-001"}'
```

## Step 7: Application Deployment

```bash
# プロジェクトクローン
git clone https://github.com/Yoshiki0705/edge-to-cloud-ai.git /opt/edge-camera
cd /opt/edge-camera/edge/raspberry-pi/camera

# Python 仮想環境
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Phase 1: 最小スクリプトで動作確認
python simple_capture.py          # 1回撮影テスト
python simple_capture.py --loop   # 連続撮影テスト (Ctrl+C で停止)

# 動作確認OK後、systemd サービス化
sudo cp edge-camera.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable edge-camera
sudo systemctl start edge-camera
sudo journalctl -u edge-camera -f  # ログ確認
```

## Step 8: Camera Placement

### Placement Tips for 3D Printer Monitoring

```
推奨カメラ位置:
┌─────────────────────────┐
│     3D Printer          │
│  ┌───────────────────┐  │
│  │                   │  │
│  │   Print Bed       │  │
│  │                   │  │
│  └───────────────────┘  │
│                         │
└─────────────────────────┘
         ↑
    [Camera] ← 正面やや上方 (30-45°下向き)
    距離: 20-40cm
    固定: 3Dプリント製マウント or クランプ
```

**Placement checklist:**
- [ ] Entire print bed is within the camera's field of view
- [ ] Nozzle tip is visible (needed for stringing detection)
- [ ] Lighting is sufficient (printer's built-in LED + additional if needed)
- [ ] Cables do not interfere with prints or the print head
- [ ] Camera is firmly mounted and not affected by vibration
- [ ] USB cable length is adequate (consider an extension cable)

**Camera mount options:**
- Option A: 3D print a custom mount (design an STL file)
- Option B: Flexible arm + clamp (off-the-shelf)
- Option C: Mount directly to printer frame (adhesive tape/screws)

## Completion Checklist

- [ ] SSH key authentication works
- [ ] ufw is active with only required ports open
- [ ] Camera captures successfully (/tmp/test.jpg is valid)
- [ ] SORACOM SIM communicates (metadata.soracom.io responds)
- [ ] simple_capture.py runs successfully
- [ ] systemd service starts
- [ ] Logs are visible via journalctl
