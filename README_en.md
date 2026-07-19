🌐 [日本語](README.md) | **English**

# ONTAP Edge-to-Cloud AI

[![Tests](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai/actions/workflows/test.yml/badge.svg)](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Yoshiki0705/ontap-edge-to-cloud-ai/badge)](https://scorecard.dev/viewer/?uri=github.com/Yoshiki0705/ontap-edge-to-cloud-ai)

> Reference architecture that breaks down IoT data silos by aggregating into ONTAP, enabling real-time analytics via Kafka/ClickHouse, and connecting to AWS AI services. For engineers validating edge-to-cloud data pipelines.

> **Disclaimer**: This is a personal technical exploration and does not represent official views or recommendations of any organization.

## Get Started

| I want to… | Guide | Time |
|-----------|-------|------|
| Understand the project overview | [FAQ](docs/en/faq.md) | 5 min |
| Deploy AWS infrastructure | [Deployment Guide](docs/en/deployment-guide.md) | 30 min |
| Set up edge devices | [Raspberry Pi Setup](edge/raspberry-pi/) | 20 min |
| Review the data schema | [Data Schema Design](docs/en/data-schema-design.md) | 10 min |
| Review security design | [Security Design](docs/en/security-design.md) | 15 min |
| Understand Kafka/ClickHouse integration | [Kafka Integration](docs/en/kafka-integration.md) | 15 min |

<details><summary>📂 All documentation</summary>

| Document | 日本語 | English |
|----------|--------|---------|
| Use Case Research | [docs/ja/use-case-research.md](docs/ja/use-case-research.md) | [docs/en/use-case-research.md](docs/en/use-case-research.md) |
| Data Schema Design | [docs/ja/data-schema-design.md](docs/ja/data-schema-design.md) | [docs/en/data-schema-design.md](docs/en/data-schema-design.md) |
| Kafka Integration | [docs/ja/kafka-integration.md](docs/ja/kafka-integration.md) | [docs/en/kafka-integration.md](docs/en/kafka-integration.md) |
| Security Design | [docs/ja/security-design.md](docs/ja/security-design.md) | [docs/en/security-design.md](docs/en/security-design.md) |
| Operations Design | [docs/ja/operations-design.md](docs/ja/operations-design.md) | [docs/en/operations-design.md](docs/en/operations-design.md) |
| Demo Scenarios | [docs/ja/demo-scenarios.md](docs/ja/demo-scenarios.md) | [docs/en/demo-scenarios.md](docs/en/demo-scenarios.md) |
| Databricks Integration | [docs/ja/databricks-integration.md](docs/ja/databricks-integration.md) | [docs/en/databricks-integration.md](docs/en/databricks-integration.md) |
| FAQ | [docs/ja/faq.md](docs/ja/faq.md) | [docs/en/faq.md](docs/en/faq.md) |
| Deployment Guide | [docs/ja/deployment-guide.md](docs/ja/deployment-guide.md) | [docs/en/deployment-guide.md](docs/en/deployment-guide.md) |
| Lessons Learned | [docs/ja/lessons-learned.md](docs/ja/lessons-learned.md) | [docs/en/lessons-learned.md](docs/en/lessons-learned.md) |

</details>

## Architecture

```
[Edge Devices]              [ONTAP (Aggregation)]       [Real-Time Ops]       [AI / Analytics]
                            FAS/AFF|Select|FSx for ONTAP  On-prem VMs           AWS Cloud
+------------------+        +--------------------+      +---------------+      +------------------+
| Raspberry Pi 5   |--NFS-->| Inspection images  |      | Kafka         |      | Bedrock (GenAI)  |
|   Camera         |        | Sensor CSV         |      |  (events)     |      | Athena (SQL)     |
|   Sensors        |--Kafka>| Equipment logs     |      | ClickHouse    |      | Glue (ETL)       |
+------------------+        | 3D models          |      |  (analytics)  |      | SageMaker (ML)   |
| 3D Printer       |--SMB-->|                    |      +---------------+      +------------------+
+------------------+        | FPolicy (trigger)  |            |                       |
                            | REST API (metrics) |            v                       v
[Connectivity]              | ONTAP S3 (backup)  |      [Dashboards]           [Databricks]
|- Wired LAN (10GbE)        | ARP/AI (protect)   |      Anomaly detection     Unity Catalog
|- Wi-Fi                    | Snapshot (preserve) |      Quality trends        Gold datasets
|- Cellular (option)        +--------------------+      Payload lookup         Feature tables
                                    |
                                    |--SnapMirror--> FSx for ONTAP --> S3 AP --> AWS AI
```

**Data flow:**
- **Payload** (images, CSV, logs): Edge → NFS → ONTAP
- **Events** (metadata): Edge → Kafka → ClickHouse
- **AI analysis**: ONTAP → S3 AP → Bedrock / Lambda
- **Backup**: ClickHouse → ONTAP S3

<details><summary>⚠️ Constraints & caveats</summary>

| Item | Details | Reference |
|------|---------|-----------|
| Hardware testing | Edge devices not yet arrived. Cloud side verified only | [FAQ](docs/en/faq.md) |
| AI accuracy | Synthetic image tests only (9/9 correct). Real-environment unverified | [Demo Scenarios](docs/en/demo-scenarios.md) |
| ONTAP integration | Mock tests only. Not tested against real ONTAP | [Operations Design](docs/en/operations-design.md) |
| S3 AP constraints | No conditional writes, no event notifications | [FAQ](docs/en/faq.md) |
| Scale | Single-device configuration only | — |

</details>

<details><summary>📚 Related projects & articles</summary>

| Project | Description |
|---------|-------------|
| [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) | FSx for ONTAP S3 AP × Lakehouse integrations (Kafka + ClickHouse + Databricks) |
| ↳ [manufacturing-data-platform](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/tree/main/integrations/manufacturing-data-platform) | Manufacturing data platform integration |
| [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) | FSx for ONTAP S3 AP serverless patterns (17 use cases) |

</details>

<details><summary>🔧 For developers</summary>

```bash
git clone https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai.git
cd ontap-edge-to-cloud-ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
```

Details: [CONTRIBUTING.md](CONTRIBUTING.md) | [TESTING.md](TESTING_en.md)

</details>

## License

MIT

---

🌐 [日本語](README.md) | **English**
