> 🌐 Language: [日本語](../ja/verification-status.md) | **English**

# Verification status

> **Last updated**: 2026-08-19

This records how far each piece of code in this repository has actually been run, and what
evidence stands behind each number. "The tests pass" is not the same as "it works in
production". Describing a stage that was never run as verified hides the part of a PoC that
breaks first.

## Conclusion

**The only thing measured on real AWS is the two-stage Amazon Bedrock analysis.** No path
involving an edge device or FSx for ONTAP has been run. The SAM templates pass cfn-lint and
the unit tests, but there is no record of a stack ever having been created.

## Why two separate axes

"How far did the code run" and "what backs this number" are different questions. Merged
into one scale, a passing unit test can be cited as grounds that something works in
production, and a figure calculated from list prices can be cited as a measurement. The
axes are kept apart here, and each reuses vocabulary that is already published elsewhere.
No new vocabulary is introduced.

## How far the code has run

### Tier definitions

Aligned with the real-hardware tiers in
[FSx for ONTAP S3 Access Points Serverless Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns).
That repository's `DemoMode only` is portal-specific and is replaced here by `local only`,
and its `real hardware, read path` becomes `real hardware, single stage` because the
distinction here is the scope of the stage rather than read versus write.

| Tier | Meaning | What a reader may expect |
|---|---|---|
| Real hardware, end-to-end | Every stage of the path ran on real AWS and real devices | It works in that configuration |
| Real hardware, single stage | That stage alone ran on real AWS; the stages around it were not connected | The behaviour of that stage. Not grounds that the path works |
| Unit tests only | Unit tests pass. Never executed on AWS | That the shape of the code is not broken |
| Local only | Run locally, for example under Docker. Never executed on AWS | The shape of the path. Differences against managed services are unconfirmed |
| Not run | Not executed | Nothing |

### Status per stage

| Stage of the path | Tier | Basis |
|---|---|---|
| Camera → local storage (NFS) | Not run | The edge devices have not arrived |
| Local storage → FSx for ONTAP sync | Not run | No real ONTAP environment |
| FSx for ONTAP → S3 access point | Not run | Same |
| S3 access point → AWS Lambda (screening) | Unit tests only | [`tests/`](../../tests/) |
| Amazon Bedrock two-stage analysis | **Real hardware, single stage** | [`tests/sample_images/README.md`](../../tests/sample_images/README.md) |
| Storing verdicts and alerting (Amazon S3 / Amazon SNS) | Unit tests only | [`tests/`](../../tests/) |
| Recording human feedback | Unit tests only | [`tests/`](../../tests/) |
| Sensor → AWS IoT Core → AWS Lambda | Unit tests only | [`tests/`](../../tests/) |
| SORACOM → Kinesis → Firehose → Amazon S3 (cellular path) | Not run | An optional path. The IAM role is not created unless `SoracomOperatorId` is supplied. Templates only |
| AWS Glue / Amazon Athena | Not run | Templates only |
| Kafka / ClickHouse | Local only | [`local-demo/`](../../local-demo/) |
| ONTAP telemetry collection (REST API polling) | Not run | No real ONTAP environment |
| Deploying the SAM templates | Not run | cfn-lint passes. No record of a stack being created |
| Stack teardown ([`scripts/teardown.sh`](../../scripts/teardown.sh)) | Not run | The order is derived from the templates' `Fn::ImportValue`, and the argument handling is exercised with a shimmed `aws`. The `delete-stack` and `wait` calls have no execution record |

Nothing is at "real hardware, end-to-end" yet.

## What backs each number

### Tier definitions

The four tiers from
[the FSx for ONTAP Adoption Playbook evidence policy](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/evidence-policy.md)
are used unchanged. That document is authoritative for the definitions and for the
promotion and demotion rules; they are not copied here. The one point worth restating is
that `documented` means "a primary source states it", not "it was measured". The only tier
that claims a measurement is `verified`.

### Basis per claim

| Claim | Tier | Basis and the conditions that must accompany it |
|---|---|---|
| 5/5 on text-described scenarios | `verified` | 2026-05-29 / ap-northeast-1 / `jp.anthropic.claude-sonnet-4-5-20250929-v1:0`. **Judgements on written descriptions of symptoms, not on images.** Not a measure of visual accuracy |
| 4/4 on real images | `verified` | Same, plus screening with `jp.anthropic.claude-haiku-4-5-20251001-v1:0`. Four images published by the Bambu Lab Wiki and Prusa Help |
| Synthetic images identified as not photographic | `verified` | Same. A separate round against images generated with OpenCV |
| Haiku mean 1,417 ms / Sonnet mean 7,186 ms | `verified` | n=4, sequential, timed on the client. Not from an AWS Lambda function inside a VPC |
| The PoC FSx for ONTAP configuration at $500.61/month | `documented` | Retrieved 2026-08-19 from the AWS Price List Query API, ap-northeast-1, unit price effectiveDate 2026-07-01. 1024 GiB × $0.300/GB-month + 128 MBps × $1.511/MBps-month. Storage and throughput only; backups and the rest are not included (see the [cost model](cost-model.md)) |
| $0.005–0.011 per image | — | **Withdrawn.** Hand-calculated from list prices, and that run recorded no token counts. Sitting in a table of measured results, it read as measured |
| $259/month falling to $40/month with two stages | — | **Withdrawn.** Under the same assumptions the formula in `tests/sample_images/README.md` gives $78/month, so the repository held three answers for one assumption. No rate's source can be reproduced |
| Token counts per image | — | Not recorded yet. `handler.py` now captures `usage` and emits `InputTokens` / `OutputTokens`, but the stack has never been deployed so there is no measurement |
| Anomalies detected within 60 seconds | `hypothesis` | A design target. Not measured |
| S3 access points require ONTAP 9.17.1 or later | `documented` | AWS documentation. [S3 AP compatibility and constraints](s3ap-compatibility-matrix.md) |
| S3 access points do not support event notifications | `documented` | Same. Covered instead by FPolicy, an explicit call, or polling |
| FlexCache write-back needs 9.15.1 or later, and is not recommended for production | `documented` | NetApp guidance and FAQ. [Greengrass and FlexCache integration](iot-greengrass-flexcache-integration.md) |
| Accuracy in a real installation | — | Not claimed. The effect of lighting, camera angle and filament colour is unconfirmed |

## What has to accompany a published number

The required fields are defined in
[the evidence policy's section on publishing numbers](https://github.com/Yoshiki0705/FSx-for-ONTAP-Adoption-Playbook/blob/main/docs/en/evidence-policy.md).
Applied to what this repository measures, they come out as: measurement date, Region, model
ID or inference profile, the AWS Lambda memory setting and whether it sits inside a VPC,
image size, iteration count, concurrency, and **where the timing was taken** — on the
client or reported by the service.

A number missing those cannot be reproduced, so it is useful for neither comparison nor
estimation. That is why the table above spells out the `jp.` prefix: a different prefix is
a different inference profile, with a different path and different charges.

## What has not been measured

Left empty rather than filled in. A blank cannot be told apart from a measurement that was
attempted and produced nothing.

| Item | Reason |
|---|---|
| Throughput and latency through an S3 access point | No real ONTAP environment. If measured, reuse the harness in the sibling repository below |
| Actual charges | No record of a deployed stack. Only estimates from published prices exist |
| End-to-end latency from edge to cloud | The edge devices have not arrived |
| Concurrent operation of several devices, and scale-out | Same |
| Accuracy in a real installation | Same. The published images were captured under different conditions |
| Accuracy of visual-inspection | Not verified. The accuracy measured for 3d-print-quality covers a different subject and different defect types, so it does not carry over |
| Bedrock latency as seen from an AWS Lambda function inside a VPC | The recorded measurement was taken on the client. A different path |
| The ONTAP version | Cannot be obtained without a real environment. The `documented` rows above are statements from official documentation, not values confirmed here |

## Conditions for citing a sibling repository's numbers

A number that does not carry its environment is not copied across. When it is cited, the
source repository and the environment are carried with it.

- **S3 access point operation latency** has been measured in
  [s3-burst-on-ontap-files](https://github.com/Yoshiki0705/s3-burst-on-ontap-files). The
  conditions are 64 B objects, concurrency 1, SINGLE_AZ_1 / 128 MBps, and **from outside
  AWS over the internet**. They do not overlap the path this repository assumes, where an
  AWS Lambda function inside a VPC reads through an S3 access point. Those figures cannot
  be used as design grounds as they stand.
- **ONTAP REST API pitfalls** — HTTP 202 with job polling, error codes, the key format in
  EMS payloads — are recorded against real hardware in
  [fsxn-observability-integrations](https://github.com/Yoshiki0705/fsxn-observability-integrations).
  Consult it when implementing ONTAP telemetry collection rather than repeating the
  investigation.
- That repository contains **no** implementation that collects ONTAP performance counters;
  metric collection is delegated to NetApp Harvest. It therefore does not duplicate the
  REST API polling here.

## Corrections to the record

Discrepancies found by checking the claims against the evidence.

- **"9/9 correct" was the sum of two different tests.** Five text-described scenarios plus
  four real images. The former involved no image at all, so the combined figure cannot be
  cited as visual accuracy. The table above separates them.
- **"AI accuracy is from synthetic tests only" was wrong.** The four images are photographs
  published in vendor documentation. The synthetic images, generated with OpenCV, were a
  separate round with a different result: they were correctly identified as not
  photographic.
- **No script in the repository reproduces the recorded run.**
  `edge/raspberry-pi/camera/test_prompt.py` is single-stage and its model ID carries no
  `jp.` prefix. The record is two-stage and prefixed. Reproducing it needs a path that
  invokes both stages.
- **The cost figures are not measurements.** They sat in the same table as the measured
  latencies while having a different origin. The table above separates the tiers.

## Promoting and demoting a tier

Demotion is always acceptable. Showing honestly that the evidence was lost is safer for a
reader than leaving a stale `verified` in place. Evidence is required only when promoting.

| Transition | What to attach |
|---|---|
| Not run → unit tests only | The tests |
| Unit tests only → real hardware, single stage | The environment it ran in (Region, date, target resources) and the steps to reproduce |
| Real hardware, single stage → real hardware, end-to-end | A record of every stage of the path being run |
| `hypothesis` / `documented` → `verified` | A measurement carrying the required metadata above |

## Related documents

- [S3 AP compatibility and constraints](s3ap-compatibility-matrix.md) — the evidence tier per constraint
- [FAQ](faq.md) — the places that touch on unverified items
- [Deployment guide](deployment-guide.md) — how to run it, not the result of a run
- [`tests/sample_images/README.md`](../../tests/sample_images/README.md) — the raw record of the Bedrock measurement
