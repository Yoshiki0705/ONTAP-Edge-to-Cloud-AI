# Security Design

> Created: 2026-05-29
> Scope: PoC #1 (3D Print Quality Monitoring) / PoC #2 (ONTAP Telemetry)
> Status: Draft

---

## 1. Design Principles

| Principle | Rationale |
|-----------|-----------|
| Least Privilege | Each component holds only minimum required permissions |
| Device auth via NFS/Kerberos + certificates | PoC phase: NFSv3 (sys auth) for rapid start. Phase 6: migrate to NFS v4.1 + Kerberos |
| Mandatory encryption in transit and at rest | Protect data over LAN/cellular and on S3/ONTAP |
| No secrets in code | Manage via environment variables / AWS Secrets Manager |
| Network segmentation | Separate ONTAP management plane from IoT data plane |

---

## 2. Authentication & Authorization Flow Overview

```
[Raspberry Pi]                    [ONTAP]                   [AWS]
┌─────────────┐                  ┌──────────────┐          ┌─────────────────────┐
│              │                  │              │          │                     │
│ NFS v4.1    │──wired LAN──→   │ FPolicy ─────│──────→   │ Lambda              │
│ + Kerberos   │  (primary)      │              │          │   ↓                 │
│              │                  │ SnapMirror ──│──────→   │ Bedrock / Athena    │
│              │                  │              │          │                     │
└─────────────┘                  └──────────────┘          └─────────────────────┘
       │
       │ (option: for sites without wired LAN)
       ▼
┌─────────────┐                  ┌──────────┐             ┌─────────────────────┐
│ SIM auth     │──cellular────→  │ SORACOM  │──IAM Role──→│ S3 / Kinesis        │
│ (automatic)  │                  │ Air/Beam │ (AssumeRole)│                     │
└─────────────┘                  └──────────┘             └─────────────────────┘
```

---

## 3. IAM Role Design

### 3.1 Role Inventory

| Role Name | Trust Entity | Purpose |
|-----------|-------------|---------|
| `EdgeToCloud-SoracomIngestion` | SORACOM (external account) | (Option: cellular connectivity only) S3/Kinesis writes from Funnel/Beam |
| `EdgeToCloud-KinesisProcessor` | Lambda | Data processing from Kinesis stream |
| `EdgeToCloud-ImageAnalyzer` | Lambda | S3 image retrieval + Bedrock invocation |
| `EdgeToCloud-GlueETL` | Glue | S3 read/write + Data Catalog updates |
| `EdgeToCloud-AthenaQuery` | IAM User/Role | Athena query execution + S3 result writes |
| `EdgeToCloud-BedrockInvoke` | Lambda | Bedrock model invocation only |

### 3.2 Policy Details

#### EdgeToCloud-SoracomIngestion (Option: cellular connectivity only)

Role used by SORACOM Funnel/Beam via AssumeRole:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowKinesisWrite",
      "Effect": "Allow",
      "Action": [
        "kinesis:PutRecord",
        "kinesis:PutRecords"
      ],
      "Resource": "arn:aws:kinesis:${AWS_REGION}:${ACCOUNT_ID}:stream/edge-to-cloud-*"
    },
    {
      "Sid": "AllowS3Write",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/raw/*"
    }
  ]
}
```

Trust policy (trusting SORACOM's AWS account):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::762707677580:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "${SORACOM_OPERATOR_ID}"
        }
      }
    }
  ]
}
```

> **Note**: `762707677580` is SORACOM's public AWS account ID (documented in [official docs](https://developers.soracom.io/en/docs/funnel/)). Set ExternalId to your SORACOM operator ID.

#### EdgeToCloud-ImageAnalyzer

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3Read",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/raw/image_capture/*"
    },
    {
      "Sid": "AllowBedrockInvoke",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel"
      ],
      "Resource": "arn:aws:bedrock:${AWS_REGION}::foundation-model/anthropic.claude-*"
    },
    {
      "Sid": "AllowResultWrite",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/processed/image_analysis/*"
    },
    {
      "Sid": "AllowSNSPublish",
      "Effect": "Allow",
      "Action": [
        "sns:Publish"
      ],
      "Resource": "arn:aws:sns:${AWS_REGION}:${ACCOUNT_ID}:edge-to-cloud-alerts"
    }
  ]
}
```

#### EdgeToCloud-GlueETL

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3ReadWrite",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::${BUCKET_NAME}/raw/*",
        "arn:aws:s3:::${BUCKET_NAME}/processed/*",
        "arn:aws:s3:::${BUCKET_NAME}/curated/*"
      ]
    },
    {
      "Sid": "AllowS3List",
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::${BUCKET_NAME}"
    },
    {
      "Sid": "AllowGlueCatalog",
      "Effect": "Allow",
      "Action": [
        "glue:GetDatabase",
        "glue:GetTable",
        "glue:GetPartitions",
        "glue:CreatePartition",
        "glue:UpdateTable"
      ],
      "Resource": [
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:catalog",
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:database/edge_to_cloud_ai",
        "arn:aws:glue:${AWS_REGION}:${ACCOUNT_ID}:table/edge_to_cloud_ai/*"
      ]
    }
  ]
}
```

---

## 4. Network Security

### 4.1 Network Segment Design

```
┌─────────────────────────────────────────────────────────┐
│ Edge Network                                            │
│                                                         │
│  VLAN 10: IoT Data Plane                                │
│  ┌──────────┐     ┌──────────┐                          │
│  │ Pi (eth0)│────→│ ONTAP    │  NFS v4.1 (data R/W)     │
│  │          │     │ data LIF │                          │
│  └──────────┘     └──────────┘                          │
│       │                                                 │
│  VLAN 20: ONTAP Management Plane (no Pi access)         │
│  ┌──────────┐     ┌──────────┐                          │
│  │ Admin PC  │────→│ ONTAP    │  HTTPS (System Manager)  │
│  │          │     │ mgmt LIF │                          │
│  └──────────┘     └──────────┘                          │
│                                                         │
│  VLAN 30: FPolicy / REST API (restricted access)        │
│  ┌──────────┐     ┌──────────┐                          │
│  │ Pi (eth0)│────→│ ONTAP    │  FPolicy + REST API      │
│  │ :limited │     │ data LIF │  (port-restricted)       │
│  └──────────┘     └──────────┘                          │
│                                                         │
│  Cellular (SORACOM Air)                                 │
│  ┌──────────┐                                           │
│  │ Pi (usb0)│────→ Internet → SORACOM → AWS             │
│  └──────────┘                                           │
└─────────────────────────────────────────────────────────┘
```

### 4.2 Firewall Rules (Pi side: ufw)

```bash
# Default: deny all
sudo ufw default deny incoming
sudo ufw default deny outgoing

# ONTAP NFS (VLAN 10 only)
sudo ufw allow out to <ONTAP_DATA_LIF_IP> port 2049 proto tcp  # NFS
sudo ufw allow out to <ONTAP_DATA_LIF_IP> port 111 proto tcp   # portmapper

# ONTAP REST API (VLAN 30, telemetry collection)
sudo ufw allow out to <ONTAP_DATA_LIF_IP> port 443 proto tcp   # HTTPS

# SORACOM (cellular interface) — Option: cellular connectivity only
sudo ufw allow out on usb0 to any port 443 proto tcp   # HTTPS (Beam/Funnel)
sudo ufw allow out on usb0 to any port 8883 proto tcp  # MQTTS (IoT Core)

# DNS
sudo ufw allow out to any port 53

# SSH (admin only, specific IP)
sudo ufw allow in from <ADMIN_NETWORK> to any port 22 proto tcp

sudo ufw enable
```

### 4.3 S3 Bucket Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyUnencryptedTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::${BUCKET_NAME}",
        "arn:aws:s3:::${BUCKET_NAME}/*"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    },
    {
      "Sid": "DenyIncorrectEncryptionHeader",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::${BUCKET_NAME}/*",
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-server-side-encryption": "aws:kms"
        }
      }
    }
  ]
}
```

---

## 5. Encryption Design

| Layer | Method | Details |
|-------|--------|---------|
| **In transit (Pi → ONTAP)** | NFS v4.1 + Kerberos (recommended) or dedicated VLAN | Primary path. PoC: dedicated VLAN acceptable. Production: Kerberos required |
| **In transit (Pi → SORACOM)** | TLS 1.2+ | Option: cellular connectivity only. SORACOM Beam terminates TLS |
| **In transit (SORACOM → AWS)** | TLS 1.2+ | Option: cellular connectivity only. SORACOM → AWS always uses TLS |
| **At rest (S3)** | SSE-KMS (AWS managed key) | Enforced via bucket default encryption |
| **At rest (ONTAP)** | NVE (NetApp Volume Encryption) | AES-256, enabled per volume |
| **At rest (Kinesis)** | SSE-KMS | Enabled at stream creation |

---

## 6. ONTAP Authentication Design

### 6.1 REST API Access

| Item | Setting |
|------|---------|
| Auth method | Local user + HTTPS certificate auth |
| Username | `svc-iot-telemetry` (service account) |
| Role | `readonly` (custom role: GET only for metrics/volumes/nodes) |
| Source restriction | Allow only Pi IP address (data-interface firewall-policy) |

```bash
# ONTAP CLI: Service account creation example
security login create -vserver svm-iot \
  -user-or-group-name svc-iot-telemetry \
  -application http \
  -authentication-method password \
  -role iot-readonly

# Custom role creation
security login role create -vserver svm-iot \
  -role iot-readonly \
  -cmddirname "volume show" \
  -access readonly
```

### 6.2 FPolicy External Server

| Item | Setting |
|------|---------|
| Communication protocol | TCP (FPolicy protocol) |
| Authentication | Mutual SSL certificates (ONTAP 9.13.1+) |
| Pi-side port | Dynamically assigned (ONTAP initiates connection) |
| Communication direction | ONTAP → Pi (ONTAP is the client) |

---

## 7. Secret Management

| Secret | Storage Location | Rotation |
|--------|-----------------|----------|
| ONTAP REST API password | Pi: environment variable (systemd EnvironmentFile) | Every 90 days |
| SORACOM API Key/Token | Not used (SIM auth only) | — |
| AWS credentials | Not used (FPolicy→Lambda handled by ONTAP side; cellular uses SORACOM AssumeRole) | — |
| FPolicy SSL certificate | Pi: /etc/fpolicy/certs/ (600 permission) | Annually |
| SSH key (Pi admin) | Administrator's local machine | Annually |

> **Important**: Never place AWS Access Key / Secret Key on Pi. AWS access goes through FPolicy → Lambda (via ONTAP) or through SORACOM's AssumeRole mechanism when using cellular connectivity.

---

## 8. Device Hardening (Raspberry Pi)

```bash
# 1. Disable unnecessary services
sudo systemctl disable bluetooth
sudo systemctl disable avahi-daemon
sudo systemctl disable cups

# 2. Automatic security updates
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades

# 3. SSH hardening (/etc/ssh/sshd_config)
PermitRootLogin no
PasswordAuthentication no
MaxAuthTries 3
AllowUsers iot-operator

# 4. Filesystem protection
# Mount /tmp with noexec
echo "tmpfs /tmp tmpfs defaults,noexec,nosuid,nodev 0 0" >> /etc/fstab

# 5. Log monitoring
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

---

## 9. Incident Response

| Scenario | Detection | Response |
|----------|-----------|----------|
| Pi compromise (rogue process) | fail2ban alert, abnormal traffic patterns | Isolate Pi from network, disable ONTAP FPolicy, suspend SIM |
| Unauthorized ONTAP writes | ARP/AI alert | Auto Snapshot → admin notification → identify and block write source |
| AWS credential leak | CloudTrail anomaly detection | Temporarily disable IAM role, rotate SORACOM ExternalId |
| Cellular line abuse | SORACOM console traffic anomaly | Suspend SIM, review communication logs |

---

## 10. Data Classification

| Level | Definition | Examples in This Project | Protection Requirements |
|-------|-----------|------------------------|------------------------|
| **Public** | Externally publishable | Architecture diagrams, public docs | Integrity protection only |
| **Internal** | Internal stakeholders only | Sensor data, telemetry | Access control + encryption |
| **Confidential** | Need-to-know basis only | Inspection images (may contain product design) | Encryption + audit log + access restriction |
| **Restricted** | Specific approvers only | — (not applicable in this PoC) | Above + MFA + physical controls |

### Data Classification for This Project

| Data Type | Classification | Rationale | Storage |
|-----------|---------------|-----------|---------|
| 3D print images | Internal~Confidential | Product shapes may be visible | S3 (SSE-KMS) / ONTAP (NVE) |
| Sensor data (temp/humidity) | Internal | Environmental info, low direct sensitivity | S3 (SSE-KMS) |
| ONTAP telemetry | Internal | Contains infrastructure configuration info | S3 (SSE-KMS) |
| AI analysis results | Internal | Contains references to source images | S3 (SSE-KMS) |
| Feedback records | Internal | Operator judgment records | S3 (SSE-KMS) |
| 3D model files (STL/3MF) | Confidential | Product design intellectual property | ONTAP (NVE) |

> **Note**: When implementing at customer sites, follow the customer's data classification policy. Above is for internal lab environment.

---

## 11. Privacy Impact Assessment (Camera Installation)

Perform the following checks when installing cameras:

| Check Item | Action |
|-----------|--------|
| Could people appear in capture area | Verify before installation. Conduct PIA if possible |
| Is capture target limited to products/equipment | Restrict camera angle to products/equipment only |
| Is prior employee notification required | Follow internal policy; post notices/explain as needed |
| Is image retention period appropriate | Set based on data classification (raw: 90d→IA→Glacier) |
| Is image access minimally scoped | Restrict via IAM + S3 bucket policy |
| Is there a procedure to delete unneeded images | S3 lifecycle policy + manual deletion procedure |

> **PoC (internal lab)**: Capture target is 3D printer only. No people in frame. PIA not required.
> **Customer environment**: Follow customer privacy policy; conduct PIA as needed.

---

## 12. Compliance Checklist

| Item | PoC | Production |
|------|-----|-----------|
| S3 encryption (SSE-KMS) | ✅ Required | ✅ Required |
| HTTPS enforcement (bucket policy) | ✅ Required | ✅ Required |
| IAM least privilege | ✅ Required | ✅ Required |
| CloudTrail enabled | ○ Recommended | ✅ Required |
| VPC Flow Logs | — Not needed (no VPC) | ✅ Required |
| GuardDuty | ○ Recommended | ✅ Required |
| ONTAP audit logs | ○ Recommended | ✅ Required |
| Pi firewall (ufw) | ✅ Required | ✅ Required |
| NFS encryption | ○ Dedicated VLAN substitute | ✅ Kerberos required |
| Secret rotation | ○ Manual | ✅ Automated |

---

## 13. OT/IT Boundary

Section 4 covers network separation on the IT side. This section covers what is
additionally needed when that edge network sits **on the same floor as production
equipment (OT)**. IT-side separation is not sufficient on its own because the
availability requirements and blast radius on the OT side differ from the IT side.

> **Scope note**: This section states design considerations. It is not a claim of
> IEC 62443 conformance. For a connection to regulated equipment, certification
> and conformity decisions are outside the scope of this document.

### 13.1 Keep the data flow one-way

This architecture only ever **sends** from edge to cloud. No path is created that
lets the cloud reach into the OT network.

| Path | Direction | Implementation |
|------|-----------|----------------|
| Pi → IoT Core (MQTT) | send only | the Pi publishes; it does not subscribe |
| Pi → ONTAP (NFS) | bidirectional, same LAN | confined to VLAN 10 |
| ONTAP → AWS (SnapMirror) | send only | initiated from the ONTAP side |
| Lambda → FSx for ONTAP S3 AP | write only | nothing from the cloud reaches OT |

**Paths deliberately absent**: cloud-to-edge command delivery (IoT Jobs, remote
control via MQTT subscribe, SSH exposed to the internet). A feature that stops a
printer remotely is also a control path for whoever compromises it. If one becomes
necessary, design it on top of an independent OT-side safety mechanism (physical
stop, PLC interlock) rather than making the cloud path the only means of control.

### 13.2 Device identity does not come from the payload

What MQTT authenticates is the **client certificate and client ID**, not the
`device_id` field inside the payload. The payload is whatever the publisher chose
to write.

```
# IoT Core rule SQL: attach the authenticated identifiers under names the payload cannot collide with
SELECT *, clientid() as client_id, topic(2) as topic_device_id FROM 'edge/+/telemetry'
```

The Lambda prefers `client_id`, then `topic_device_id`, then the payload's
`device_id` (`cloud/iot_ingestion/identifiers.py`).

**Measured problem**: before the fix, `device_id` was taken from the payload and
interpolated straight into an S3 key. Sending `device_id = "../../../etc/shadow"`
produced the key `ingest/../../../etc/shadow/year=2026/...`. S3 does not normalise
`..`, so the object is created under that literal key. The **consumers** normalise:
an FSx for ONTAP S3 AP maps a key onto a path in a real filesystem namespace, and
Athena/Glue read `ingest/<device_id>/year=.../` as Hive partitions. A `..` segment
is therefore an escape from the intended prefix rather than a cosmetic oddity. A
value containing CR/LF lands in a `PutObject` metadata header.

Scope the IoT policy per Thing. Allowing a wildcard publish lets one compromised
device write anywhere in every other device's data space.

```json
{
  "Effect": "Allow",
  "Action": "iot:Publish",
  "Resource": "arn:aws:iot:<region>:<account>:topic/edge/${iot:Connection.Thing.ThingName}/telemetry"
}
```

Reference: [Thing policy variables](https://docs.aws.amazon.com/iot/latest/developerguide/thing-policy-variables.html)

### 13.3 Do not extend a blast radius into OT

| Failure | Edge behaviour | Effect on OT |
|---------|----------------|--------------|
| Cloud unreachable | accumulates in the local SQLite buffer (`edge/greengrass/s3ap_client/buffer.py`) | none; equipment keeps running |
| Buffer full | evicts oldest first, raises `BufferFullError` | none; monitoring has a gap |
| ONTAP unreachable | NFS write fails, falls back to the cellular path | none |
| Pi failure | collection stops | none; the Pi observes and does not control |

**Design premise**: the Pi is observation-only and is not part of any control
system. If that stops being true (the Pi writing to a PLC, for instance), every
"none" in the table above has to be re-evaluated.

### 13.4 What does not belong on the edge

| Not this | Why | Instead |
|---------|-----|---------|
| Long-lived static AWS credentials | physical access carries them off | IoT Core certificate auth, SORACOM Beam AssumeRole |
| Plaintext ONTAP admin credentials | a route into the management plane | a read-only custom role (§6.1) |
| SSH open to the internet | brute force and vulnerability surface | specific IPs inside the management VLAN only (§4.2) |
| A world-writable buffer path | another user on the host can pre-create or symlink it | under `~/.local/state/`; set `KAFKA_BUFFER_PATH` explicitly |

### 13.5 Not covered, and not verified

- **NFS encryption**: the PoC substitutes NFSv4.1 on a dedicated VLAN. Kerberos is
  required where the link is shared (§5, §12).
- **Direct OT protocol collection**: reading Modbus or OPC-UA directly is not
  implemented in this repository. If it is added, OT protocols generally carry no
  authentication, so whichever segment the collection point sits in becomes the
  privilege boundary.
- **IEC 62443 / NIST SP 800-82 conformance**: not assessed. Connecting to
  regulated equipment is outside the scope of this document.

## 14. Private connectivity and endpoints

Configurations that keep traffic to AWS services off the internet. This extends the network
separation in §4 into the cloud side.

| Configuration | What it solves | Note |
|---------------|----------------|------|
| Gateway VPC endpoint | Keeps S3 traffic inside the VPC, at no additional charge | Per route table. Not directly usable from on-premises |
| Interface VPC endpoint | Keeps traffic to Bedrock, Secrets Manager and others inside the VPC | Creates an ENI per AZ, with hourly and data processing charges |
| AWS PrivateLink | The mechanism underneath, also used for VPC-to-VPC and cross-account connectivity | An endpoint policy can bound what is reachable |
| Connectivity from on-premises | Reach the VPC's endpoints over Direct Connect or VPN | DNS resolution has to be designed on the on-premises side |

**Order of decision**: ask first whether each flow needs the internet at all, and move the ones that
do not onto endpoints. Closing everything at once makes it hard to isolate which flow broke.

### Network origin of an S3 access point

An S3 access point has a network origin setting and can be configured to accept requests only from a
VPC ([source](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/accessing-data-via-s3-access-points.html)).
For access points attached to an FSx for ONTAP volume, block public access is enforced by default and
cannot be disabled.

**There is a conflict, though.** Using Athena requires the access point to have an **internet**
network origin
([source](https://docs.aws.amazon.com/fsx/latest/ONTAPGuide/tutorial-query-data-with-athena.html)).
Where the analytics path and a private-only requirement collide, one has to take precedence.

### Endpoint policies

A VPC endpoint can carry a policy. Separately from restrictions on the IAM role, it enforces "from
this network, only these resources are reachable". S3 access point authorization already has two
layers, IAM and file system permissions
([S3 AP compatibility and constraints](s3ap-compatibility-matrix.md)); an endpoint policy sits in
front of both as a third.

---

## 15. Data lake permissions and the catalog

Analytics permissions tend to be maintained in two places, the catalog and the data. Maintaining both
is how one of them ends up stale.

| Layer | What it controls |
|---|---|
| Glue Data Catalog | Visibility of tables and columns |
| Lake Formation | Permissions at table, column and row level |
| S3 / file storage | Access to the actual data |

**Lake Formation table permissions have been extended to cover access to the underlying S3 data**
([source](https://aws.amazon.com/about-aws/whats-new/2026/06/aws-lake-formation-access-data-amazon-s3/)),
which reduces the need to maintain the catalog-side and data-side grants separately.

**Where this repository stands**: the Glue crawler and Athena queries exist
([`usecases/ontap-telemetry-analytics/`](../../usecases/ontap-telemetry-analytics/)), but Lake
Formation permission management is **not in place**. Everything is written assuming a single account
and a single user. Multi-team use starts with designing this.

---

## 16. Threat detection and control visibility

| Service | Role | State in this repository |
|---|---|---|
| GuardDuty | Detecting anomalous behaviour inside the account | Recommended to enable (§12 checklist) |
| Security Hub | Aggregating findings and compliance state across security services | Not in place |
| CloudTrail | Recording API calls | Assumed enabled (§17) |

**What Security Hub is for** is collecting findings that individual services produce into one place.
When results from GuardDuty, Inspector and Config are scattered, there is no basis for prioritising a
response.

**Specific to IoT**: anomalous device behaviour — publishing to an unexpected topic, a sudden jump in
message volume — is not visible to account-level threat detection. Device-side monitoring is a
separate design, and is not implemented here.

---

## 17. Data residency and auditability

### 17.1 Data residency

**Where data sits and where it is processed is not settled by Region choice alone.** A generative AI
call hands data to wherever the model runs.

| Strength of requirement | Options | Note |
|---|---|---|
| Keep it within a Region | Use only services and models available in that Region | Model availability differs by Region; confirm the model you intend to use can be enabled there first |
| Keep it within a country or bloc | A Region in that geography, or an independently operated partition | The set of available services can differ from an ordinary Region |
| It cannot leave the site | Complete processing at the edge ([Pattern 09](aws-patterns/09-edge-agentic-ai.md)), or a hybrid configuration | Verify first that edge-side model capability suffices |

For retrieval-augmented generation under data residency requirements, AWS
[publishes a worked configuration](https://aws.amazon.com/blogs/machine-learning/implement-rag-while-meeting-data-residency-requirements-using-aws-hybrid-and-edge-services/).
Where stricter isolation is required, an independently operated partition is also an option
([European digital sovereignty](https://aws.amazon.com/compliance/europe-digital-sovereignty/)).

> **This section offers no legal judgement.** Which requirements apply to your organisation, and
> which configuration satisfies them, belongs to legal and compliance functions. What is organised
> here is the technical options and what changes with each.

### 17.2 Auditability

Being able to reconstruct who did what to which data and when. In this architecture the records are
spread across four places.

| Record | What it shows | How to think about retention |
|---|---|---|
| CloudTrail | AWS API calls | Long retention, including tamper protection |
| S3 / file storage access logs | Which data was read | High volume; bound to what is needed |
| ONTAP audit logs | File system level operations | Keep timestamps correlatable with the cloud-side logs |
| AI invocation records | Which model returned what for which input | Needed to explain a verdict. [Agentic AI on AWS](agentic-ai-on-aws.md) §6 |

**A consequence of two-layer authorization**: access through an S3 access point passes both IAM and
file system permissions. Looking only at the IAM-side log, a request denied by the file system can
appear to have been allowed. The design has to correlate both.

**Additional requirement when an agent is involved**: for a process that chooses several steps
itself, not only the final output but what it consulted and called along the way has to be retained.
The list is in [Agentic AI on AWS](agentic-ai-on-aws.md) §6.

### 17.3 Not addressed in this section

- **Lake Formation adoption**: not done (§15)
- **Security Hub adoption**: not done (§16)
- **Device-side behaviour monitoring**: not implemented (§16)
- **Log correlation**: no mechanism designed for correlating the four record sources
- **Basis for retention periods**: the reason each retention period was chosen is not recorded

---

## Related Documents

- [Quality gates](../agent/quality-gates_en.md) — the gates that verify this design
- [Operations design](operations-design.md)
- [Data schema design](data-schema-design.md)
- [IoT Greengrass / FlexCache integration](iot-greengrass-flexcache-integration.md)
