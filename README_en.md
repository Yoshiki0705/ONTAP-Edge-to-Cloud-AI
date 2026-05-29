🌐 [日本語](README.md) | **English**

# ONTAP Edge-to-Cloud AI

[![Tests](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai/actions/workflows/test.yml/badge.svg)](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Yoshiki0705/ontap-edge-to-cloud-ai/badge)](https://scorecard.dev/viewer/?uri=github.com/Yoshiki0705/ontap-edge-to-cloud-ai)

**TL;DR**: Building a system to connect underutilized inspection images and sensor data on NAS to AI analytics — without copying data. Raspberry Pi collects data, writes to ONTAP, and connects directly to Bedrock/Athena via S3 Access Points.

> **Disclaimer**: This is a personal technical exploration project and does not represent official views or recommendations of any organization. It does not recommend purchasing any specific product.

## The Problem

Factories and sites accumulate inspection images, equipment logs, and sensor data on NAS storage daily. In most cases, this data is "just stored" — not analyzed or leveraged by AI.

**Common situations:**
- Terabytes of inspection images on NAS, used only for manual visual review
- Equipment logs are saved but failure precursors go undetected
- Want to analyze data with cloud AI services, but full copy to cloud is impractical
- Want to integrate edge device (camera, sensor) data with existing storage infrastructure

## This Project's Approach

Use existing ONTAP NAS as the data aggregation point. Edge devices write collected data via NFS/SMB, then connect to cloud AI/analytics services through ONTAP capabilities.

**Key points:**
- No full data copy to S3 (direct access via ONTAP S3 Access Points)
- Existing file workflows (NFS/SMB) remain unchanged
- File arrival triggers automated analysis (FPolicy)
- Edge → cloud sync uses incremental transfer (SnapMirror)

### Target Audience

- **Existing ONTAP users**: Want to leverage NAS data with AI/analytics
- **IoT/Edge developers**: Want to integrate edge device data with existing storage
- **AWS users**: Want to use Athena/Bedrock/SageMaker with non-S3 storage sources

### What If I Don't Have ONTAP?

This architecture assumes ONTAP, but the core pattern (edge collection → aggregation → AI analysis) works with other storage:

| Storage | Data Flow | Characteristics | Constraints |
|---------|-----------|----------------|-------------|
| **S3 direct** | Edge → S3 → Athena/Bedrock | Simplest. Easy setup. Native AWS integration. S3 Object Lock for tamper protection. CloudFront for edge cache delivery | No NFS/SMB access. Integrating with existing file workflows requires extra work. Event-driven via S3 Event Notifications |
| **EFS** | Edge → NFS → EFS → Lambda/Bedrock | NFS mountable. Good affinity with Linux devices. Auto-scaling. AWS Backup for protection | No SMB. No direct S3 API access. Event-driven requires Lambda + CloudWatch. Cross-region via EFS Replication |
| **ONTAP** | Edge → NFS/SMB → ONTAP → S3 AP → AWS AI | NFS + SMB + S3 on same data. FPolicy file-arrival triggers. SnapMirror incremental sync. FlexCache for low-latency remote site delivery. ARP/AI ransomware anomaly detection with automatic Snapshot protection | Requires ONTAP environment. S3 AP has no conditional writes. Needs ONTAP operational knowledge |

**Which to choose:**
- No existing data / greenfield → **S3 direct** is simplest
- Linux devices writing NFS / VPC-contained → **EFS**
- Already have ONTAP/NAS with data / need NFS+SMB / want to avoid data copying → **ONTAP**

## Architecture

```
[Edge Devices]                   [ONTAP (Data Aggregation)]       [AI / Analytics]
                                 FAS/AFF | ONTAP Select | FSxN
┌────────────────┐               ┌────────────────────┐          ┌──────────────────┐
│ Raspberry Pi 5 │──NFS─────────→│                    │          │ AWS              │
│  Camera        │               │  Inspection images  │─S3 AP──→│  Bedrock (GenAI) │
│  Sensors       │               │  Sensor CSV         │          │  SageMaker (ML)  │
├────────────────┤               │  Equipment logs     │─SnapMirror→ FSxN ─S3 AP──→│
│ 3D Printer     │──SMB─────────→│  3D models          │          │  Athena (SQL)    │
├────────────────┤               │                    │          │  Glue (ETL)      │
│ USB Camera     │──NFS─────────→│  FPolicy (events)   │          │  QuickSight (BI) │
└────────────────┘               │  REST API (telemetry)│          ├──────────────────┤
                                 │  ARP/AI (protection) │          │ Local AI         │
[Connectivity Options]           │  Snapshot (preserve) │          │  GPU Server      │
├─ Wired LAN (10GbE)            └────────────────────┘          │  Pi Edge Infer.  │
├─ Wi-Fi                                                         └──────────────────┘
├─ SORACOM Cellular (option)
└─ SORACOM S+ Camera (option)
```

### Edge Devices (Options)

| Device | Connection | Purpose |
|--------|-----------|---------|
| Raspberry Pi 5 | Wired LAN (NFS) | Camera capture, sensor collection, edge inference |
| USB Camera (4K) | Via Pi | Visual inspection, quality monitoring |
| CSI Camera (NoIR V2) | Via Pi | Low-light, near-infrared |
| 3D Printer | Wired LAN (SMB) | Print data storage |
| SORACOM S+ Camera | Cellular (option) | Sites without wired LAN |
| SORACOM Air + Pi | Cellular (option) | Connectivity for sites without LAN |
| Industrial Sensors | Pi GPIO / I2C / SPI | Temperature, vibration, current |

### ONTAP Platforms (Options)

| Platform | Deployment | Characteristics |
|----------|-----------|----------------|
| FAS/AFF | On-premises | Hardware appliance |
| ONTAP Select | On-premises / VM | Software-defined. Runs on commodity servers or VMs |
| FSx for ONTAP | AWS Cloud | Fully managed. SnapMirror destination, S3 AP support |

## Motivation

As an SA/SE visiting customer sites, I repeatedly heard "we have data on NAS but can't leverage it." With the following technologies maturing in 2024-2025, a practical solution became feasible for the first time:

- **FSx for ONTAP S3 Access Points** (2025 GA): S3 API access without data copying
- **SORACOM Flux** (2024 GA): Low-code camera × AI pipeline
- **Claude Vision / Multimodal AI**: Industrial image judgment at practical accuracy with generic prompts

The first PoC is **3D print quality monitoring** (visually compelling, failures happen frequently for easy test data collection).

## Current Limitations

- **No hardware testing yet**: Edge devices (Raspberry Pi, camera) have not arrived. End-to-end hardware testing is pending. Cloud side (Lambda, Bedrock) is verified.
- **AI accuracy tested with synthetic data only**: Prompt testing used public and synthetic images (9/9 correct). Real-environment accuracy (lighting, camera angle, filament color) is unverified.
- **ONTAP integration is design-only**: FPolicy, SnapMirror, S3 AP integration code is implemented but untested against real ONTAP (mock tests only).
- **Single-device configuration**: Multi-device concurrent operation and scale-out are untested.

## What I've Learned So Far

- **Two-stage AI analysis cuts cost by 85%**: Analyzing all images with the high-accuracy model costs ~$259/month. Screening with Haiku and routing only suspected anomalies to Sonnet brings it to ~$40/month. This pattern applies to other AI pipelines.
- **Prompts alone achieve practical accuracy for industrial image judgment**: Without custom model training, Claude Vision prompts correctly identified 3D print defects in 9/9 test cases. Real-environment validation is pending.
- **FSxN S3 Access Points constraints**: No conditional writes, no event notifications. Direct Iceberg/Delta Lake writes aren't possible. FPolicy-based complementary design is needed.
- **ONTAP REST API works well for IoT telemetry collection**: Performance metrics, capacity, and health can be collected at 1-minute intervals. Polling-based but sufficient for PoC.

## Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| AWS Infrastructure (CFn) | ✅ Deployed | S3, Kinesis, Lambda, IAM, Glue, SNS |
| Lambda (Two-Stage AI) | ✅ Deployed | Haiku screening + Sonnet detail (85% cost reduction) |
| ONTAP Telemetry Collector | ✅ Implemented | REST API polling (mock E2E tested) |
| Edge Camera Code | ✅ Implemented | Awaiting Pi arrival |
| Design Documents | ✅ Complete | 8 documents, ja/en synced |
| Hardware Testing | 📋 Pending | After Pi + camera + ONTAP arrival |

## Quick Start

### Prerequisites

- AWS CLI v2 + credentials configured
- Python 3.12+
- Bedrock model access enabled
- ONTAP 9.13.1+ (FPolicy, REST API, S3 AP)

### Deploy

```bash
# AWS infrastructure
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides Environment=poc \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1

# Edge device → edge/raspberry-pi/SETUP.md
```

## Documentation

| Document | 日本語 | English |
|----------|--------|---------|
| Use Case Research | [docs/ja/use-case-research.md](docs/ja/use-case-research.md) | [docs/en/use-case-research.md](docs/en/use-case-research.md) |
| Data Schema Design | [docs/ja/data-schema-design.md](docs/ja/data-schema-design.md) | [docs/en/data-schema-design.md](docs/en/data-schema-design.md) |
| Security Design | [docs/ja/security-design.md](docs/ja/security-design.md) | [docs/en/security-design.md](docs/en/security-design.md) |
| Operations Design | [docs/ja/operations-design.md](docs/ja/operations-design.md) | [docs/en/operations-design.md](docs/en/operations-design.md) |
| FAQ | [docs/ja/faq.md](docs/ja/faq.md) | [docs/en/faq.md](docs/en/faq.md) |

## Related Projects

- [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) — FSx for ONTAP S3 AP × Lakehouse integrations

## License

MIT
