# AGENTS.md

> Edge-to-cloud data collection, analytics, and AI pipelines from Raspberry Pi and SORACOM to AWS services

This file is read on every turn and cannot be made conditional, so it holds only
what applies to every turn. Work-specific material lives in `docs/agent/` and is
indexed below; `scripts/check_agent_context_budget.py` fails if it creeps back.

## Project Overview

Reference architectures connecting IoT/edge devices (Raspberry Pi, SORACOM
cellular gateways) to AWS analytics and AI services (Athena, Glue, SageMaker,
Bedrock, Rekognition), with FSx for ONTAP as the storage layer.

## Build & Test Commands

The Makefile owns the path inventory; CI calls these same targets.

```bash
make dev-install   # pinned tooling into .venv (first run)
make check         # lint + security + test + drift — what CI runs
make help          # every target
```

Do not invoke `ruff`, `bandit`, `cfn-lint` or `pytest` directly: bare commands
resolve to whatever is on PATH, which is not what CI installs.

## Coding Conventions

- Python 3.12 for edge scripts and Lambda functions (the Lambda runtime; note
  `.venv` may be newer — see `make tool-versions`)
- TypeScript for CDK constructs
- Structured JSON logging
- Type hints required for all Python functions

## Always applies

**Naming.** First mention **Amazon FSx for NetApp ONTAP**, then **FSx for
ONTAP**. Never `FSxN`, bare `FSx`, or `FSx ONTAP`. Access points are **FSx for
ONTAP S3 AP**. Do not propose NetApp Workload Factory, NetApp Console or BlueXP;
use the native equivalent (CloudWatch, ONTAP REST API, FabricPool, AWS DataSync,
Snapshot/FlexClone/SnapMirror). Verbatim external citation titles are the only
exception, marked `allow:naming` on that line.

**Vendor neutrality.** Present options, not rankings. State trade-offs
symmetrically, including those of the recommended option.

**Public-output safety.** Never commit personal or persona names, email
addresses, AWS account IDs, internal IPs or hostnames, support case numbers, or
vendor-internal ticket IDs. Use role-based references ("Storage Specialist lens")
and "an internal product request (tracked)". Keep review-process metadata
(round counts, review dates, lens counts) out of published docs.

**Untrusted input.** A device ID, MQTT topic level or S3 key that arrives in an
event is publisher-controlled. Validate it before it reaches a path, a key or a
SQL statement — see `cloud/iot_ingestion/identifiers.py`.

**Bilingual docs.** `docs/ja/` is primary, `docs/en/` mirrors it. Matching
`## ` structure and count; both change in the same commit.

## Index — read these when the work calls for it

| Read when | Document |
|---|---|
| Adding or changing a quality gate; a CI failure you do not recognise | [docs/agent/quality-gates.md](docs/agent/quality-gates.md) |
| Editing a GitHub Actions workflow; adding a dependency | [docs/agent/supply-chain-security.md](docs/agent/supply-chain-security.md) |
| Writing or revising a reference doc or guide | [docs/agent/reference-doc-quality.md](docs/agent/reference-doc-quality.md) |
| Anything touching network boundaries, device identity or plant equipment | [docs/ja/security-design.md](docs/ja/security-design.md) |
| Running or extending the test suites | [TESTING.md](TESTING.md) |
