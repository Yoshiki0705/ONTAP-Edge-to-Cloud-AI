"""Phase 1: Minimal capture script for SORACOM Flux.

This is the "small and working" version for Phase 1.
Just captures an image and POSTs it to SORACOM unified endpoint.
No buffer, no retry, no health monitoring — those come in Phase 2.

Usage:
    python simple_capture.py              # Single capture + upload
    python simple_capture.py --loop       # Continuous capture (60s interval)

Requirements:
    pip install opencv-python-headless requests
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import cv2
import requests

# Configuration — adjust these for your environment
DEVICE_ID = "rpi5-001"
CAMERA_DEVICE = 0  # /dev/video0
RESOLUTION = (1920, 1080)
JPEG_QUALITY = 80
INTERVAL_SECONDS = 60
SORACOM_ENDPOINT = "http://unified.soracom.io"


def capture_and_upload() -> bool:
    """Capture one image and upload to SORACOM."""
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
    jpeg_bytes = jpeg.tobytes()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"Captured: {len(jpeg_bytes)} bytes at {timestamp}")

    # Upload to SORACOM (Flux handles AI analysis + notification)
    try:
        resp = requests.post(
            SORACOM_ENDPOINT,
            data=jpeg_bytes,
            headers={
                "Content-Type": "image/jpeg",
                "X-Device-Id": DEVICE_ID,
                "X-Timestamp": timestamp,
            },
            timeout=30,
        )
        print(f"Upload: HTTP {resp.status_code}")
        return resp.status_code in (200, 201, 202)
    except requests.exceptions.RequestException as e:
        print(f"Upload failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Phase 1: Simple capture for SORACOM Flux")
    parser.add_argument("--loop", action="store_true", help="Continuous capture mode")
    args = parser.parse_args()

    if not args.loop:
        success = capture_and_upload()
        return 0 if success else 1

    print(f"Starting continuous capture: interval={INTERVAL_SECONDS}s, device={CAMERA_DEVICE}")
    while True:
        try:
            capture_and_upload()
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(INTERVAL_SECONDS)

    return 0


if __name__ == "__main__":
    sys.exit(main())
