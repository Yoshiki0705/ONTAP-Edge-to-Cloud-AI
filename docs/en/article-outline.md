# dev.to Article Structure: Edge-to-Cloud AI Series

> Status: Outline draft (body not written)  
> Target audience: IoT/AWS engineers, SORACOM users, manufacturing DX practitioners  
> Series: 3 articles planned

---

## Article 1: "Automated 3D Print Quality Monitoring with Raspberry Pi + SORACOM + Bedrock"

### Target Audience

- Engineers interested in IoT × Generative AI
- People who haven't used SORACOM Flux
- 3D printer users (Maker community)

### Structure

1. **Introduction** (200 words)
   - The problem: unattended 3D prints fail without detection
   - Limitations of existing monitoring (timelapse, built-in cameras)
   - Solution: real-time AI inspection

2. **Architecture Overview** (300 words + diagram)
   - Pi → SORACOM → S3 → Bedrock → notification pipeline
   - Two-stage analysis (Haiku screening + Sonnet detail) cost optimization
   - Why this architecture (comparison with alternatives)

3. **Implementation: Edge Side** (with code, 500 words)
   - simple_capture.py walkthrough (minimal config)
   - Camera placement tips (framing, lighting, mounting)
   - SORACOM SIM + Flux configuration steps

4. **Implementation: Cloud Side** (with code, 500 words)
   - CloudFormation template walkthrough
   - Lambda two-stage analysis logic
   - Prompt engineering tips

5. **Results and Accuracy** (300 words + table)
   - Prompt test results (5/5 = 100%)
   - Detectable defect types and severity classification
   - Cost actuals ($40/month vs $259/month)

6. **Summary and Next Article Preview** (200 words)
   - Phase 1 outcomes
   - Next: ONTAP integration for data accumulation and analytics

### Tags

`#iot` `#aws` `#raspberrypi` `#3dprinting` `#generativeai`

---

## Article 2: "ONTAP × IoT: Connecting Factory File Data to AI Analytics"

### Target Audience

- NetApp / ONTAP users
- Manufacturing IT/OT practitioners
- Data engineers (file data → analytics platform)

### Structure

1. **Introduction**: Unlocking data trapped in factory NAS (inspection images, equipment logs)
2. **ONTAP value in IoT context**: FPolicy, SnapMirror, FlexCache, Multi-Protocol, S3 AP
3. **Implementation: FPolicy → automated analysis pipeline**
4. **Implementation: SnapMirror → FSxN → Athena/Bedrock**
5. **Implementation: ONTAP REST API telemetry → predictive maintenance**
6. **Results and cost**
7. **Summary**

### Tags

`#netapp` `#ontap` `#aws` `#iot` `#manufacturing`

---

## Article 3: "What It Takes to Move an IoT × AI PoC to Production"

### Target Audience

- People who've done IoT PoCs but struggle with production
- Architects, project managers

### Structure

1. **Introduction**: The PoC worked. But it never went to production. Why?
2. **PoC → Pilot → Production barriers**
   - Device operations (OTA updates, incident response, replacement procedures)
   - Cost management (two-stage analysis, capture frequency optimization)
   - Security (device hardening, network segmentation)
   - Monitoring (health checks, data quality validation)
3. **Practices from this project**
   - Setting Go/No-Go criteria
   - Incremental feature addition (Flux → Lambda → ONTAP)
   - Cost optimization example ($259 → $40)
4. **Checklist: 10 items needed for production**
5. **Summary**

### Tags

`#iot` `#devops` `#architecture` `#aws` `#bestpractices`

---

## Publication Schedule

| Article | Writing Start | Target Publish | Dependency |
|---------|-------------|---------------|-----------|
| Article 1 | After Pi arrival (need real photos) | Pi arrival + 2 weeks | Hardware test complete |
| Article 2 | After ONTAP connection | Article 1 + 2 weeks | FAS2820 access |
| Article 3 | After pilot complete | Article 2 + 2 weeks | Scale-out test |

## Article Quality Checklist (Pre-publish)

- [ ] Code is verified working (copy-paste reproducible)
- [ ] Screenshots/photos are from real hardware
- [ ] Cost figures are measured (estimates clearly labeled)
- [ ] No vendor marketing language
- [ ] Constraints and caveats stated
- [ ] Published in both ja/en (or en only)
- [ ] Link to GitHub repository included
- [ ] Links to previous/next articles in series
