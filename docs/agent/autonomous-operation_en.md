# Long-running autonomous operation

> Read when driving a multi-step task (adding a pattern, a verification run, an IaC change)
> autonomously over a long session. The foundation is the global steering
> (`ai-agent-workflow`'s Auditor Sub-Agent section, `benchmark-and-evidence-standards`);
> this file carries only what is specific to this repository. Not always loaded.
>
> 日本語: [autonomous-operation.md](autonomous-operation.md)

## Where the decision log lives, and its shape

For a multi-step task (adding a new `usecases/` pattern, a verification run on real
hardware, an IaC change such as a `template.yaml`), keep a decision log separate from the
implementation prose. Because the log carries process metadata (rejected options, unverified
assumptions, basis tiers), it lives in this repository's private working area
`.private/tasks/<task>/` (`.private/` is gitignored, and similar ledgers already live
there). You may create one file per task (e.g. `impl-note.md`), but keep the three sections
in that single record rather than splitting them into separate files, and do not spawn
duplicate containers. The three sections:

```markdown
## Decisions
- <what was decided>: <why. basis is measurement / documentation / guess>

## Rejected alternatives
- <the option rejected>: <why. could it return if the situation changes>

## Assumptions
- <taken as given without verifying>: <what breaks if it is wrong>
```

For work involving verification, tag each `Decisions` basis with an evidence tier. The only
allowed words are `verified` / `documented` / `field-observation` / `hypothesis`. These are
the same vocabulary the ledger in `docs/{ja,en}/verification-status.md` uses, and
`scripts/check_verification_ledger.py` rejects a fifth invented tier. Keep the decision log
to the same four words; do not write a tier in the log that the ledger could not carry.

## Signals to call the auditor

When you notice any of the following, call the auditor before continuing. The definition of
the signals and how to invoke it are in `ai-agent-workflow`'s Auditor Sub-Agent section and
are not repeated here.

- The same approach has failed twice
- You have re-edited the same file three or more times
- The same error message recurs in a multi-step task

Hand the auditor the decision log and the diff, and instruct it to doubt rather than to
reinforce. Do not build an automatic hook (false firing on read-only calls outweighs the
automation). Review just before committing public output belongs to the persona review
board; keep it separate from the auditor.

## Measure the spread before claiming an effect

When measuring performance, throughput, latency, or cost, measure the run-to-run spread of
the unchanged configuration first, before attributing an effect to a change. If a change's
delta sits within that spread, it is noise, not an effect: say so, or raise the iteration
count until the effect clears the spread. A one-off "A is faster than B," each measured
once, gets the same treatment. The requirements and metadata are in
`benchmark-and-evidence-standards`.

The only measured evidence in this repository at present is the two-stage Bedrock inference
figures (recorded in `verification-status.md`, obtained with specific inference profiles).
When a change touches those numbers, do not break the link between the ledger row and the
inference profile. Changing a model ID or an inference-profile prefix such as `jp.` is a
different path and different billing, and the recorded numbers stop describing that
configuration (`check_verification_ledger.py` detects this drift).

## Checklists for recurring task types

The task types that recur in this repository have their own pitfalls. Treat a second
failure of the same kind as a sign that the checklist is missing an item, and add one item
at a time to the relevant task-type section.

### Adding a usecases pattern

Existing patterns (`usecases/3d-print-quality` and others) follow a fixed shape:
README / design.md / demo-guide.md / lambda/ / template.yaml / ontap-setup.sh. When adding
a new one:

- Add an example `*.example.json` to `cfn-params/`, and a row to the table in
  `cfn-params/README.md` (`check_cfn_params_contract.py` checks the correspondence)
- Keep the `template.yaml` environment variables, the values the handler reads, and the
  must-set declarations in `usecases/handler-map.txt` in agreement
  (`check_lambda_env_contract.py`)
- Keep README and design matched in `## ` structure and count across JA/EN, changing both
  in the same commit
- Pass `make check`. It includes lint / security / test / drift (tests alone skip the
  static checks)

### A verification run on real hardware

A script that only runs on real hardware (SSM, ONTAP REST, AD operations) passing offline
gates is not evidence that it runs on real hardware. During a verification run:

- List in the pass/fail requirements which artifacts the teardown destroys, and place an
  export step before the teardown
- Treat the claim as `hypothesis` until it has run once on real hardware
- Before incurring charges, reconcile the AWS operations each principal (instance role,
  Lambda role) calls against its permissions
- Measure the spread of the unchanged configuration first (section above)

### A change that assumes an AWS API call

- Do not write region availability, quotas, pricing, or model IDs from memory; confirm
  before the call
- "Unsupported" / "cannot" is a claim. Attach a source or a measurement, and where you
  cannot, write "not verified"
- Take the identifier for a destructive call from a saved file or a list's output, not by
  typing it by hand
