# Raspberry Pi 初回セットアップ Playbook

> Pi が届いた日にやること。所要時間: 約1-2時間。

## 前提

- Raspberry Pi 5 (16GB)
- NVMe SSD (M.2 2280) + Geekworm X1004 拡張ボード
- USB カメラ (Logitech BRIO 4K)
- SORACOM IoT SIM (plan-D) + USB ドングル or HAT
- 有線LAN ケーブル + 10GbE スイッチ接続
- 27W USB-C 電源アダプター
- microSD カード (OS書き込み用、初回のみ)

## Step 1: OS 書き込み (macOS から)

```bash
# Raspberry Pi Imager をインストール
brew install --cask raspberry-pi-imager

# または公式サイトからダウンロード
# https://www.raspberrypi.com/software/
```

1. Raspberry Pi Imager を起動
2. OS: **Raspberry Pi OS Lite (64-bit)** を選択（デスクトップ不要）
3. ストレージ: NVMe SSD を選択（X1004 経由で USB 接続）
4. 設定（歯車アイコン）:
   - ホスト名: `rpi5-001`
   - SSH 有効化: パスワード認証 → 後で鍵認証に変更
   - ユーザー名: `iot-operator`
   - パスワード: 初期パスワード設定（後で無効化）
   - Wi-Fi: 設定しない（有線LAN使用）
   - ロケール: Asia/Tokyo, JP keyboard

## Step 2: 初回起動 + SSH 接続

```bash
# Pi に電源投入、有線LAN接続
# ルーターの DHCP リースまたは arp-scan で IP を確認
arp-scan --localnet | grep -i "raspberry\|dc:a6:32\|e4:5f:01\|2c:cf:67\|d8:3a:dd"

# SSH 接続
ssh iot-operator@<PI_IP>
```

## Step 3: 基本設定

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

## Step 4: セキュリティハードニング

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

## Step 5: カメラ確認

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

## Step 6: SORACOM SIM セットアップ

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

## Step 7: アプリケーションデプロイ

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

## Step 8: カメラ設置

### 3Dプリンター監視の設置ポイント

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

**設置チェックリスト:**
- [ ] プリントベッド全体が画角に収まるか
- [ ] ノズル先端が見えるか（糸引き検出に必要）
- [ ] 照明が十分か（プリンター内蔵LED + 必要に応じて追加）
- [ ] ケーブルが印刷物やヘッドに干渉しないか
- [ ] 振動でカメラがブレないか（しっかり固定）
- [ ] USB ケーブル長は足りるか（延長ケーブル検討）

**カメラマウント案:**
- 案A: 3Dプリンターで自作マウントを印刷（STLファイルを設計）
- 案B: フレキシブルアーム + クランプ（市販品）
- 案C: プリンターフレームに直接固定（両面テープ/ネジ）

## 確認完了チェックリスト

- [ ] SSH 鍵認証で接続できる
- [ ] ufw が有効で必要ポートのみ開放
- [ ] カメラで撮影できる（/tmp/test.jpg が正常）
- [ ] SORACOM SIM で通信できる（metadata.soracom.io 応答あり）
- [ ] simple_capture.py が動作する
- [ ] systemd サービスが起動する
- [ ] ログが journalctl で確認できる
