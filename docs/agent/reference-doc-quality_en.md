# Reference-Doc / Guide Quality Bar

> Read when writing or revising a technical reference or guide. Does not apply to
> conversation or short answers.
>
> 日本語: [reference-doc-quality.md](reference-doc-quality.md)

## Required elements

| Element | Purpose |
|---|---|
| Conclusion in the executive summary | the reader can decide within the first ten lines |
| FAQ / common misconceptions | recovers the assumptions nobody read |
| Selection flowchart (mermaid is fine) | separates "which one" from the prose |
| OT/IT security considerations (where applicable) | mandatory for docs touching plant or field equipment |
| Phased adoption steps | the order from PoC to production |
| Related Documents (back-links) | reachability; an unlinked doc is an unread doc |

## JA/EN parity

`docs/ja/` and `docs/en/` keep the same `## ` heading structure and count. A
change to one lands in both in the same commit.
`.github/workflows/agent-output-audit.yml` warns on a heading-count difference.

## Naming

- First mention **Amazon FSx for NetApp ONTAP**, then **FSx for ONTAP**
- Access points are **FSx for ONTAP S3 AP**
- Never `FSxN`, bare `FSx`, or `FSx ONTAP`
- The only exception is a verbatim external citation title; mark that line `allow:naming`

## Writing comparisons

Present options, not rankings. State trade-offs symmetrically, including the
recommended option's own constraints. `最強`, `game-changer`, `競合ツール`,
`優位性`, `より優れ`, `is better than`, `is superior to` are hard-failed by
`agent-output-audit.yml`.

## Never publish

Personal or persona names, email addresses, AWS account IDs, internal IPs and
hostnames, support case numbers, vendor-internal ticket IDs. Use role-based
references (`Storage Specialist lens`) and "an internal product request
(tracked)".

Keep review-process metadata out of published docs (round counts, review dates,
lens counts). It is noise for readers; provenance belongs in `.private/`
(gitignored).

## Numbers and confidence

- Publish a performance or cost number with its environment (version, region,
  configuration, measurement date)
- Separate "sample run" from "production estimate"
- Write "not verified" where that is the case, rather than filling in a plausible
  default

## Before committing

```bash
make secrets
# CI mirrors these checks: .github/workflows/agent-output-audit.yml
```

## Related documents

- [Quality gates](quality-gates_en.md)
- [Supply-chain security](supply-chain-security_en.md)
