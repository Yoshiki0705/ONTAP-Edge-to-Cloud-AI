🌐 [日本語](README.md) | **English**

# ONTAP Edge-to-Cloud AI

> NetApp ONTAP × IoT × AWS AI/Analytics — Reference architecture connecting ONTAP storage data to AWS AI/analytics services via edge devices (Raspberry Pi, SORACOM)

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Yoshiki0705/ontap-edge-to-cloud-ai/badge)](https://scorecard.dev/viewer/?uri=github.com/Yoshiki0705/ontap-edge-to-cloud-ai)

## Overview

Pipelines that collect and pre-process file data (inspection images, equipment logs, sensor CSVs) from ONTAP (on-premises FAS/AFF, ONTAP Select, or FSx for ONTAP) via IoT edge devices, then leverage AWS AI/analytics services. The first PoC implements **3D print quality monitoring**.

### Why ONTAP is Central

- **Leverage existing data assets**: Connect data accumulated on factory/site ONTAP NAS to AI/analytics without copying
- **FPolicy event-driven**: Trigger automated analysis pipelines on file arrival
- **SnapMirror sync**: Bandwidth-efficient edge → cloud (FSxN) data synchronization
- **S3 Access Points**: Direct S3 API access to FSxN data (Athena, Bedrock, SageMaker)
- **Multi-Protocol**: NFS (edge devices) + SMB (Windows equipment) + S3 (AWS services) on the same data

### Architecture (Two-Stage AI Analysis)

```
[Edge]                    [SORACOM]              [AWS Cloud]
Raspberry Pi 5            Flux / Funnel         ┌──────────────────────────────┐
┌──────────────┐          ┌─────────┐           │  S3 Data Lake                │
│ USB Camera   │──60s────→│ Cellular│──HTTPS──→ │    ↓                         │
│ (1080p JPEG) │          │ or WiFi │           │  Lambda (Two-Stage)          │
└──────────────┘          └─────────┘           │    ├─ Haiku: Screening       │
                                                │    └─ Sonnet: Detail(anomaly)│
[ONTAP Storage]                                 │    ↓                         │
┌──────────────┐                                │  SNS → Slack/Email alert     │
│ FAS/AFF      │──SnapMirror──→ FSx for ONTAP   │    ↓                         │
│ FPolicy      │                  ↓ S3 AP       │  Athena (SQL)                │
│ REST API     │                  Bedrock/SM    │  QuickSight (BI)             │
└──────────────┘                                └──────────────────────────────┘
```

### Cost Optimization

| Approach | Monthly Cost | Description |
|----------|-------------|-------------|
| Single model (Sonnet) | ~$259/month | Analyze all images with high-accuracy model |
| **Two-stage (adopted)** | **~$40/month** | Haiku screening, Sonnet only for suspected anomalies |

### Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| AWS Infrastructure (CFn) | ✅ Deployed | S3, Kinesis, Lambda, IAM, Glue, SNS |
| Lambda (Two-Stage) | ✅ Deployed | Haiku + Sonnet, prompt accuracy 100% |
| ONTAP Telemetry Collector | ✅ Implemented | REST API polling (mock E2E tested) |
| CloudWatch Monitoring | ✅ Configured | Dashboard + 3 alarms + budget |
| Edge Code | ✅ Implemented | Awaiting Pi arrival for testing |
| SORACOM Integration | 📋 Pending | Configure after SIM arrival |
| Hardware Testing | 📋 Pending | After Pi + camera arrival |

### Related Projects

- [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) — FSx for ONTAP S3 Access Points × Lakehouse integrations (parent project)

## Quick Start

### Prerequisites

- AWS CLI v2 + credentials configured
- Python 3.12+
- Bedrock model access enabled (Claude Haiku 4.5 / Sonnet 4.5)
- (Optional) ONTAP 9.13.1+ (FPolicy, REST API)

### Deploy AWS Infrastructure

```bash
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides \
    Environment=poc \
    SoracomOperatorId=<YOUR_OPERATOR_ID> \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### Edge Device Setup

```bash
# Raspberry Pi initial setup → edge/raspberry-pi/SETUP.md

# Phase 1: Minimal config verification
cd edge/raspberry-pi/camera
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python simple_capture.py --loop
```

## Directory Structure

```
edge/                          Edge device code
  raspberry-pi/
    camera/                    Camera capture system
      simple_capture.py        Phase 1: Minimal script (for Flux)
      main.py                  Phase 2+: Full-featured (buffer, health monitoring)
    sensors/
      ontap_telemetry.py       ONTAP REST API telemetry collector
    SETUP.md                   Initial setup playbook
  soracom/                     SORACOM config guide
cloud/                         AWS cloud infrastructure
  ingestion/template.yaml      CloudFormation (S3, Kinesis, IAM, Glue)
  ai/image_analyzer/           Lambda: Two-stage image analysis
  ai/feedback_recorder/        Lambda: AI accuracy feedback recording
  processing/glue_etl_job.py   Glue ETL job
docs/                          Design documents (ja/en synced)
  ja/, en/                     Language versions
tests/                         Tests (20 tests passing)
```

## Documentation

| Document | 日本語 | English |
|----------|--------|---------|
| Use Case Research | [docs/ja/use-case-research.md](docs/ja/use-case-research.md) | [docs/en/use-case-research.md](docs/en/use-case-research.md) |
| Data Schema Design | [docs/ja/data-schema-design.md](docs/ja/data-schema-design.md) | [docs/en/data-schema-design.md](docs/en/data-schema-design.md) |
| Security Design | [docs/ja/security-design.md](docs/ja/security-design.md) | [docs/en/security-design.md](docs/en/security-design.md) |
| Operations Design | [docs/ja/operations-design.md](docs/ja/operations-design.md) | [docs/en/operations-design.md](docs/en/operations-design.md) |
| Business Story | [docs/ja/business-story.md](docs/ja/business-story.md) | [docs/en/business-story.md](docs/en/business-story.md) |
| PoC Proposal Template | [docs/ja/poc-proposal-template.md](docs/ja/poc-proposal-template.md) | [docs/en/poc-proposal-template.md](docs/en/poc-proposal-template.md) |
| FAQ | [docs/ja/faq.md](docs/ja/faq.md) | [docs/en/faq.md](docs/en/faq.md) |
| SORACOM Setup | [edge/soracom/README_ja.md](edge/soracom/README_ja.md) | [edge/soracom/README.md](edge/soracom/README.md) |

## License

MIT
