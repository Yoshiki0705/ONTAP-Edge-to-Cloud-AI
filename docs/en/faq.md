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

A: 4/4 on four photographs from vendor documentation and 5/5 on five written descriptions of symptoms. They measure different things and are not added together ([verification status](verification-status.md)). Real-environment accuracy (lighting, camera angle, filament color) is unverified. The prompt is conservatively designed to flag only clear defects.

**Q: How does two-stage analysis work?**

A: Stage 1 has Claude Haiku (cheap, fast) decide "defect or not". Only on "defect" does Stage 2
run Claude Sonnet (high accuracy) for detailed analysis. Where most images are normal that
saves model calls, and how much it saves is decided by the anomaly rate. The higher that rate, the more often stage two
runs and the smaller the saving; at a 100% anomaly rate two stages cost more than one, because
the screening call becomes pure overhead. The "roughly 85% less" that used to be quoted here
came from unit prices with a different source and is withdrawn. The formula is in the
[cost model](cost-model.md).

**Q: Can this be used for inspections other than 3D printing?**

A: Yes. Change the Lambda prompt to apply to any image judgment — visual inspection (scratches, discoloration), inventory checks, safety equipment verification. Prompt change only, no model retraining needed.

**Q: What's the performance impact of FPolicy?**

A: FPolicy adds latency to target file operations (several ms to tens of ms in synchronous mode). For high-frequency write environments, use asynchronous mode or narrow notification targets via filtering.

**Q: What are FSx for ONTAP S3 Access Points constraints?**

A: The main ones are no conditional writes (so no direct Iceberg or Delta Lake writes), no S3
event notifications (so no object-created Lambda trigger), ListObjectsV2 slower than native S3,
and ONTAP 9.17.1 or later. The full list, with the basis for each claim, is collected in
[S3 AP compatibility and constraints](./s3ap-compatibility-matrix.md).

## Cost

**Q: What's the monthly AWS cost?**

A: No monthly total here. The "~$40/month" that used to be quoted was one of three answers this repository gave for the same assumptions, and it is withdrawn. The only figure whose magnitude will hurt you is FSx for ONTAP: $500.61/month for the PoC configuration, calculated from ap-northeast-1 rates retrieved 2026-08-19. Everything else is single or double-digit dollars at PoC scale. The formulas and the pricing date are in the [cost model](cost-model.md). Kinesis in ON_DEMAND mode is not charged while idle.

**Q: How to reduce cost?**

A: (1) Lengthen the capture interval (acts directly on the model call count; it does not halve the total, only the per-call part), (2) skip while the printer is idle, (3) use Haiku only without Sonnet (lower accuracy), (4) delete FSx for ONTAP after the PoC if it is in scope — that one dominates. The [cost model](cost-model.md) has a flowchart of where pushing helps.

## Troubleshooting

**Q: Lambda returns AccessDenied error**

A: The S3 bucket policy enforces KMS encryption. PutObject without `ServerSideEncryption: aws:kms` header is denied. Also, GetObject on non-existent objects requires ListBucket permission.

**Q: Bedrock returns ValidationException**

A: Model ID requires an inference profile. Use `jp.anthropic.claude-sonnet-4-5-20250929-v1:0` (JP profile) instead of `anthropic.claude-sonnet-4-5-20250929-v1:0`.

**Q: Tests are failing**

A: Verify `pip install pytest requests opencv-python-headless numpy`. Python 3.12+ required. Tests have no external dependencies (all mocked).
