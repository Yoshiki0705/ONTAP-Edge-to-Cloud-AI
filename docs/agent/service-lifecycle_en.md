# Service availability

> Read when naming an AWS service in a design, or when correcting an existing mention.
>
> 日本語: [service-lifecycle.md](service-lifecycle.md)

A reader builds what the reference describes. If a step names a service that is closed to new
customers, there is no path to create it in the console, and nothing in the document said so. The
failure lands on the reader, and it lands after they have started.

## Automated check

`scripts/check_sunset_services.py`, via `make drift`. Per document, it enforces "if you bring the
service up, say where it stands in the same document".

- Scope: `docs/**/*.md`, `usecases/**/*.md`, `cloud/**/*.md`, `edge/**/*.md`, and the root
  `README*.md` / `TESTING*.md` / `CONTRIBUTING.md`
- Verdict: fails when a document names a listed service and contains none of the status phrases
  (`新規顧客`, `new customers`, `提供終了`, `discontinued`, `end of support`, `in maintenance`,
  `maintenance mode`, `sunset`, `非開放`, `サポート終了`)
- The inventory lives in `SUNSET_SERVICES`, each entry carrying its status and source URL as a
  comment

Document-level rather than line-level because the same service usually appears both in prose and in
a table; a line-level rule would flag every mention except the one carrying the note.

> **Neither the placement of the note nor the suitability of the alternative can be machine-checked.**
> The gate passing does not mean the note sits where a reader will see it.

## How to write it

For any service at "closed to new customers" or beyond, do one of two things.

1. Remove the mention
2. State the status with a source and give a current alternative

State alternatives symmetrically: say which conditions favour which, without treating one as
inferior.

## Traps

- **Do not put bare `maintenance` in the marker list.** This repository uses
  `predictive maintenance` throughout. Measured: 7 of 60 documents contain the word, and with it in
  the list, a document naming a discontinued service without a note passed on the strength of
  "predictive maintenance". One of two identical defects was reported
- **Renames happen quietly, unlike end-of-support.** The documentation is rewritten without a
  what's-new entry. This gate does not detect renames
- **Nothing outside the inventory is detected.** Zero violations does not mean every service named
  in the docs is current; the inventory is a snapshot from when it was written
- **Only `.md` is walked.** Service names in template comments or docstrings are out of scope

## How to check

1. The "service changes" and "service availability" entries under
   `aws.amazon.com/about-aws/whats-new/`
2. Each service's document history page — a feature closed individually often appears only there
3. For renames, read the current title of the official documentation page

## Related documents

- [Quality gates](quality-gates_en.md)
- [Reference doc quality bar](reference-doc-quality_en.md)
