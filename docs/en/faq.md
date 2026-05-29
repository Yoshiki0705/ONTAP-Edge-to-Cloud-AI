# FAQ

## Setup

**Q: Can I try this without ONTAP?**

A: The cloud side (Lambda + Bedrock) works without ONTAP. The edge side can also be validated with Pi + camera + direct S3 upload. ONTAP integration (FPolicy, SnapMirror, S3 AP) is a Phase 2+ option.

**Q: Does this work on devices other than Raspberry Pi?**

A: The camera capture script is OpenCV-based, so it works on any Linux + USB camera. Should work on NVIDIA Jetson, x86 Linux PC, WSL2 (untested).

**Q: Which AWS region does this work in?**

A: Requires a region where Bedrock Claude models are available. This project is validated in `ap-northeast-1` (Tokyo). Change the region parameter in the CloudFormation template for other regions.

## Technical

**Q: What's the AI accuracy?**

A: 9/9 correct in testing (public images + text-described scenarios). Real-environment accuracy (lighting, camera angle, filament color) is unverified. The prompt is conservatively designed to flag only clear defects.

**Q: How does two-stage analysis work?**

A: Stage 1: Claude Haiku (cheap, fast) determines "defect yes/no." Only if "yes," Stage 2: Claude Sonnet (high accuracy) performs detailed analysis. In environments with mostly normal images, this reduces cost by 85%.

**Q: Can this be used for inspections other than 3D printing?**

A: Yes. Change the Lambda prompt to apply to any image judgment — visual inspection (scratches, discoloration), inventory checks, safety equipment verification. Prompt change only, no model retraining needed.

**Q: What's the performance impact of FPolicy?**

A: FPolicy adds latency to target file operations (several ms to tens of ms in synchronous mode). For high-frequency write environments, use asynchronous mode or narrow notification targets via filtering.

**Q: What are FSxN S3 Access Points constraints?**

A: No conditional writes (no direct Iceberg/Delta Lake writes), no S3 event notifications (no Lambda triggers). See [use-case-research.md](use-case-research.md) section 5.1 for details.

## Cost

**Q: What's the monthly AWS cost?**

A: PoC scale (1 device, 60-second intervals): ~$40/month. Breakdown: Bedrock API ~$30, S3 ~$3, Kinesis ~$0 (ON_DEMAND, no data = no charge), Lambda ~$1, other ~$5.

**Q: How to reduce cost?**

A: (1) Extend capture interval to 120s (halves cost), (2) Skip when printer is idle, (3) Use Haiku only without Sonnet (lower accuracy).

## Troubleshooting

**Q: Lambda returns AccessDenied error**

A: The S3 bucket policy enforces KMS encryption. PutObject without `ServerSideEncryption: aws:kms` header is denied. Also, GetObject on non-existent objects requires ListBucket permission.

**Q: Bedrock returns ValidationException**

A: Model ID requires an inference profile. Use `jp.anthropic.claude-sonnet-4-5-20250929-v1:0` (JP profile) instead of `anthropic.claude-sonnet-4-5-20250929-v1:0`.

**Q: Tests are failing**

A: Verify `pip install pytest requests opencv-python-headless numpy`. Python 3.12+ required. Tests have no external dependencies (all mocked).
