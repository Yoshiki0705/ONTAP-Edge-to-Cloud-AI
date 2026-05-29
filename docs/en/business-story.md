# Business Story: Edge-to-Cloud AI

> "Turn existing enterprise data into business value with IoT and AI"

---

## Why Now (Timing Inevitability)

Three technical conditions converged in 2024-2025, making this architecture feasible for the first time:

| Timing | Event | Impact on This Project |
|--------|-------|----------------------|
| July 2024 | SORACOM Flux GA | Low-code camera × GenAI pipeline became possible |
| Feb 2025 | FSx for ONTAP S3 Access Points GA | Connect existing NAS data to AI/analytics without copying |
| 2024-2025 | Claude Vision / Multimodal AI maturation | Industrial image judgment reached practical accuracy with generic prompts |

**What wasn't possible 1 year ago:**
- Without Flux, camera→AI pipeline required weeks of development
- Without S3 AP, ETL to copy ONTAP data to S3 was required
- Without mature Vision AI, custom model training needed months and large labeled datasets

**Why now**: PoC runs in 1-2 weeks, leverages existing data assets, and applies to new inspection targets with just a prompt change.

---

## Elevator Pitch (30 seconds)

> Factory and site ONTAP NAS systems accumulate inspection images, equipment logs, and sensor CSVs daily.
> However, most of this data is "just stored" without being utilized.
>
> This architecture collects field data via Raspberry Pi + SORACOM edge devices
> and connects directly to AWS AI/analytics services (Bedrock, SageMaker, Athena).
> ONTAP's SnapMirror and S3 Access Points enable AI analysis without data copying.
>
> Result: Automated inspection, predictive maintenance, reduced operational costs.

---

## One-Page Diagram: Value Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Business Value                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │ Quality  │  │ Cost     │  │Predictive│  │ Data     │             │
│  │ Improve  │  │ Reduction│  │ Maint.   │  │ Utiliz.  │             │
│  │ Auto-    │  │ Labor    │  │ Zero     │  │ Unlock   │             │
│  │ inspect  │  │ savings  │  │ downtime │  │ dormant  │             │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘             │
├─────────────────────────────────────────────────────────────────────┤
│                        AI / Analytics Layer                         │
│  Bedrock (Image AI)  │  SageMaker (Prediction)  │  Athena (SQL)     │
├─────────────────────────────────────────────────────────────────────┤
│                        Data Integration Layer                       │
│  FSx for ONTAP ←── S3 Access Points ──→ AWS AI/Analytics Services   │
│       ↑ SnapMirror                                                  │
├─────────────────────────────────────────────────────────────────────┤
│                        Edge / IoT Layer                             │
│  Raspberry Pi + SORACOM  │  Camera  │  Sensors  │  ONTAP REST API   │
├─────────────────────────────────────────────────────────────────────┤
│                        Field Data Sources                           │
│  Inspection imgs  │  Equipment logs  │  Sensor CSV  │  Telemetry    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Why 3D Printer Monitoring as the Demo

3D printer monitoring is the **entry point**, not the real value.

| Aspect | 3D Printer Monitoring (Demo) | Real Value (Generic Pattern) |
|--------|------------------------------|------------------------------|
| Target | 1 printer | Entire factory equipment/inspection |
| Data | Camera images | Images + sensors + logs + files |
| AI | Defect detection | Predictive maintenance + quality prediction + report generation |
| Storage | S3 only | ONTAP (existing NAS) + FSxN + S3 |
| Scale | 1 device | Tens to hundreds of devices |
| Customer | Maker/individual | Manufacturing/logistics/building management |

**Why we chose 3D printer monitoring:**
1. Visually compelling (great for demos)
2. Minimal hardware (Pi + camera + printer)
3. Failures happen frequently (test data accumulates naturally)
4. Microcosm of all patterns (image AI + event-driven + data accumulation)

---

## Target Customers and Challenges

### Customer Segments

| Segment | Challenge | Value of This Architecture |
|---------|-----------|---------------------------|
| **Manufacturing (existing ONTAP customers)** | Inspection images on NAS are unused | SnapMirror + S3 AP enables AI analysis without data movement |
| **Logistics & Warehousing** | Visual inspection requires manual labor | Camera + Bedrock for automation |
| **Building Management** | Equipment failures are reactive | Sensors + SageMaker for predictive maintenance |
| **Agriculture** | Field condition monitoring is manual | Fixed cameras + AI for automated monitoring |

### Value Proposition for Existing ONTAP Customers

> "Leverage your existing ONTAP data with AI — without copying it"

1. **No data movement**: S3 Access Points provide direct S3 API access to existing NFS/SMB data
2. **No workflow changes**: Field operations (NFS writes) remain unchanged
3. **Incremental adoption**: Start with telemetry collection, expand to image AI, predictive maintenance
4. **Data protection**: SnapMirror + ARP/AI for safe cloud integration

---

## Competitive Differentiation

| Comparison | This Architecture | Pure AWS IoT | Other IoT Platforms |
|-----------|-------------------|-------------|---------------------|
| Existing NAS data | ✅ ONTAP S3 AP direct | ❌ Copy to S3 required | ❌ Proprietary storage |
| Edge→Cloud comms | SORACOM (SIM auth, private network) | IoT Core (certificate mgmt) | Proprietary protocol |
| AI analysis | Bedrock (latest models, pay-per-use) | Same | Proprietary AI or limited models |
| Data protection | ONTAP Snapshot + ARP/AI | S3 Versioning | Vendor-dependent |
| Operating cost | ~$40-55/month (PoC) | Comparable | Higher fixed monthly fees |
| Scalability | ✅ Same architecture for multiple use cases | ✅ | △ Vendor lock-in |

---

## Business Success Metrics (Not Just Technical)

| Metric | Measurement | PoC Target | Production Target |
|--------|-------------|-----------|------------------|
| Inspection labor reduction | (current - post-implementation) / current | Confirm feasibility | 50% reduction |
| Early defect detection rate | AI-detected / total defects | ≥ 70% | ≥ 90% |
| Unattended operation time | Continuous operation without human intervention | 8 hours/day | 24 hours/day |
| Material waste reduction | Material saved by early failure detection and stop | Start measurement | 30% reduction |
| Unplanned downtime count | Monthly unexpected equipment stops | Baseline measurement | 50% reduction |

> **Important**: Technical metrics (accuracy 80%, latency 60s) are means. Business metrics are the real success criteria.

---

## AI Judgment Positioning (Governance)

| Item | Definition |
|------|-----------|
| **AI output nature** | Assistive signal. Not a final decision |
| **Automatic actions** | Auto-stop only for severity: high/critical. All others require human judgment |
| **Responsibility scope** | AI notifies "suspicious." Final stop/continue decision is the operator's |
| **False positive impact** | Print pause (resumable). No irreversible damage by design |
| **False negative impact** | Filament waste, print time loss. No safety hazard |

### Safe Experimentation Boundaries

| Allowed | Not Allowed |
|---------|-------------|
| Ignore AI alerts and continue printing | Make expensive material disposal decisions based solely on AI |
| Adjust thresholds to tune accuracy | Disable safety mechanisms (temperature limiters) via AI |
| Try new prompts | Use untested prompts in customer production environments |
| Change capture intervals | Install cameras where individuals may be captured |

---

## ROI Estimate (Manufacturing Example)

### Assumptions

- Inspection process: 1 line, 1 visual inspector (annual salary ¥5M)
- Inspection frequency: 1/minute, 8 hours/day, 250 days/year
- Defect rate: 2%, loss per defective item: ¥5,000

### Cost Comparison

| Item | Current (Visual Inspection) | After Implementation |
|------|---------------------------|---------------------|
| Labor | ¥5,000,000/year | ¥2,500,000/year (50% reduction: inspector→supervisor) |
| Defect losses | ¥6,000,000/year | ¥3,000,000/year (50% reduction: early detection) |
| System cost | ¥0 | ¥600,000/year (AWS + SORACOM + hardware) |
| **Total** | **¥11,000,000/year** | **¥6,100,000/year** |
| **Savings** | — | **¥4,900,000/year** |

> **Note**: Above is an estimate based on assumptions. Actual ROI varies significantly by site conditions. Pre-implementation site assessment is required.

---

## Engagement Approach

```
Step 1: Demo (1 day)
  Show live 3D printer monitoring demo
  → "This can be applied to your inspection processes"

Step 2: Assessment (1-2 weeks)
  Site visit: data sources, network, existing ONTAP environment
  → Agree on PoC scope

Step 3: PoC (4 weeks)
  Small-scale validation with customer's real data/environment
  → Go/No-Go decision

Step 4: Pilot (2-3 months)
  Production operation on 1 line/1 site
  → Measure effectiveness, plan scale-out

Step 5: Production Rollout
  Deploy to all lines/sites
  → Continuous improvement
```
