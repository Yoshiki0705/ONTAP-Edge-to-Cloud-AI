# Article Draft #2: A Two-Stage AI Pattern That Cuts Image-Analysis Cost by 85%

> Status: Draft
> Target: dev.to / personal blog
> Disclaimer: Personal technical exploration, not an official organizational position. Cost figures are estimates under specific conditions.

---

## TL;DR

Analyzing every image with a high-accuracy model is expensive. A two-stage design — "screen with a cheap model → analyze only suspects with a high-accuracy model" — achieved an estimated $259 → $40/month (~85% reduction). This article shares the pattern and the decision criteria.

**Disclaimer**: Cost figures are estimates under specific assumptions (capture frequency, image size, region). Actual costs vary.

---

## 1. Problem: Running Every Image Through a High-Accuracy Model Is Costly

In 3D print quality monitoring, we capture an image every 60 seconds and judge with AI. That's 1,440/day, 43,200/month.

Analyzing all of them with Claude Sonnet (high-accuracy):

```
43,200 images/month × ~$0.006/image ≈ $259/month
```

But in reality, **most images are "normal."** Anomalies occur in a few percent. Using a high-accuracy model on normal images is wasteful.

## 2. Solution: Two-Stage Analysis (Screen → Detail)

```
[Image] → [Stage 1: Screen with Haiku]
              │
              ├── "normal" → done (cheap)
              │
              └── "suspected anomaly" → [Stage 2: Detail with Sonnet]
                                            │
                                            └── final verdict + recommended action
```

- **Stage 1 (Claude Haiku)**: Cheap, fast. Binary "normal / needs review" only
- **Stage 2 (Claude Sonnet)**: High-accuracy. Outputs anomaly type, severity, recommended action

## 3. Cost Estimate

Assumption: 5% anomaly rate (95% resolved at Stage 1)

| Approach | Calculation | Monthly |
|----------|-------------|---------|
| Sonnet only | 43,200 × $0.006 | ~$259 |
| Two-stage | Haiku: 43,200 × $0.001 + Sonnet: 2,160 × $0.006 | ~$56 |

Extending the capture interval to 120s roughly halves it again. In practice it landed around **$40**.

> Note: This is an estimate. It varies with model pricing, image size, token count, and region.

## 4. Implementation Notes

### Stage 1 prompt is specialized for triage
Stage 1 doesn't need detail. Have it judge only "normal" vs "needs review," minimizing token output. When ambiguous, err on the safe side (needs review) and send to Stage 2.

### Conservative triage (Recall-first)
If Stage 1 misses an anomaly (False Negative), it never reaches Stage 2. So design Stage 1 for **Recall-first**: "when in doubt, escalate to Stage 2." Some False Positives (normal judged as needs-review) are absorbed by Stage 2.

### Only Stage 2 makes the final call
The final anomaly type, severity, and action come from Stage 2. Stage 1 is purely a cost-optimization filter.

## 5. Where This Pattern Applies

"Most inputs need only simple processing; a few need detailed processing" is a widespread pattern:

- Log anomaly detection (cheap model for normal logs, detail only for suspects)
- Document classification (coarse classify → detailed extraction)
- Content moderation (instant judgment for obvious cases, review only gray zones)
- Customer inquiry triage (cheap for templates, high-accuracy only for complex ones)

Shared decision criteria:
1. Can most inputs be handled by simple processing?
2. Can a cheap model do adequate "triage"?
3. What's the balance between miss cost (FN) and review cost (FP)?

## 6. Caveats / Trade-offs

- **Latency**: With two stages, anomaly cases take Stage 1 + Stage 2 time. Consider if real-time matters
- **Complexity of two calls**: Error handling and retries in two places
- **Stage 1 accuracy dominates**: Misses at Stage 1 never reach Stage 2. Stage 1 evaluation is critical
- **Cost estimate is condition-dependent**: In high-anomaly-rate environments, the savings shrink

## 7. Validation Status

- Prompt testing: 9/9 correct on synthetic + public images
- Real-environment accuracy (lighting, camera angle, filament color) yet to come
- Feedback loop (human correction of misjudgments) implemented; accuracy continuously measured

## Summary

Two-stage analysis is an effective cost-optimization pattern for workloads where most inputs need only simple processing. For 3D print quality monitoring, it led to an estimated ~85% cost reduction. Apply it with an understanding of the latency and Stage 1 accuracy trade-offs.

---

## Repository

https://github.com/Yoshiki0705/ontap-edge-to-cloud-ai

---

*Cost figures are estimates under specific conditions. This is a personal technical exploration, not an official position of any organization.*
