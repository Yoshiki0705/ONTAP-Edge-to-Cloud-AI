# PoC Planning Template: Edge-to-Cloud AI

> Planning template for conducting a PoC with this architecture. Customize for internal validation or customer proposals.

---

## Proposal Summary (1-Page)

| Item | Content |
|------|---------|
| **Proposal Name** | [Project] Field Data AI Utilization PoC |
| **Target Challenge** | [e.g., Manual inspection dependency, reactive equipment maintenance, dormant data] |
| **Proposal** | Collect field data via edge devices (Raspberry Pi + SORACOM), analyze with AWS AI services |
| **Duration** | 4 weeks |
| **Estimated Cost** | Hardware: ~¥150K / AWS: ~¥5,000/month / Implementation: [partner quote] |
| **Expected Outcome** | [e.g., Validate feasibility of 50% inspection labor reduction] |
| **Go/No-Go Criteria** | [e.g., AI detection accuracy ≥ 80%, false positive rate ≤ 10%] |

---

## 1. Customer Challenge Assessment

### Discovery Questions

| # | Question | Answer |
|---|----------|--------|
| 1 | What data do you want to "see" or "know" from the field? | |
| 2 | How is that data currently managed? (paper/Excel/NAS/DB) | |
| 3 | Do you have existing NetApp ONTAP / NAS infrastructure? | |
| 4 | Is there network connectivity at the site? (wired/Wi-Fi) | |
| 5 | Is power available? (AC/PoE/battery) | |
| 6 | What is the data sensitivity level? (public/internal/confidential/restricted) | |
| 7 | Current labor cost for inspection/monitoring? | |
| 8 | Cost of equipment downtime? (per hour) | |

### Application Decision Matrix

| Customer Situation | Recommended Pattern | Priority |
|-------------------|-------------------|----------|
| Images/logs accumulated on ONTAP NAS | Pattern C/D (FPolicy + SnapMirror) | High |
| Visual inspection process exists | Pattern A (Camera + AI) | High |
| Unplanned equipment downtime is a problem | Pattern B (Sensor + Prediction) | High |
| Data exists but isn't utilized | Pattern D (SnapMirror → FSxN → Athena) | Medium |
| No network at site | SORACOM cellular connectivity | Medium |

---

## 2. PoC Scope Definition

### In Scope

- [ ] 1 edge device setup and verification
- [ ] Data collection pipeline (edge → cloud)
- [ ] AI analysis accuracy validation ([target: image/sensor/log])
- [ ] Alert notification verification
- [ ] 4-week continuous operation test
- [ ] Results report and Go/No-Go decision

### Out of Scope

- Multi-device scale-out
- Production deployment
- Integration with existing systems (MES/ERP/BMS)
- SLA/SLO guarantees
- 24/7 operational support

---

## 3. Success Criteria

### Technical Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| AI detection accuracy | ≥ 80% | Calculated from feedback records |
| False positive rate | ≤ 10% | False Positive / Total Positive |
| Response time | ≤ 60 seconds | Capture → alert |
| System uptime | ≥ 95% | Calculated from health reports |

### Business Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| [e.g., Inspection labor reduction] | [e.g., Confirm 50% reduction feasibility] | Current vs PoC period comparison |
| [e.g., Early defect detection] | [e.g., 50% reduction in detection lead time] | Current lead time vs PoC |
| [e.g., Data utilization rate] | [e.g., 30% of unused data becomes queryable] | Athena-queryable data volume |

### Go/No-Go Decision Criteria

| Decision | Condition |
|----------|-----------|
| **Go** (proceed to pilot) | All technical metrics met AND business metric feasibility confirmed |
| **Conditional Go** | 80% of technical metrics met, improvement plan exists |
| **No-Go** | Below 50% of technical metrics, or fundamental constraint discovered |

---

## 4. Team and Roles

| Role | Owner | Responsibility |
|------|-------|---------------|
| **Business Sponsor** | [Customer] | Go/No-Go decision, budget approval |
| **Field Operator** | [Customer] | Installation site, operational feedback |
| **IT Administrator** | [Customer] | Network, AWS account, security approval |
| **Implementation Lead** | [Owner] | Architecture design, implementation, testing |
| **Technical Support** | [As needed] | Best practice advice |

---

## 5. Schedule

```
Week 1: Environment Preparation
  - AWS account/IAM setup
  - Edge device procurement and setup
  - Network verification, SORACOM SIM configuration
  - ONTAP connectivity check (if applicable)

Week 2: Pipeline Construction
  - Data collection script development
  - Cloud infrastructure deployment
  - AI analysis setup and prompt tuning
  - Notification configuration

Week 3: Validation Run
  - Start continuous operation
  - Accuracy verification and feedback recording
  - Issue resolution and tuning

Week 4: Evaluation and Reporting
  - Accuracy report generation
  - Cost actuals compilation
  - Go/No-Go decision meeting
  - Next phase planning (if Go)
```

---

## 6. Estimated Cost

| Item | Initial | Monthly | Notes |
|------|---------|---------|-------|
| Raspberry Pi 5 kit | ~¥15,000 | — | Pi + camera + SSD + power |
| SORACOM SIM | ~¥500 | ~¥500 | plan-D base + data |
| AWS (PoC scale) | — | ~¥5,000 | S3 + Lambda + Bedrock + Kinesis |
| Implementation | [estimate] | — | Design, build, test |
| **Total** | **~¥15,500 + impl** | **~¥5,500/month** | |

---

## 7. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| AI accuracy below target | PoC failure | Prompt improvement, model change, capture condition adjustment |
| Unstable network | Data loss | Local buffer + fallback communication |
| Insufficient field cooperation | Installation/operation stalls | Business sponsor engagement |
| Cost overrun | Budget exceeded | Budget alarm configured ($50/month) |
| Security concerns | Approval delays | Present security design document upfront |

---

## Appendix: Available Assets

| Asset | Format | Purpose |
|-------|--------|---------|
| CloudFormation template | YAML | Deploy full AWS infrastructure in 1 command |
| Edge device setup guide | Markdown | Pi initial setup playbook |
| SORACOM configuration guide | Markdown | Funnel/Flux setup steps |
| Data schema design | Markdown | Message format, S3 partition design |
| Security design | Markdown | IAM, encryption, network design |
| Operations design | Markdown | SLI/SLO, runbook, escalation |
| Bedrock prompt | Python | Tested prompt (100% accuracy) |
