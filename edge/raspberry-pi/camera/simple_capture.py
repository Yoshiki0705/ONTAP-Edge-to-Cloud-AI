"""Phase 1: Capture images → save to ONTAP NFS → invoke Lambda for AI analysis.

Primary data flow:
  1. Capture image from camera
  2. Save to ONTAP NFS volume (FPolicy will also detect this for other integrations)
  3. Invoke Lambda directly for AI analysis (Pi knows what it wrote)
  4. Save analysis result to ONTAP NFS

Usage:
    python simple_capture.py              # Single capture + analyze
    python simple_capture.py --loop       # Continuous (60s interval)
    python simple_capture.py --no-analyze # Capture only, skip Lambda

Requirements:
    pip install opencv-python-headless boto3
    NFS mount configured: mount -t nfs <ONTAP_IP>:/vol_images /mnt/ontap/images
    AWS credentials configured (aws configure) for Lambda invocation
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import cv2

# Configuration — adjust via environment variables or edit defaults
DEVICE_ID = os.getenv("DEVICE_ID", "rpi5-001")
CAMERA_DEVICE = int(os.getenv("CAMERA_DEVICE", "0"))
RESOLUTION = (
    int(os.getenv("CAPTURE_RESOLUTION_WIDTH", "1920")),
    int(os.getenv("CAPTURE_RESOLUTION_HEIGHT", "1080")),
)
JPEG_QUALITY = int(os.getenv("CAPTURE_JPEG_QUALITY", "80"))
INTERVAL_SECONDS = int(os.getenv("CAPTURE_INTERVAL_SECONDS", "60"))
ONTAP_IMAGE_PATH = os.getenv("ONTAP_NFS_PATH", "/mnt/ontap/images")
ONTAP_RESULT_PATH = os.getenv("ONTAP_RESULT_PATH", "/mnt/ontap/results")
LAMBDA_FUNCTION_NAME = os.getenv("LAMBDA_FUNCTION_NAME", "edge-to-cloud-image-analyzer")
AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")
S3_BUCKET = os.getenv("S3_BUCKET", "")  # If set, also upload to S3 for Athena


def capture_image() -> tuple[bytes, str]:
    """Capture one image from camera. Returns (jpeg_bytes, timestamp)."""
    cam = cv2.VideoCapture(CAMERA_DEVICE)
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, RESOLUTION[0])
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, RESOLUTION[1])
    ret, frame = cam.read()
    cam.release()

    if not ret:
        raise RuntimeError("Failed to capture image from camera")

    _, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return jpeg.tobytes(), timestamp


def save_to_ontap(image_bytes: bytes, timestamp: str) -> Path:
    """Save image to ONTAP NFS mount. Returns the saved file path."""
    date_dir = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    output_dir = Path(ONTAP_IMAGE_PATH) / date_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{timestamp}_{DEVICE_ID}.jpg"
    output_path = output_dir / filename
    output_path.write_bytes(image_bytes)
    return output_path


def invoke_analysis_lambda(image_path: Path, image_bytes: bytes) -> dict | None:
    """Invoke the image analysis Lambda function.

    Passes the ONTAP file path (for reference) and uploads image to S3
    for Lambda to read (Lambda can't access on-prem NFS directly).
    """
    lambda_client = boto3.client("lambda", region_name=AWS_REGION)

    # Upload image to S3 for Lambda to access
    s3_key = f"raw/image_capture/{image_path.relative_to(Path(ONTAP_IMAGE_PATH))}"

    if S3_BUCKET:
        s3_client = boto3.client("s3", region_name=AWS_REGION)
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=image_bytes,
            ContentType="image/jpeg",
            ServerSideEncryption="aws:kms",
        )
    else:
        # If no S3 bucket configured, encode image in Lambda payload (limited to 6MB)
        import base64
        pass  # Will use S3 bucket in production

    # Invoke Lambda
    payload = {
        "bucket": S3_BUCKET,
        "key": s3_key,
        "ontap_path": str(image_path),
        "device_id": DEVICE_ID,
    }

    try:
        response = lambda_client.invoke(
            FunctionName=LAMBDA_FUNCTION_NAME,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )
        result = json.loads(response["Payload"].read())
        return result
    except Exception as e:
        print(f"Lambda invocation failed: {e}")
        return None


def save_result_to_ontap(result: dict, timestamp: str) -> None:
    """Save analysis result to ONTAP NFS mount."""
    date_dir = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    output_dir = Path(ONTAP_RESULT_PATH) / date_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{timestamp}_{DEVICE_ID}_result.json"
    output_path = output_dir / filename
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def capture_and_analyze(skip_analyze: bool = False) -> bool:
    """Full pipeline: capture → save to ONTAP → analyze → save result."""
    # 1. Capture
    image_bytes, timestamp = capture_image()
    print(f"[{timestamp}] Captured: {len(image_bytes)} bytes")

    # 2. Save to ONTAP NFS
    image_path = save_to_ontap(image_bytes, timestamp)
    print(f"[{timestamp}] Saved to ONTAP: {image_path}")

    if skip_analyze:
        return True

    # 3. Invoke Lambda for AI analysis
    if not S3_BUCKET:
        print(f"[{timestamp}] Skipping analysis: S3_BUCKET not configured")
        return True

    result = invoke_analysis_lambda(image_path, image_bytes)
    if result is None:
        print(f"[{timestamp}] Analysis failed")
        return False

    # 4. Save result to ONTAP
    body = result.get("body", result)
    save_result_to_ontap(body, timestamp)

    status = body.get("status", "unknown")
    alert = body.get("alert_sent", False)
    print(f"[{timestamp}] Analysis: status={status}, alert_sent={alert}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Capture images → ONTAP NFS → Lambda AI analysis"
    )
    parser.add_argument("--loop", action="store_true", help="Continuous capture mode")
    parser.add_argument("--no-analyze", action="store_true", help="Skip Lambda analysis")
    args = parser.parse_args()

    # Verify ONTAP NFS mount
    if not Path(ONTAP_IMAGE_PATH).exists():
        print(f"ERROR: ONTAP mount not found: {ONTAP_IMAGE_PATH}")
        print(f"Mount first: sudo mount -t nfs <ONTAP_IP>:/vol_images {ONTAP_IMAGE_PATH}")
        return 1

    if not args.loop:
        success = capture_and_analyze(skip_analyze=args.no_analyze)
        return 0 if success else 1

    print(f"Starting continuous capture: interval={INTERVAL_SECONDS}s")
    print(f"  Image output: {ONTAP_IMAGE_PATH}")
    print(f"  Result output: {ONTAP_RESULT_PATH}")
    print(f"  Lambda: {LAMBDA_FUNCTION_NAME} ({'enabled' if S3_BUCKET else 'disabled (no S3_BUCKET)'})")

    while True:
        try:
            capture_and_analyze(skip_analyze=args.no_analyze)
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(INTERVAL_SECONDS)

    return 0


if __name__ == "__main__":
    sys.exit(main())
