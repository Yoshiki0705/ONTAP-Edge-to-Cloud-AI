🌐 [日本語](README.md) | **English**

# ONTAP Edge-to-Cloud AI

> Reference architecture for leveraging factory/site NAS data with edge devices and AI

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

| Storage | What's Possible | Additional Value with ONTAP |
|---------|----------------|---------------------------|
| S3 direct | Edge → S3 → Athena/Bedrock | — (simplest approach) |
| EFS | NFS mount → Lambda/Bedrock | — |
| **ONTAP** | All of the above + below | FPolicy (event-driven), SnapMirror (incremental sync), Multi-Protocol (NFS+SMB+S3 on same data), Snapshot (data preservation), ARP/AI (security) |

ONTAP's additional value applies when:
- You already have ONTAP/NAS with accumulated data
- You need both NFS and SMB access to the same data
- You want to analyze data via S3 API without copying to cloud
- You want file-arrival-triggered automated processing

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
| PoC Planning Template | [docs/ja/poc-proposal-template.md](docs/ja/poc-proposal-template.md) | [docs/en/poc-proposal-template.md](docs/en/poc-proposal-template.md) |
| FAQ | [docs/ja/faq.md](docs/ja/faq.md) | [docs/en/faq.md](docs/en/faq.md) |

## Related Projects

- [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) — FSx for ONTAP S3 AP × Lakehouse integrations

## License

MIT
