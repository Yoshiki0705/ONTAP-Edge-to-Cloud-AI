# Security Design

> Created: 2026-05-29  
> Scope: PoC #1 (3D Print Quality Monitoring) / PoC #2 (ONTAP Telemetry)  
> Status: Draft

---

## 1. Design Principles

| Principle | Rationale |
|-----------|-----------|
| Least Privilege | Each component holds only minimum required permissions |
| Device auth via NFS/Kerberos + certificates | ONTAP NFS v4.1 Kerberos authentication as primary path; SIM-based auth for cellular connectivity |
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
