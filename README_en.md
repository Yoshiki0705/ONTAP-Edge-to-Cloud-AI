🌐 [日本語](README.md) | **English**

# ONTAP Edge-to-Cloud AI

> Reference architecture using NetApp ONTAP as a data hub to aggregate field data from edge devices and leverage AI/analytics

## Overview

Pipelines where edge devices (Raspberry Pi, cameras, sensors, etc.) write collected field data to ONTAP (FAS/AFF, ONTAP Select, or FSx for ONTAP) via NFS/SMB, then connect to AWS AI/analytics services through ONTAP capabilities (FPolicy, SnapMirror, S3 Access Points).

The first PoC implements **3D print quality monitoring**.

## Architecture

```
[Edge Devices]                   [ONTAP Data Hub]                 [AI / Analytics]
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
[Edge Connectivity Options]      │  Snapshot (preserve) │          │  AIDE GPU Server │
├─ Wired LAN (10GbE)            └────────────────────┘          │  Pi Edge Infer.  │
├─ Wi-Fi                                                         └──────────────────┘
├─ SORACOM Cellular (option)
└─ SORACOM S+ Camera (option)
```

### Data Flow

1. **Edge → ONTAP**: Devices write directly to ONTAP via NFS/SMB (over LAN)
2. **ONTAP → AI/Analytics**: FPolicy event-driven, SnapMirror sync, S3 AP access to AWS services
3. **AI Results → ONTAP**: Inference results written back to ONTAP, referenced by edge devices

### Why ONTAP as Data Hub

| Feature | Role |
|---------|------|
| **Multi-Protocol** | NFS (Linux/Pi) + SMB (Windows/printer) + S3 (AWS) on same data |
| **FPolicy** | Trigger automated analysis pipelines on file arrival |
| **SnapMirror** | Bandwidth-efficient edge ONTAP → cloud FSxN synchronization |
| **S3 Access Points** | Direct S3 API access to ONTAP/FSxN data (no data copying) |
| **Snapshot** | Fix datasets at any point in time (AI training data, audit) |
| **ARP/AI** | Ransomware detection and auto-protection on IoT device compromise |
| **FlexCache** | Low-latency edge reference of cloud AI results |

### Edge Devices (Options)

| Device | Connection | Purpose |
|--------|-----------|---------|
| Raspberry Pi 5 (16GB) | Wired LAN (NFS) | Camera capture, sensor collection, edge inference |
| USB Camera (4K) | Via Pi | Visual inspection, quality monitoring |
| CSI Camera (NoIR V2) | Via Pi | Low-light, near-infrared capture |
| 3D Printer | Wired LAN (SMB) | Print data storage, status integration |
| SORACOM S+ Camera | Cellular (option) | Camera for sites without wired LAN |
| SORACOM Air + Pi | Cellular (option) | Connectivity for sites without wired LAN |
| Industrial Sensors | Pi GPIO / I2C / SPI | Temperature, vibration, current, pressure |

### ONTAP Platforms (Options)

| Platform | Deployment | Characteristics |
|----------|-----------|----------------|
| FAS/AFF | On-premises | Hardware appliance. Entry to high-end |
| ONTAP Select | On-premises / VM | Software-defined. Runs on commodity servers or VMs |
| FSx for ONTAP | AWS Cloud | Fully managed. S3 AP, SnapMirror destination |

### AI/Analytics (Options)

| Service | Deployment | Purpose |
|---------|-----------|---------|
| Amazon Bedrock | Cloud | Image AI (Claude Vision), report generation |
| Amazon SageMaker | Cloud | Custom ML models (predictive maintenance, anomaly detection) |
| Amazon Athena | Cloud | SQL analytics (query ONTAP data directly via S3 AP) |
| AWS Glue | Cloud | ETL, data catalog |
| AIDE GPU Server | Local | On-premises AI inference (large models) |
| Pi Edge Inference | Edge | TensorFlow Lite / ONNX Runtime (lightweight models) |

## Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| AWS Infrastructure (CFn) | ✅ Deployed | S3, Kinesis, Lambda, IAM, Glue, SNS |
| Lambda (Two-Stage AI) | ✅ Deployed | Haiku screening + Sonnet detailed analysis |
| ONTAP Telemetry Collector | ✅ Implemented | REST API polling (mock E2E tested) |
| Edge Camera Code | ✅ Implemented | Awaiting Pi arrival for testing |
| Design Documents | ✅ Complete | 8 documents, ja/en synced |
| Hardware Testing | 📋 Pending | After Pi + camera + ONTAP arrival |

## Quick Start

### Prerequisites

- AWS CLI v2 + credentials configured
- Python 3.12+
- Bedrock model access enabled (Claude Haiku 4.5 / Sonnet 4.5)
- ONTAP 9.13.1+ (FPolicy, REST API, S3 AP)

### Deploy AWS Infrastructure

```bash
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides Environment=poc \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1
```

### Edge Device Setup

```bash
# Raspberry Pi initial setup → edge/raspberry-pi/SETUP.md
cd edge/raspberry-pi/camera
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python simple_capture.py --loop
```

## Directory Structure

```
edge/                          Edge device code
  raspberry-pi/
    camera/                    Camera capture → ONTAP NFS write
    sensors/                   ONTAP REST API telemetry collector
    SETUP.md                   Initial setup playbook
  soracom/                     SORACOM config guide (option)
cloud/                         AWS cloud infrastructure
  ingestion/template.yaml      CloudFormation
  ai/                          Lambda (image analysis, feedback recording)
  processing/                  Glue ETL
docs/                          Design documents (ja/en synced)
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

## Related Projects

- [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) — FSx for ONTAP S3 Access Points × Lakehouse integrations (parent project)

## License

MIT
