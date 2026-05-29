"""Phase 1: Minimal capture script — write to ONTAP NFS.

This is the "small and working" version for Phase 1.
Captures an image and writes it to an NFS-mounted ONTAP volume.
FPolicy on ONTAP then triggers Lambda for AI analysis.

Usage:
    python simple_capture.py              # Single capture
    python simple_capture.py --loop       # Continuous capture (60s interval)

Requirements:
    pip install opencv-python-headless
    NFS mount configured: mount -t nfs <ONTAP_IP>:/vol_images /mnt/ontap
"""

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2

# Configuration — adjust these for your environment
DEVICE_ID = "rpi5-001"
CAMERA_DEVICE = 0  # /dev/video0
RESOLUTION = (1920, 1080)
JPEG_QUALITY = 80
INTERVAL_SECONDS = 60
ONTAP_MOUNT_PATH = "/mnt/ontap/images"  # NFS mount point for ONTAP volume


def capture_and_save() -> bool:
    """Capture one image and save to ONTAP NFS mount."""
    # Capture
    cam = cv2.VideoCapture(CAMERA_DEVICE)
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
    ret, frame = cam.read()
    cam.release()

    if not ret:
        print("ERROR: Failed to capture image")
        return False

    # Encode to JPEG
    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])

    # Save to ONTAP NFS mount (FPolicy will detect and trigger Lambda)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(ONTAP_MOUNT_PATH) / datetime.now(timezone.utc).strftime("%Y/%m/%d")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{timestamp}_{DEVICE_ID}.jpg"

    output_path.write_bytes(jpeg.tobytes())
    print(f"Saved: {output_path} ({len(jpeg.tobytes())} bytes)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Phase 1: Capture images to ONTAP NFS")
    parser.add_argument("--loop", action="store_true", help="Continuous capture mode")
    args = parser.parse_args()

    if not Path(ONTAP_MOUNT_PATH).exists():
        print(f"ERROR: ONTAP mount path not found: {ONTAP_MOUNT_PATH}")
        print(f"Mount ONTAP NFS volume first: sudo mount -t nfs <ONTAP_IP>:/vol_images {ONTAP_MOUNT_PATH}")
        return 1

    if not args.loop:
        success = capture_and_save()
        return 0 if success else 1

    print(f"Starting continuous capture: interval={INTERVAL_SECONDS}s, output={ONTAP_MOUNT_PATH}")
    while True:
        try:
            capture_and_save()
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(INTERVAL_SECONDS)

    return 0


if __name__ == "__main__":
    sys.exit(main())
