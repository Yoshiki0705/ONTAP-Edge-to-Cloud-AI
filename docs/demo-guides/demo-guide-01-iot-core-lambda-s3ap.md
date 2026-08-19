> 🌐 Language: **English**

# Demo Guide 01: IoT Core → Lambda → S3 AP Direct Write

> **Goal**: Validate the end-to-end flow of MQTT telemetry → IoT Core rule → Lambda → PutObject → FSx for ONTAP S3 Access Point → Athena query. No S3 standard bucket involved.

> **Time**: ~45 minutes (excluding FSx for ONTAP provisioning)
> **Cost**: IoT Core and Lambda are billed per message and per invocation, so the total
> follows the publish rate this guide configures. The "~$2/day" quoted here previously gave
> no message volume and no pricing date, so it could not be checked. FSx for ONTAP is separate
> and dominates — see [the cost model](../en/cost-model.md).

> **Prerequisites**: Complete [Demo Guide 00](./demo-guide-00-prerequisites.md) first.

---

## Architecture

```
[MQTT Client]          [IoT Core]           [Lambda]              [FSx for ONTAP]
mosquitto_pub  ──────> Rules Engine  ──────> iot-s3ap-ingest ──> S3 AP PutObject
  │                      │                    │                      │
  │ topic:               │ SQL:               │ handler.py           │ Volume: /iot-data
  │ edge/{device}/       │ SELECT *,          │  - Parse event       │   └── ingest/{device}/
  │   telemetry          │   topic(2)         │  - Build key         │       year=.../month=../
  │                      │   as device_id     │  - PutObject         │       day=.../hour=../
  │                      │                    │    to S3AP_ARN       │       {uuid}.json
  └──────────────────────┴────────────────────┴──────────────────────┘
                                                                         │
                                                                         ▼
                                                                    [Athena]
                                                                    SELECT * FROM iot_data
                                                                    WHERE year='2026'
                                                                      AND device_id='rpi5-001'
```

---

## Step 1: Deploy IoT Ingestion Stack

```bash
cd /path/to/edge-to-cloud-ai

# Deploy (direct mode — IoT Core → Lambda, no SQS)
sam build --template-file cloud/iot_ingestion/template.yaml

sam deploy \
  --template-file cloud/iot_ingestion/template.yaml \
  --stack-name edge-to-cloud-iot-ingestion-poc \
  --parameter-overrides \
    Environment=poc \
    S3APAccessPointArn="$S3AP_ARN" \
    MqttTopicFilter="edge/+/telemetry" \
    BatchMode=false \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$AWS_REGION" \
  --resolve-s3
```

**Expected output**: Stack creates:
- Lambda function: `edge-to-cloud-iot-s3ap-ingest-poc`
- IoT Core rule: `edge_to_cloud_s3ap_ingest_poc`
- IAM roles with S3 AP PutObject permission

### Verify deployment

```bash
# Check Lambda exists
aws lambda get-function \
  --function-name edge-to-cloud-iot-s3ap-ingest-poc \
  --query "Configuration.{State:State,Runtime:Runtime,Memory:MemorySize}" \
  --region "$AWS_REGION"

# Check IoT Rule exists
aws iot get-topic-rule \
  --rule-name edge_to_cloud_s3ap_ingest_poc \
  --query "rule.{sql:sql,actions:actions[0]}" \
  --region "$AWS_REGION"
```

---

## Step 2: Publish Test MQTT Message

```bash
# Single telemetry message
mosquitto_pub \
  --cafile certs/AmazonRootCA1.pem \
  --cert "certs/${DEVICE_ID}-cert.pem" \
  --key "certs/${DEVICE_ID}-private.pem" \
  -h "$IOT_ENDPOINT" \
  -p 8883 \
  -t "edge/${DEVICE_ID}/telemetry" \
  -m '{
    "temperature": 23.5,
    "humidity": 67.2,
    "vibration_rms": 0.42,
    "current_amps": 1.8,
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
  }'
```

**Alternative (AWS CLI — no certificates needed):**

```bash
aws iot-data publish \
  --topic "edge/${DEVICE_ID}/telemetry" \
  --cli-binary-format raw-in-base64-out \
  --payload '{
    "temperature": 23.5,
    "humidity": 67.2,
    "vibration_rms": 0.42,
    "current_amps": 1.8,
    "timestamp": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"
  }' \
  --region "$AWS_REGION"
```

---

## Step 3: Verify Data Written to FSx for ONTAP via S3 AP

### 3.1 ListObjectsV2 via S3 AP

```bash
# Wait 2-3 seconds for Lambda execution
sleep 3

# List written objects
aws s3api list-objects-v2 \
  --bucket "$S3AP_ARN" \
  --prefix "ingest/${DEVICE_ID}/" \
  --region "$AWS_REGION" | jq '.Contents[] | {Key, Size, LastModified}'
```

**Expected output**:
```json
{
  "Key": "ingest/rpi5-001/year=2026/month=07/day=27/hour=14/a1b2c3d4e5f6.json",
  "Size": 142,
  "LastModified": "2026-07-27T14:30:02+00:00"
}
```

### 3.2 GetObject — Read back the written data

```bash
KEY=$(aws s3api list-objects-v2 \
  --bucket "$S3AP_ARN" \
  --prefix "ingest/${DEVICE_ID}/" \
  --query "Contents[-1].Key" \
  --output text --region "$AWS_REGION")

aws s3api get-object \
  --bucket "$S3AP_ARN" \
  --key "$KEY" \
  /dev/stdout --region "$AWS_REGION" | jq .
```

**Expected output**:
```json
{
  "device_id": "rpi5-001",
  "temperature": 23.5,
  "humidity": 67.2,
  "vibration_rms": 0.42,
  "current_amps": 1.8,
  "timestamp": "2026-07-27T14:30:00Z"
}
```

### 3.3 Verify via NFS (optional — requires EC2 in same VPC)

```bash
# On EC2 instance with NFS mount to FSx for ONTAP
ls /mnt/fsxn/iot-data/ingest/rpi5-001/year=2026/month=07/day=27/hour=14/
cat /mnt/fsxn/iot-data/ingest/rpi5-001/year=2026/month=07/day=27/hour=14/*.json | jq .
```

This confirms **multiprotocol access** — same data written via S3 AP is readable via NFS.

---

## Step 4: Publish Multiple Messages (Load Test)

```bash
# Send 20 messages at 1-second intervals
for i in $(seq 1 20); do
  TEMP=$(echo "20 + $i * 0.3" | bc)
  aws iot-data publish \
    --topic "edge/${DEVICE_ID}/telemetry" \
    --cli-binary-format raw-in-base64-out \
    --payload "{
      \"temperature\": $TEMP,
      \"humidity\": $(echo "60 + $RANDOM % 20" | bc),
      \"vibration_rms\": $(echo "scale=2; $RANDOM / 32768" | bc),
      \"current_amps\": $(echo "scale=1; 1 + $RANDOM % 3" | bc),
      \"sequence\": $i,
      \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
    }" \
    --region "$AWS_REGION"
  sleep 1
done

echo "Published 20 messages. Waiting for Lambda processing..."
sleep 5
```

### Verify all messages written

```bash
OBJECT_COUNT=$(aws s3api list-objects-v2 \
  --bucket "$S3AP_ARN" \
  --prefix "ingest/${DEVICE_ID}/" \
  --query "KeyCount" \
  --output text --region "$AWS_REGION")

echo "Objects in S3 AP: $OBJECT_COUNT"
# Expected: 20+ (including any from Step 2)
```

---

## Step 5: Query with Amazon Athena via S3 AP

### 5.1 Create Glue Database and Table

```bash
aws glue create-database \
  --database-input '{"Name": "edge_to_cloud_iot"}' \
  --region "$AWS_REGION" 2>/dev/null || true

aws glue create-table \
  --database-name "edge_to_cloud_iot" \
  --table-input '{
    "Name": "telemetry_raw",
    "StorageDescriptor": {
      "Columns": [
        {"Name": "device_id", "Type": "string"},
        {"Name": "temperature", "Type": "double"},
        {"Name": "humidity", "Type": "double"},
        {"Name": "vibration_rms", "Type": "double"},
        {"Name": "current_amps", "Type": "double"},
        {"Name": "sequence", "Type": "int"},
        {"Name": "timestamp", "Type": "string"}
      ],
      "Location": "s3://'${S3AP_ARN}'/ingest/'${DEVICE_ID}'/",
      "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
      "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
      "SerdeInfo": {
        "SerializationLibrary": "org.openx.data.jsonserde.JsonSerDe"
      }
    },
    "PartitionKeys": [
      {"Name": "year", "Type": "string"},
      {"Name": "month", "Type": "string"},
      {"Name": "day", "Type": "string"},
      {"Name": "hour", "Type": "string"}
    ],
    "TableType": "EXTERNAL_TABLE",
    "Parameters": {
      "projection.enabled": "true",
      "projection.year.type": "integer",
      "projection.year.range": "2024,2030",
      "projection.month.type": "integer",
      "projection.month.range": "1,12",
      "projection.month.digits": "2",
      "projection.day.type": "integer",
      "projection.day.range": "1,31",
      "projection.day.digits": "2",
      "projection.hour.type": "integer",
      "projection.hour.range": "0,23",
      "projection.hour.digits": "2",
      "storage.location.template": "s3://'${S3AP_ARN}'/ingest/'${DEVICE_ID}'/year=${year}/month=${month}/day=${day}/hour=${hour}"
    }
  }' \
  --region "$AWS_REGION"
```

### 5.2 Run Athena Query

```bash
QUERY_ID=$(aws athena start-query-execution \
  --query-string "SELECT device_id, temperature, humidity, timestamp
    FROM edge_to_cloud_iot.telemetry_raw
    WHERE year = '$(date -u +%Y)'
      AND month = '$(date -u +%m)'
      AND day = '$(date -u +%d)'
    ORDER BY timestamp DESC
    LIMIT 10" \
  --result-configuration "OutputLocation=s3://${S3AP_ARN}/athena-results/" \
  --region "$AWS_REGION" \
  --query "QueryExecutionId" --output text)

echo "Query ID: $QUERY_ID"

# Wait for completion
sleep 5
aws athena get-query-execution \
  --query-execution-id "$QUERY_ID" \
  --query "QueryExecution.Status" \
  --region "$AWS_REGION"

# Get results
aws athena get-query-results \
  --query-execution-id "$QUERY_ID" \
  --region "$AWS_REGION" | jq '.ResultSet.Rows[1:6]'
```

**Expected**: Temperature values from your published messages, queried directly from FSx for ONTAP via S3 AP — no S3 standard bucket involved.

---

## Step 6: Check Lambda Metrics

```bash
# Invocation count
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=edge-to-cloud-iot-s3ap-ingest-poc \
  --start-time "$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 \
  --statistics Sum \
  --region "$AWS_REGION" | jq '.Datapoints | sort_by(.Timestamp) | last'

# Duration (latency)
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=edge-to-cloud-iot-s3ap-ingest-poc \
  --start-time "$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 \
  --statistics Average \
  --region "$AWS_REGION" | jq '.Datapoints | sort_by(.Timestamp) | last'
```

---

## Validation Checklist

| # | Check | Command | Expected |
|---|-------|---------|----------|
| 1 | Lambda deployed | `aws lambda get-function --function-name ...` | State: Active |
| 2 | IoT Rule created | `aws iot get-topic-rule --rule-name ...` | SQL + Lambda action |
| 3 | MQTT publish succeeds | `aws iot-data publish ...` | Exit 0 |
| 4 | Object appears in S3 AP | `aws s3api list-objects-v2 --bucket $S3AP_ARN ...` | Key with Hive partition |
| 5 | Object readable via S3 AP | `aws s3api get-object --bucket $S3AP_ARN ...` | Original telemetry JSON |
| 6 | Object readable via NFS | `cat /mnt/fsxn/iot-data/ingest/...` | Same JSON content |
| 7 | Athena query succeeds | `aws athena get-query-results ...` | Telemetry rows returned |
| 8 | Lambda duration < 500ms | CloudWatch Duration metric | Avg < 500ms |
| 9 | No S3 bucket used | Verify no `s3://bucket-name` in pipeline | All paths use S3 AP ARN |

---

## Troubleshooting

| Symptom | Likely Cause | Resolution |
|---------|-------------|------------|
| Lambda returns 500 "AccessDenied" | IAM role missing S3 AP permission | Check `s3:PutObject` on `${S3AP_ARN}/object/*` |
| Objects not appearing after publish | IoT Rule disabled or SQL mismatch | `aws iot get-topic-rule` — check SQL filter |
| Athena query returns 0 rows | Partition projection mismatch | Verify `storage.location.template` path matches actual keys |
| Lambda cold start > 2s | First invocation after idle | Normal for Python 3.12 Lambda. Subsequent calls < 100ms |
| "No such access point" error | S3 AP not AVAILABLE yet | Poll: `aws fsx describe-s3-access-points` until Lifecycle=AVAILABLE |

---

## Cleanup

```bash
# Delete IoT ingestion stack
aws cloudformation delete-stack \
  --stack-name edge-to-cloud-iot-ingestion-poc \
  --region "$AWS_REGION"

# Delete Athena table/database
aws glue delete-table --database-name edge_to_cloud_iot --name telemetry_raw --region "$AWS_REGION"
aws glue delete-database --name edge_to_cloud_iot --region "$AWS_REGION"

# Delete test data from S3 AP (optional — or delete volume)
aws s3 rm "s3://${S3AP_ARN}/ingest/" --recursive --region "$AWS_REGION"
aws s3 rm "s3://${S3AP_ARN}/test/" --recursive --region "$AWS_REGION"
```

---

## Next Steps

- **Demo Guide 02**: [Greengrass S3 AP Client Component](./demo-guide-02-greengrass-s3ap-client.md) — deploy the custom Greengrass component on Raspberry Pi for direct PutObject to S3 AP with offline buffer
- **Demo Guide 03** (planned): FlexCache read cache distribution of ingested data to on-premises GPU servers
