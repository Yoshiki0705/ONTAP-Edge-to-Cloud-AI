> 🌐 Language: [日本語](../../ja/deployment-models/README.md) | **English**

# Deployment models

> Last verified: 2026-08-19

The same pattern takes a different shape depending on scale and industry. This is where those
differences live.

If the [pattern catalog](../aws-patterns/README.md) answers "what to build", these answer "where and
at what scale to put it".

## The models

| Model | Subject | Depth |
|---|---|---|
| [Model A: single factory](model-a-single-factory.md) | One site, a handful to a few dozen devices | Data flow / storage / AI / security controls / what drives cost |
| [Model B: multiple factories](model-b-multi-factory.md) | Several sites, aggregation across them | Same |
| [Models C–F: differences in other industries](model-c-f-other-industries.md) | Retail / healthcare / telecom / energy | Only the differences from A and B |

## Why the depth differs

**A and B are detailed; C–F cover only differences.** The implementation and verification in this
repository target manufacturing use cases
([3D print quality monitoring](../../../usecases/3d-print-quality/),
[visual inspection](../../../usecases/visual-inspection/)). For other industries there is neither an
implementation, nor measurements, nor industry-specific primary sources.

Detailing four industries equally would mean matching length without having the material. That is
what a public reference should avoid. C–F therefore narrow to what changes relative to A and B —
regulatory requirements, data residency, latency requirements, cost structure — and state that they
are unimplemented.

## How to choose

| Situation | Model to read |
|---|---|
| Starting at one site | [A](model-a-single-factory.md) |
| Several sites already, wanting a cross-site view | [B](model-b-multi-factory.md) |
| One site now, more later | Read [A](model-a-single-factory.md), then "moving from A to B" in [B](model-b-multi-factory.md) |
| An industry other than manufacturing | Check the differences in [C–F](model-c-f-other-industries.md), then return to A or B |

**The most expensive part of moving from A to B is adding a way to identify a site afterwards.** Even
starting with one site, putting a site identifier into the event schema and the storage paths from
the beginning reduces the rewriting later.

## Assumptions that cut across

- **Choosing the pattern is separate**: which AI path to use is in the
  [pattern catalog](../aws-patterns/README.md)
- **Security control detail**: [security design](../security-design.md). Each model states only what
  changes for that model
- **Figures**: [deployment guide](../deployment-guide.md). Each model names only the cost drivers
- **These are not measurements**: hardware testing in this repository is incomplete
  ([README](../../../README_en.md#about-this-repository)). No performance or cost numbers appear here

## Unimplemented

| Item | Models affected |
|---|---|
| Running multiple sites in production | B |
| Verifying data sync across sites | B |
| Assessing conformance to industry-specific regulation | C–F |
| Provisioning a large device fleet | A, B |
