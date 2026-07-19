# Lessons Learned

> Technical insights gained through the validation process of this project.

## Two-Stage AI Analysis Cuts Cost by 85%

Analyzing all images with the high-accuracy model (Claude Sonnet) costs ~$259/month. A two-stage approach — screening with Haiku and routing only suspected anomalies to Sonnet — brings it down to ~$40/month.

**Design pattern:**

```
Image arrives → Haiku (cheap, fast) → Normal: done
                                    → Suspected anomaly: Sonnet (high accuracy) → judgment
```

- Haiku: $0.25/1M input tokens — suitable for full-volume processing
- Sonnet: $3.00/1M input tokens — only for images requiring detailed analysis
- At 5% anomaly rate, ~85% cost reduction

This pattern applies to other AI pipelines beyond image judgment (text classification, audio analysis, etc.).

## Prompts Alone Achieve Practical Accuracy for Industrial Image Judgment

Without custom model training, Claude Vision prompts correctly identified 3D print defects in 9/9 test cases.

**Test conditions:**
- Public + synthetic images used
- Defect types: layer delamination, stringing, warping, nozzle clogging
- Judgment criteria explicitly stated in prompt

**Caveats:**
- Accuracy under real conditions (lighting, camera angle, filament color variation) is unverified
- Production use requires domain-specific prompt tuning and threshold adjustment

## FSx for ONTAP S3 Access Points Constraints

S3 Access Points (2025 GA) enable S3 API access to data aggregated in ONTAP. However, the following constraints apply:

| Constraint | Impact | Mitigation |
|-----------|--------|-----------|
| No conditional writes | Cannot write Iceberg/Delta Lake directly | Complement with FPolicy + Lambda |
| No event notifications | S3 Event Notifications unavailable | Use FPolicy for file-arrival detection |
| AD-joined SVM requires AD DC reachability | All data ops return AccessDenied when DC unreachable | Embed pre-flight health check |

Details: [FAQ](faq.md)

## ONTAP REST API Works Well for IoT Telemetry Collection

Performance metrics, capacity, and health can be collected at 1-minute intervals.

- Polling-based but sufficient granularity for PoC
- `/api/cluster/metrics` for cluster-wide, `/api/storage/volumes` for volume-level
- Authentication via ONTAP local accounts or AD integration

**Constraints:**
- No push-based (webhook) option. Polling interval design required
- Large volume environments need pagination handling

## Related Documents

- [Data Schema Design](data-schema-design.md)
- [Operations Design](operations-design.md)
- [FAQ](faq.md)
