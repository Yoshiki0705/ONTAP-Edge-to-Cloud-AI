# Prompt Test Results

> Tested: 2026-05-29
> Model: jp.anthropic.claude-sonnet-4-5-20250929-v1:0 (Bedrock, ap-northeast-1)
> Screening: jp.anthropic.claude-haiku-4-5-20251001-v1:0
> Iterations: 1 per image (n=4 for the latency and cost figures), sequential, concurrency 1
> Timing: measured on the client, not inside an AWS Lambda function in a VPC
> Cost: calculated from published model prices — `handler.py` does not capture token usage,
> so these are not billed amounts and do not come from an API response

This is a sample run, not a production estimate. The evidence tier of each figure below,
and what has deliberately not been measured, are recorded in
[verification status](../../docs/en/verification-status.md).

**Round 1 and Round 2 test different things and their scores are not additive.** Round 1
feeds the model a written description of a symptom; no image is involved, so it does not
measure visual accuracy. Round 2 feeds real photographs. Reporting a combined "9/9" would
present the two as one visual-accuracy result.

## Summary

### Text-Based Scenario Test (Round 1)

**Accuracy: 5/5 (100%)**

| Test Case | Expected | Result | Confidence | Score | Severity |
|-----------|----------|--------|-----------|-------|----------|
| Normal print | normal | ✅ normal | 0.95 | 95/100 | — |
| Severe stringing | anomaly | ✅ anomaly | 0.95 | 45/100 | high |
| Layer shift | anomaly | ✅ anomaly | 0.98 | 15/100 | critical |
| Spaghetti failure | anomaly | ✅ anomaly | 0.98 | 0/100 | critical |
| Minor cosmetic (should NOT flag) | normal | ✅ normal | 0.92 | 88/100 | low (logged only) |

### Real Image Test (Round 2) — Two-Stage Analysis

**Accuracy: 4/4 (100%) — All defects correctly detected by both stages**

| Image | Source | Stage 1 (Haiku) | Stage 2 (Sonnet) | Score |
|-------|--------|----------------|-----------------|-------|
| real_stringing.png | Bambu Lab Wiki | ✅ has_defect=True (0.95) | ✅ anomaly: stringing (high) | 45/100 |
| real_delamination.png | Bambu Lab Wiki | ✅ has_defect=True (0.85) | ✅ anomaly: delamination (medium) | 45/100 |
| real_stringing_prusa.jpg | Prusa Help | ✅ has_defect=True (0.85) | ✅ anomaly: stringing (high) | 35/100 |
| real_stringing_detail.jpg | Prusa Help | ✅ has_defect=True (0.85) | ✅ anomaly: stringing (high) | 62/100 |

> The per-image cost column that used to sit here — $0.005 to $0.011 — was withdrawn. It was
> hand-calculated from list prices, not observed: this run recorded no token counts, because
> the handler discarded them. Sitting between measured verdicts and measured latencies, it
> read as measured. The formula is in [the cost model](../../docs/ja/cost-model.md), and
> `InputTokens` / `OutputTokens` now make the counts available to put into it.

### Two-Stage Analysis Validation

| Metric | Result |
|--------|--------|
| Stage 1 (Haiku) correctly flagged all defects | ✅ 4/4 |
| Stage 1 would have skipped Stage 2 for any defect | ❌ 0/4 (correct — all should proceed) |
| Stage 2 provided actionable recommendations | ✅ 4/4 |
| Average Haiku latency | 1,417ms |
| Average Sonnet latency | 7,186ms |

## Key Findings

1. **Two-stage works correctly**: Haiku reliably flags defects (confidence 0.85-0.95), triggering Sonnet for detail
2. **Real images produce richer analysis**: Multiple defect types detected per image (stringing + under-extrusion)
3. **Actionable recommendations**: "Increase retraction distance", "Reduce nozzle temperature" — specific and useful
4. **Latency acceptable**: Haiku ~1.4s + Sonnet ~7.2s = ~8.6s total (well within 60s interval)

## Cost Projection (Real Images)

The monthly figures that used to be here were withdrawn. They rested on a per-image cost this
run did not measure, and at the same 10% defect rate they gave $75/month while the rest of the
repository said $40/month — two answers from one assumption. What survives is the shape of the
calculation, which does not depend on a rate:

| Scenario | Calls per day |
|----------|---------------|
| All images have defects (worst case) | 1440 screening + 1440 detail |
| 10% defect rate (typical) | 1440 screening + 144 detail |
| 5% defect rate (good printer) | 1440 screening + 72 detail |

At 60-second intervals, 1440 captures a day. Multiply each stage's call count by that stage's
per-call cost and sum; [the cost model](../../docs/ja/cost-model.md) has the formula, the
pricing date and the current rates. A well-tuned printer typically sits at a 2-5% defect rate,
which is the left end of this table.

## Files

- `synthetic_*.jpg` - Generated patterns (OpenCV) — Claude correctly identified as non-real
- `real_stringing.png` - Bambu Lab Wiki: stringing comparison image
- `real_delamination.png` - Bambu Lab Wiki: layer cracking/delamination
- `real_stringing_prusa.jpg` - Prusa Help: stringing thumbnail
- `real_stringing_detail.jpg` - Prusa Help: stringing close-up
