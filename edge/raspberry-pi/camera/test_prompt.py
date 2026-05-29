"""Bedrock Claude Vision prompt tester for 3D print quality analysis.

Tests the analysis prompt against sample images to validate accuracy
before deploying to production. Can use local images or URLs.

Usage:
    python test_prompt.py --image /path/to/image.jpg
    python test_prompt.py --url https://example.com/print-failure.jpg
    python test_prompt.py --test-all  # Run against all test images in tests/

Requirements:
    pip install boto3 requests
    AWS credentials configured (aws configure)
    Bedrock model access enabled for Claude
"""

import argparse
import base64
import json
import sys
import time
from pathlib import Path

import boto3
import requests

MODEL_ID = "anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = "ap-northeast-1"

ANALYSIS_PROMPT = """You are a 3D printing quality inspector. Analyze this image of a 3D print in progress or completed.

Check for the following defects:
1. **Stringing** - thin strings of filament between parts
2. **Layer delamination** - layers separating or not adhering properly
3. **Warping** - edges lifting from the print bed
4. **Under-extrusion** - gaps or thin spots in layers
5. **Over-extrusion** - blobs or excess material
6. **Nozzle clogging** - inconsistent extrusion patterns
7. **Layer shifting** - misaligned layers
8. **Spaghetti** - filament tangling, print completely failed

Respond in JSON format:
{
  "status": "normal" | "anomaly_detected",
  "confidence": 0.0-1.0,
  "anomalies": [
    {
      "type": "stringing|delamination|warping|under_extrusion|over_extrusion|nozzle_clog|layer_shift|spaghetti",
      "severity": "low|medium|high|critical",
      "location": "description of where in the image",
      "description": "brief description of the issue"
    }
  ],
  "recommendation": "action to take",
  "overall_quality_score": 0-100
}

If the print looks normal with no defects, return status "normal" with an empty anomalies array and quality score above 80.
Be conservative - only flag clear defects, not minor cosmetic variations."""


def analyze_image(image_bytes: bytes, model_id: str = MODEL_ID) -> dict:
    """Send image to Bedrock Claude Vision for analysis."""
    client = boto3.client("bedrock-runtime", region_name=REGION)

    image_base64 = base64.b64encode(image_bytes).decode("utf-8")

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": ANALYSIS_PROMPT,
                    },
                ],
            }
        ],
    }

    start_time = time.time()
    response = client.invoke_model(
        modelId=model_id,
        contentType="application/json",
        accept="application/json",
        body=json.dumps(request_body),
    )
    latency_ms = (time.time() - start_time) * 1000

    response_body = json.loads(response["body"].read())
    content_text = response_body["content"][0]["text"]

    # Parse JSON from response
    json_text = content_text
    if "```json" in json_text:
        json_text = json_text.split("```json")[1].split("```")[0]
    elif "```" in json_text:
        json_text = json_text.split("```")[1].split("```")[0]

    result = json.loads(json_text.strip())
    result["_latency_ms"] = round(latency_ms)
    result["_input_tokens"] = response_body.get("usage", {}).get("input_tokens", 0)
    result["_output_tokens"] = response_body.get("usage", {}).get("output_tokens", 0)

    return result


def load_image_from_url(url: str) -> bytes:
    """Download image from URL."""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.content


def load_image_from_file(path: str) -> bytes:
    """Load image from local file."""
    return Path(path).read_bytes()


def print_result(result: dict, source: str) -> None:
    """Pretty-print analysis result."""
    print(f"\n{'='*60}")
    print(f"Source: {source}")
    print(f"{'='*60}")
    print(f"Status: {result.get('status', 'unknown')}")
    print(f"Confidence: {result.get('confidence', 0):.0%}")
    print(f"Quality Score: {result.get('overall_quality_score', 'N/A')}/100")
    print(f"Latency: {result.get('_latency_ms', 0)}ms")
    print(f"Tokens: in={result.get('_input_tokens', 0)}, out={result.get('_output_tokens', 0)}")

    anomalies = result.get("anomalies", [])
    if anomalies:
        print(f"\nAnomalies ({len(anomalies)}):")
        for a in anomalies:
            print(f"  [{a.get('severity', '?')}] {a.get('type', '?')}: {a.get('description', '')}")
            print(f"         Location: {a.get('location', 'N/A')}")
    else:
        print("\nNo anomalies detected.")

    print(f"\nRecommendation: {result.get('recommendation', 'N/A')}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Test Bedrock prompt for 3D print analysis")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--image", help="Path to local image file")
    group.add_argument("--url", help="URL of image to analyze")
    group.add_argument("--test-all", action="store_true", help="Test all images in tests/ directory")
    parser.add_argument("--model", default=MODEL_ID, help="Bedrock model ID")

    args = parser.parse_args()

    if args.image:
        print(f"Loading image: {args.image}")
        image_bytes = load_image_from_file(args.image)
        result = analyze_image(image_bytes, args.model)
        print_result(result, args.image)

    elif args.url:
        print(f"Downloading image: {args.url}")
        image_bytes = load_image_from_url(args.url)
        result = analyze_image(image_bytes, args.model)
        print_result(result, args.url)

    elif args.test_all:
        test_dir = Path(__file__).parent.parent.parent.parent / "tests" / "sample_images"
        if not test_dir.exists():
            print(f"Test directory not found: {test_dir}")
            print("Create tests/sample_images/ and add .jpg files to test.")
            return 1

        images = list(test_dir.glob("*.jpg")) + list(test_dir.glob("*.png"))
        if not images:
            print(f"No images found in {test_dir}")
            return 1

        print(f"Testing {len(images)} images...")
        results = []
        for img_path in sorted(images):
            print(f"\nAnalyzing: {img_path.name}...")
            image_bytes = img_path.read_bytes()
            result = analyze_image(image_bytes, args.model)
            print_result(result, img_path.name)
            results.append({"file": img_path.name, **result})

        # Summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        for r in results:
            status_icon = "🔴" if r.get("status") == "anomaly_detected" else "🟢"
            print(f"  {status_icon} {r['file']}: {r.get('status')} "
                  f"(confidence={r.get('confidence', 0):.0%}, "
                  f"score={r.get('overall_quality_score', 'N/A')})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
