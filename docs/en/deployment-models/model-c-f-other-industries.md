> 🌐 Language: [日本語](../../ja/deployment-models/model-c-f-other-industries.md) | **English**

# Models C–F: differences in other industries

> Last verified: 2026-08-19

What changes in retail, healthcare, telecom and energy relative to
[Model A](model-a-single-factory.md) and [Model B](model-b-multi-factory.md), and nothing more.

## What this document is

**This repository has no implementation, no measurements and no industry-specific primary sources for
these sectors.** What follows organises which decisions change when a design written for
manufacturing is applied elsewhere.

Each sector is not written to the depth of A and B. Doing so would mean matching length without
having the material.

> **No legal judgement is offered on regulation or compliance.** Which regulations apply, and which
> configuration satisfies them, belongs to legal and compliance functions. What is listed here is
> which questions have to be brought in.

## Four axes

Four axes carry most of the difference from A and B. Thinking in these axes transfers better than
per-sector detail.

| Axis | What changes |
|---|---|
| Regulatory requirements | Which regulations apply, what records are required, whether third-party audit is involved |
| Data residency | Where data may sit, and where it may be processed |
| Latency requirement | How quickly a decision has to arrive to be useful |
| Cost structure | The ratio of fixed to usage cost, and the order of magnitude of site count |

---

## Model C: retail edge

| Axis | Difference from A and B |
|---|---|
| Regulatory requirements | A requirement to separate payment-related systems from everything else appears. Because shoppers appear in camera footage, questions about handling video are added |
| Data residency | A requirement to complete processing inside the store is common — video does not leave |
| Latency requirement | Mostly minutes suffice, for example shelf gap detection. Payment integration is a separate system |
| Cost structure | **Site count differs by an order of magnitude.** At hundreds to thousands of stores, per-site fixed cost dominates |

**Design consequence**: at high site counts, the "fixed cost per site" structure from
[Model B](model-b-multi-factory.md) bites. Assuming edge storage in every store becomes hard to
sustain, and the weight shifts towards completing work on the device, as in
[Pattern 09](../aws-patterns/09-edge-agentic-ai.md).

**Questions to bring in**: handling footage containing people (the security section of
[Pattern 06](../aws-patterns/06-video-analytics.md)). Separation from payment systems. Store network
bandwidth.

**Unimplemented**: there is no retail use case in this repository.

---

## Model D: healthcare edge

| Axis | Difference from A and B |
|---|---|
| Regulatory requirements | Regulation on handling patient information applies. Retention periods and audit requirements tend to be stricter than in manufacturing |
| Data residency | Requirements to keep data inside the facility or the country are common. Which Region a generative AI call runs in becomes a question |
| Latency requirement | Diagnostic support can require immediacy. Batch analysis is a separate system |
| Cost structure | Moderate site count. Audit and log retention cost more than in A and B |

**Design consequence**: where residency requirements are strong, the options in
[security design §17](../security-design.md) narrow to completing processing at the edge or a hybrid
configuration. AWS publishes
[a worked configuration for retrieval-augmented generation under data residency requirements](https://aws.amazon.com/blogs/machine-learning/implement-rag-while-meeting-data-residency-requirements-using-aws-hybrid-and-edge-services/).

**Questions to bring in**: determining whether patient information is present. The role of human
confirmation where AI output informs diagnosis. Audit log retention and tamper protection.

**Unimplemented**: there is no healthcare use case in this repository.
**Conformance to regulation has not been assessed.**

---

## Model E: telecommunications edge

| Axis | Difference from A and B |
|---|---|
| Regulatory requirements | Requirements on confidentiality of communications. Reporting obligations on equipment operation may apply |
| Data residency | Equipment is geographically distributed, spanning several areas even within one country |
| Latency requirement | **This is the largest difference.** Equipment anomaly detection can require milliseconds to seconds |
| Cost structure | Many sites with expensive equipment at each. Telemetry volume is an order of magnitude larger |

**Design consequence**: tight latency makes sending the decision to the cloud hard to sustain. The
escalation thinking in [Pattern 09](../aws-patterns/09-edge-agentic-ai.md) becomes central, with the
cloud handling training and cross-site analysis. Because telemetry volume is large, the cardinality
estimate in [Pattern 07](../aws-patterns/07-digital-twin.md) directly decides the design.

**Questions to bring in**: the cardinality ceiling of the time-series database. Sampling interval for
equipment telemetry. Aggregation at the edge, meaning not sending everything.

**Unimplemented**: there is no telecom equipment use case in this repository.

---

## Model F: energy and utilities

| Axis | Difference from A and B |
|---|---|
| Regulatory requirements | Critical infrastructure requirements. Regulation on connecting to control systems applies |
| Data residency | Requirements to stay within a country or bloc are strong |
| Latency requirement | Immediate for anything control-related; minutes suffice for monitoring and analysis |
| Cost structure | Few to moderate site count. Equipment is long-lived, so connecting to existing machinery is the main work |

**Design consequence**: **the boundary with control systems matters most.** The OT/IT principles in
[security design §13](../security-design.md) — keeping data flow one-directional, not widening a
failure into the OT side — become requirements rather than preferences in this model. With much
existing equipment, starting from the namespace design in
[Pattern 08](../aws-patterns/08-unified-namespace.md) is worth more here.

**Questions to bring in**: whether writing back to control systems belongs in the design at all — not
including it is the default. Which segment holds the collection point for OT protocols. Data
residency requirements.

**Unimplemented**: there is no energy or utilities use case in this repository.
**Conformance to critical infrastructure regulation has not been assessed.**

---

## Summary: which axis dominates

| Model | Dominant axis | Patterns to consult |
|---|---|---|
| C retail | Cost structure (order of magnitude of sites) | [09](../aws-patterns/09-edge-agentic-ai.md), [06](../aws-patterns/06-video-analytics.md) |
| D healthcare | Data residency | [05](../aws-patterns/05-agentic-rag.md), [09](../aws-patterns/09-edge-agentic-ai.md) |
| E telecom | Latency requirement | [07](../aws-patterns/07-digital-twin.md), [09](../aws-patterns/09-edge-agentic-ai.md) |
| F energy | Regulatory requirements (OT boundary) | [08](../aws-patterns/08-unified-namespace.md), [03](../aws-patterns/03-industrial-iot-analytics.md) |

**[Pattern 09](../aws-patterns/09-edge-agentic-ai.md) appears in all four.** For a common reason: one
of "the data cannot leave", "latency is not sufficient", or "site count makes cloud round trips
uneconomic" presents more strongly than it does in manufacturing.

## Unverified and unimplemented

| Item | State |
|---|---|
| Use case implementations for the four sectors | None |
| Assessment of conformance to sector-specific regulation | Not done |
| Measurement of per-sector latency requirements | Not done |
| Verifying the cost structure at high site counts | Not done |

## References

- [Model A: single factory](model-a-single-factory.md) / [Model B: multiple factories](model-b-multi-factory.md)
- [Security design §17: data residency and auditability](../security-design.md)
- [Pattern catalog](../aws-patterns/README.md)
