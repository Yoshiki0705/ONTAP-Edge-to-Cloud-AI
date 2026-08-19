🌐 [日本語](README.md) | **English**

# ONTAP Edge-to-Cloud AI

[![Tests](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai/actions/workflows/test.yml/badge.svg)](https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Yoshiki0705/ontap-edge-to-cloud-ai/badge)](https://scorecard.dev/viewer/?uri=github.com/Yoshiki0705/ontap-edge-to-cloud-ai)

**TL;DR**: designs and **deployable code** for aggregating the data that IoT devices produce at a
factory or site into one place, analysing it with Kafka and ClickHouse, and connecting it to AWS AI
services. FSx for ONTAP is the storage layer in the worked example; the differences when using S3 or
EFS are stated alongside it.

## What is here

Three maturity levels per row. **Implemented** means deployable code exists in this repository.
**Design only** means the design is written but there is no code. **Concept** means an outline only.

| Area | Contents | Maturity | Location |
|------|----------|----------|----------|
| Edge collection | Camera capture, sensor reads, Kafka publish, local buffering during disconnection with replay on recovery | Implemented | [`edge/raspberry-pi/`](edge/raspberry-pi/) |
| Event schema | The v3 schema shared across Kafka, ClickHouse and Databricks | Implemented | [`edge/raspberry-pi/common/event_schema.py`](edge/raspberry-pi/common/event_schema.py) |
| ONTAP telemetry collection | REST API polling for performance, capacity and health | Implemented (not verified on hardware) | [`edge/raspberry-pi/sensors/ontap_telemetry.py`](edge/raspberry-pi/sensors/ontap_telemetry.py) |
| Two-stage AI image analysis | Screen with a cheap model, escalate only suspected anomalies | Implemented | [`cloud/ai/image_analyzer/`](cloud/ai/image_analyzer/) |
| Feedback recording | Human labels against AI verdicts | Implemented | [`cloud/ai/feedback_recorder/`](cloud/ai/feedback_recorder/) |
| MQTT ingestion | IoT Core → Lambda → S3 access point | Implemented | [`cloud/iot_ingestion/`](cloud/iot_ingestion/) |
| Shared infrastructure (CFn) | S3, Kinesis, IAM, Glue, SNS | Implemented | [`cloud/ingestion/template.yaml`](cloud/ingestion/template.yaml) |
| FSx for ONTAP (CFn) | File system, SVM, volumes | Implemented | [`cloud/fsxn/`](cloud/fsxn/) |
| ClickHouse schema | Kafka engine tables, materialized views, rollups, dead letter | Implemented | [`cloud/clickhouse/ddl/`](cloud/clickhouse/ddl/) |
| Use case: 3D print quality monitoring | Template, Lambda, Athena queries, ONTAP setup | Implemented | [`usecases/3d-print-quality/`](usecases/3d-print-quality/) |
| Use case: visual inspection | The above with a different prompt | Implemented | [`usecases/visual-inspection/`](usecases/visual-inspection/) |
| Use case: ONTAP telemetry analytics | Glue crawler and Athena queries | Implemented | [`usecases/ontap-telemetry-analytics/`](usecases/ontap-telemetry-analytics/) |
| Local demo | Run the event path with no physical hardware | Implemented | [`local-demo/`](local-demo/) |
| Kafka / ClickHouse placement | Topology and topic design. No IaC | Design only | [kafka-integration](docs/en/kafka-integration.md) |
| Databricks integration | Four connection paths and Unity Catalog design | Design only | [databricks-integration](docs/en/databricks-integration.md) |
| FlexCache / SnapMirror | Edge write paths and read delivery | Design only | [iot-greengrass-flexcache-integration](docs/en/iot-greengrass-flexcache-integration.md) |
| Greengrass custom S3 client | Direct PutObject to an S3 access point | Design only (walkthrough exists) | [demo-guide-02](docs/demo-guides/demo-guide-02-greengrass-s3ap-client.md) |

Nine designs are laid out in the [AWS pattern catalog](docs/en/aws-patterns/README.md), each with a
maturity label and a note on when to choose it. What has and has not been verified on hardware is
collected under [About this repository](#about-this-repository).

## Architecture

![Files written by cameras and vibration sensors at an edge site are aggregated through local storage into Amazon FSx for NetApp ONTAP, and reach Amazon Bedrock, Amazon Athena and Amazon SageMaker AI through an S3 access point. Sensor events take two separate paths, to AWS IoT Core and to Kafka / ClickHouse](docs/images/architecture-overview-en.svg)

Figure 1: overall architecture ([.drawio](docs/diagrams/architecture-overview-en.drawio) / [日本語](docs/images/architecture-overview.svg))

**Data paths:**
- **Payload** (images, CSV, logs): edge → NFS → ONTAP (stored)
- **Events** (metadata): edge → Kafka → ClickHouse (analytics)
- **AI analysis**: ONTAP → S3 AP → Bedrock / Lambda (quality verdict)
- **Backup**: ClickHouse → ONTAP S3 (S3-compatible storage)

## The problem

Factories and sites generate data continuously from IoT devices — cameras, sensors, control PCs.
In most cases that data ends up scattered per device and per site.

**What this looks like:**
- Camera images in the printer vendor's cloud, sensor data on the Pi's SD card, equipment logs on a Windows PC
- No way to analyse data from site A alongside site B
- Individual device data is visible, but the whole picture — correlation, trends — is not
- Analysis with AI is wanted, but the data is scattered and no pipeline can be built

On the edge and on-premises side:
- The platform and tooling for cross-cutting analysis are not in place
- Governance, cataloguing and access control have to be built from nothing
- Building the analytics platform itself costs enough time and money that data work never starts

## Approach

A hybrid pipeline: aggregate scattered IoT data into a storage layer, analyse with Kafka and
ClickHouse, and run image analysis on AWS AI services.

**Data flow:**
1. Edge devices write to storage over NFS (payload: images, CSV)
2. In parallel, they publish a structured event to Kafka (metadata: when, where, what)
3. ClickHouse ingests from Kafka and serves dashboards and anomaly detection
4. Amazon Bedrock (via Lambda) analyses images and returns a quality verdict
5. Databricks manages curated datasets and produces AI training data

**Before → After:**

| | Before | After |
|---|--------|-------|
| Data | Siloed per device | Aggregated, distributed over Kafka |
| Analysis | No means (tooling has to be built first) | Dashboards in ClickHouse |
| Anomaly detection | Human inspection (impossible unattended) | AI detects and alerts (target: within 60 seconds of capture; not measured on hardware) |
| Cross-site analysis | Impossible | Quality trends across sites in Databricks |

### Who this is for

- **IoT / edge developers** looking for how to aggregate and use the data devices produce
- **Data practitioners** wanting to break device-level silos and analyse across an organisation
- **Existing ONTAP users** wanting to use ONTAP as the aggregation point for IoT data
- **AWS users** wanting to use Athena, Bedrock or SageMaker against a source other than S3

### Storage layer options

The core pattern — edge collection, aggregation, AI analysis — holds with a different aggregation
point.

| Storage | Data flow | Characteristics | Constraints |
|---------|-----------|-----------------|-------------|
| **S3 directly** | Edge → S3 → Athena/Bedrock | Simplest. Easy setup. Native AWS integration. S3 Object Lock for tamper protection. Edge caching via CloudFront | No NFS/SMB access. Integrating with existing file workflows takes extra work. Event-driven via S3 Event Notifications |
| **EFS** | Edge → NFS → EFS → Lambda/Bedrock | NFS mountable. Good fit for Linux devices. Auto-scaling. Protected by AWS Backup | No SMB. No direct S3 API access. Event-driven has to be built with Lambda + CloudWatch. Cross-Region via EFS Replication |
| **ONTAP** | Edge → NFS/SMB → ONTAP → S3 AP → AWS AI | NFS, SMB and S3 over the same data. FPolicy for file-arrival triggers. SnapMirror for differential sync. FlexCache for low-latency delivery to remote sites. ARP/AI for ransomware anomaly detection with automatic Snapshot protection | Requires an ONTAP environment. S3 AP does not support conditional writes, and [has other constraints](docs/en/s3ap-compatibility-matrix.md). Operating it requires ONTAP knowledge |

**How to choose:**
- No data yet, building fresh → **S3 directly** is simplest
- Writing over NFS from Linux devices, staying inside a VPC → **EFS**
- Data already on ONTAP/NAS, both NFS and SMB needed, avoiding a copy → **ONTAP**

### Edge devices (options)

| Device | Connection | Use |
|--------|------------|-----|
| Raspberry Pi 5 | Wired LAN (NFS) | Camera capture, sensor collection, edge inference |
| USB camera (4K) | Via Pi | Visual inspection, quality monitoring |
| CSI camera (NoIR V2) | Via Pi | Low-light and near-infrared capture |
| 3D printer | Wired LAN (SMB) | Print data storage |
| SORACOM S+ Camera | Cellular (option) | Sites without wired LAN |
| SORACOM Air + Pi | Cellular (option) | Connectivity for sites without wired LAN |
| Industrial sensors | Pi GPIO / I2C / SPI | Temperature, humidity, vibration, current |

### ONTAP platforms (options)

| Platform | Placement | Characteristics |
|----------|-----------|-----------------|
| FAS/AFF | On-premises | Hardware appliance |
| ONTAP Select | On-premises / VM | Software-defined, runs on general-purpose servers or VMs |
| FSx for ONTAP | AWS cloud | Fully managed. SnapMirror destination, supports S3 AP (ONTAP 9.17.1 or later) |

## Quick start

### Prerequisites

- AWS CLI v2 with credentials configured
- Python 3.12+
- Bedrock model access enabled
- ONTAP 9.13.1+ (FPolicy, REST API). **9.17.1 or later** for S3 Access Points
  ([source](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/access-point-for-fsxn-restrictions-limitations-naming-rules.html))

### Deploy

```bash
# AWS infrastructure
aws cloudformation deploy \
  --template-file cloud/ingestion/template.yaml \
  --stack-name edge-to-cloud-ai-poc \
  --parameter-overrides Environment=poc \
  --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-1

# Edge device → edge/raspberry-pi/SETUP_en.md
```

The event path can be run without any physical hardware via [`local-demo/`](local-demo/).
The full procedure is in the [deployment guide](docs/en/deployment-guide.md).

## Documentation

| Document | 日本語 | English |
|----------|--------|---------|
| **AWS pattern catalog** (9 patterns) | [aws-patterns](docs/ja/aws-patterns/README.md) | [aws-patterns](docs/en/aws-patterns/README.md) |
| **Deployment models** (differences by scale and industry) | [deployment-models](docs/ja/deployment-models/README.md) | [deployment-models](docs/en/deployment-models/README.md) |
| Agentic AI on AWS | [agentic-ai-on-aws](docs/ja/agentic-ai-on-aws.md) | [agentic-ai-on-aws](docs/en/agentic-ai-on-aws.md) |
| Flexible AI Data Layer (forward-looking) | [flexible-ai-data-layer](docs/ja/flexible-ai-data-layer.md) | [flexible-ai-data-layer](docs/en/flexible-ai-data-layer.md) |
| Deployment guide | [deployment-guide](docs/ja/deployment-guide.md) | [deployment-guide](docs/en/deployment-guide.md) |
| S3 AP compatibility and constraints | [s3ap-compatibility-matrix](docs/ja/s3ap-compatibility-matrix.md) | [s3ap-compatibility-matrix](docs/en/s3ap-compatibility-matrix.md) |
| **Verification status** (how far it ran on real hardware) | [verification-status](docs/ja/verification-status.md) | [verification-status](docs/en/verification-status.md) |
| Use case research | [use-case-research](docs/ja/use-case-research.md) | [use-case-research](docs/en/use-case-research.md) |
| Data schema design | [data-schema-design](docs/ja/data-schema-design.md) | [data-schema-design](docs/en/data-schema-design.md) |
| Kafka integration design | [kafka-integration](docs/ja/kafka-integration.md) | [kafka-integration](docs/en/kafka-integration.md) |
| Greengrass + FlexCache integration | [iot-greengrass-flexcache-integration](docs/ja/iot-greengrass-flexcache-integration.md) | [iot-greengrass-flexcache-integration](docs/en/iot-greengrass-flexcache-integration.md) |
| Databricks integration | [databricks-integration](docs/ja/databricks-integration.md) | [databricks-integration](docs/en/databricks-integration.md) |
| Security design | [security-design](docs/ja/security-design.md) | [security-design](docs/en/security-design.md) |
| Operations design | [operations-design](docs/ja/operations-design.md) | [operations-design](docs/en/operations-design.md) |
| Demo scenarios | [demo-scenarios](docs/ja/demo-scenarios.md) | [demo-scenarios](docs/en/demo-scenarios.md) |
| FAQ | [faq](docs/ja/faq.md) | [faq](docs/en/faq.md) |

Architecture diagrams (official icons, both languages): [docs/diagrams/](docs/diagrams/)

Demo walkthroughs (English only): [prerequisites](docs/demo-guides/demo-guide-00-prerequisites.md) /
[IoT Core → Lambda → S3 AP](docs/demo-guides/demo-guide-01-iot-core-lambda-s3ap.md) /
[Greengrass → S3 AP client](docs/demo-guides/demo-guide-02-greengrass-s3ap-client.md)

For maintainers: [quality gates](docs/agent/quality-gates_en.md) /
[supply chain security](docs/agent/supply-chain-security_en.md) /
[reference doc quality bar](docs/agent/reference-doc-quality_en.md) /
[testing](TESTING_en.md) / [contributing](CONTRIBUTING.md)

## About this repository

> **Disclaimer**: this project is personal technical exploration. It does not represent the official
> position or recommendation of any employer, and it does not recommend purchasing any product.

### Current limits

- **Hardware testing incomplete**: the edge devices (Raspberry Pi, cameras) have not arrived, so
  no end-to-end test on hardware has run. The only thing measured on real AWS is the two-stage
  Amazon Bedrock analysis, and there is no record of a SAM template ever being deployed. The status
  of each stage is in [verification status](docs/en/verification-status.md)
- **AI accuracy comes from two different tests**: 4/4 on four photographs published in vendor
  documentation, and 5/5 on five written descriptions of symptoms. Synthetic images generated with
  OpenCV were a separate round and were correctly identified as not photographic. **The two measure
  different things and are not additive.** Accuracy under real conditions — lighting, camera angle,
  filament colour — is unverified
- **ONTAP integration is design only**: the FPolicy, SnapMirror and S3 AP code is written, but has
  not run against a real ONTAP system (mock tests only)
- **Single device**: concurrent operation of multiple devices and scale-out are unverified
- **Kafka / ClickHouse pending**: awaiting a managed platform deployment. The path is exercised
  through [`local-demo/`](local-demo/) in the meantime

### What has been learned so far

- **Two-stage AI analysis can lower cost (calculated)**: analysing every image with the
  high-accuracy model works out to ~$259/month, while screening with a cheap model and escalating
  only suspected anomalies works out to ~$40/month. These are **calculations**, not measurements:
  they assume 60-second intervals, continuous operation, a 10% anomaly rate and model pricing in
  one Region. A lower anomaly rate narrows the gap
  ([figures at a realistic defect rate](tests/sample_images/README.md)). The pattern itself applies
  to other AI pipelines
- **Prompting alone reaches usable accuracy for industrial image checks**: 4 of 4 on photographs
  from vendor documentation with Claude Vision prompts and no custom model training. Verification
  under real
  conditions is still ahead
- **FSx for ONTAP S3 Access Points carry constraints**: no conditional writes and no event
  notifications, so Iceberg and Delta Lake cannot be written directly and FPolicy has to fill the
  gap. The full list, with the basis for each item, is in
  [S3 AP compatibility and constraints](docs/en/s3ap-compatibility-matrix.md)
- **The ONTAP REST API is usable for IoT telemetry**: performance metrics, capacity and health at
  one-minute intervals. Polling-based, but sufficient for a proof of concept

### Why this exists

Visiting sites as an SA/SE, one comment kept recurring: data from IoT devices and sensors sits
separately per site and per device, and cannot be analysed across them. The data is being produced;
the silos are what prevent using it. On the on-premises side there was also no analytics platform or
governance tooling in place, so "we would have to build the tools first" became the reason nothing
started.

Three things arriving together made "aggregate, then analyse across" cheap enough to attempt:

- **FSx for ONTAP S3 Access Points**: S3 API access to aggregated data without a copy
- **Multimodal AI maturity**: general-purpose prompts reaching usable accuracy on industrial images
- **Raspberry Pi 5 (16GB)**: enough capacity for preprocessing and light inference at the edge

**3D print quality monitoring** was chosen as the first subject: visually legible, and failures
happen often enough to gather test data.

## Related projects

- [fsxn-lakehouse-integrations](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations) — FSx for ONTAP S3 AP × lakehouse integration (**the Kafka, ClickHouse and Databricks side lives here**)
  - The integration itself: [integrations/manufacturing-data-platform](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/tree/main/integrations/manufacturing-data-platform)
  - Sync record: [Edge ↔ Lakehouse sync](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/blob/main/integrations/manufacturing-data-platform/docs/en/14_edge_lakehouse_sync.md) ([日本語](https://github.com/Yoshiki0705/fsxn-lakehouse-integrations/blob/main/integrations/manufacturing-data-platform/docs/ja/14_edge_lakehouse_sync.md)) — schema, topics and division of responsibility
- [FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns](https://github.com/Yoshiki0705/FSx-for-ONTAP-S3AccessPoints-Serverless-Patterns) — serverless patterns for FSx for ONTAP S3 AP (17 use cases)

## License

MIT
