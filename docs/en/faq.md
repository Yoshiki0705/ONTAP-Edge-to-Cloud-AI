# FAQ: Edge-to-Cloud AI

> Typical questions partners/SIs receive from customers, with answers

---

## Security

**Q: What happens if a device is hacked?**

A: Three layers of defense are designed. (1) No AWS credentials stored on device (SORACOM SIM auth + AssumeRole), (2) Network segmentation (no access to ONTAP management plane), (3) ONTAP ARP/AI detects abnormal write patterns and auto-creates protective Snapshots. On device compromise, SIM suspension immediately cuts communication.

**Q: Where is image data stored? Is it encrypted?**

A: Stored in S3 (SSE-KMS encryption) and ONTAP (NVE: AES-256). In-transit encryption via TLS 1.2+. S3 bucket policy denies unencrypted transport.

**Q: Could employees appear in camera images?**

A: Cameras are positioned to capture only products/equipment. If people may appear in frame, a privacy impact assessment is conducted before installation, with mitigations including capture area restriction, blur processing, or relocation.

---

## Cost

**Q: What's the monthly cost?**

A: PoC scale (1 device): ~¥5,500/month (AWS ~¥5,000 + SORACOM ~¥500). Two-stage AI analysis achieves ~85% cost reduction compared to analyzing all images with the high-accuracy model.

**Q: How does cost scale for production deployment?**

A: Proportional to device count. 10 devices: AWS ~¥30,000-50,000/month + SORACOM ~¥5,000/month + hardware initial ~¥150,000. Since only the cheap Haiku model runs during normal operation, lower anomaly rates mean better cost efficiency.

**Q: Can this integrate with existing AWS environments at no additional cost?**

A: Existing S3, CloudWatch, and IAM can be leveraged. Additional costs are only Bedrock API calls (pay-per-use) and Kinesis (ON_DEMAND: usage-based billing).

---

## Technical

**Q: Can this work without existing ONTAP / NAS?**

A: Yes. ONTAP integration is a Phase 2 option. Phase 1 runs with Pi + SORACOM + S3 + Bedrock only. When ONTAP exists, it provides additional value through existing data AI utilization and event-driven integration.

**Q: Can this work at sites without internet?**

A: SORACOM cellular SIM enables operation without wired networks. In cellular dead zones, data is buffered locally and batch-uploaded when connectivity returns. For fully offline environments, edge inference (TensorFlow Lite) provides basic detection (Phase 3+).

**Q: What's the AI accuracy?**

A: 100% in testing (9/9 test cases correct). Production accuracy varies with environmental conditions (lighting, camera position, filament color), so PoC validates real-environment accuracy. Target: ≥80% accuracy, ≤10% false positive rate.

**Q: Is this limited to 3D print inspection?**

A: No. The architecture is generic. By changing the prompt, it applies to visual inspection (scratches, discoloration, dimensions), inventory management (stocktaking), safety equipment verification (helmet detection), and any image-based judgment.

**Q: Is Raspberry Pi suitable for industrial use?**

A: Sufficient for PoC/pilot. For production, consider industrial enclosures (dust/waterproof), UPS (power protection), and industrial Pi-compatible devices (RevPi, etc.).

---

## Operations

**Q: What happens if a device fails?**

A: (1) Auto-alert if no captures for 5 minutes, (2) Remote diagnosis via SORACOM Napter, (3) If unrecoverable, swap with spare (setup guide available, 30 minutes). Printing itself continues without the Pi.

**Q: What's the impact of AI false positives?**

A: Auto-stop only for severity: high/critical (resumable). All others are notification-only with human judgment. False positive feedback is recorded and reflected in weekly accuracy improvements.

**Q: Can this integrate with existing monitoring (Nagios, Zabbix, etc.)?**

A: SNS enables notification to any endpoint. Supports Webhook, email, SMS, PagerDuty, Slack. CloudWatch metrics can also be ingested into existing monitoring systems.

---

## Implementation Process

**Q: How long does a PoC take?**

A: 4 weeks (1 week prep + 1 week build + 1 week validation + 1 week evaluation). AWS infrastructure deploys in 1 command via CloudFormation. Edge device starts operating in 1-2 hours following the setup guide.

**Q: What changes for production after PoC?**

A: Main additions: (1) Increased device count, (2) 24/7 monitoring, (3) Automated OTA updates, (4) Security hardening (VPG private network), (5) Formal SLA/SLO agreement. The architecture itself remains the same as PoC.

**Q: Can field operators without AWS knowledge manage this?**

A: Daily operations are only Slack/Teams notification review and feedback recording. No AWS console access needed. For incidents, follow the Runbook; if unresolved, escalation flow hands off to engineers.
