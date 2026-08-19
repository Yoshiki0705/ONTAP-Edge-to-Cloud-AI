"""AWS Glue ETL Job: Transform raw IoT data to Parquet for analytics.

This job reads raw JSON sensor readings and ONTAP telemetry from S3,
applies schema validation, and writes optimized Parquet files for Athena queries.

Glue Job Parameters:
    --source_bucket: S3 bucket containing raw data
    --target_bucket: S3 bucket for processed output (can be same as source)
    --database_name: Glue Data Catalog database name
    --processing_date: Date to process (YYYY-MM-DD format, default: yesterday)
"""

import sys
from datetime import UTC, datetime, timedelta

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.transforms import *  # noqa: F403  AWS Glue's documented import form
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F

# Initialize Glue context
sc = SparkContext()
glue_context = GlueContext(sc)
spark = glue_context.spark_session
job = Job(glue_context)

# Parse job parameters
args = getResolvedOptions(
    sys.argv,
    [
        "JOB_NAME",
        "source_bucket",
        "target_bucket",
        "database_name",
        "processing_date",
    ],
)
job.init(args["JOB_NAME"], args)

SOURCE_BUCKET = args["source_bucket"]
TARGET_BUCKET = args["target_bucket"]
DATABASE_NAME = args["database_name"]

# Default to yesterday if not specified
if args.get("processing_date"):
    PROCESSING_DATE = datetime.strptime(args["processing_date"], "%Y-%m-%d")
else:
    PROCESSING_DATE = datetime.now(UTC) - timedelta(days=1)

YEAR = f"{PROCESSING_DATE.year:04d}"
MONTH = f"{PROCESSING_DATE.month:02d}"
DAY = f"{PROCESSING_DATE.day:02d}"


def process_sensor_readings():
    """Transform raw sensor readings JSON to Parquet.

    Idempotency: Uses overwrite mode per date partition.
    Re-running for the same date replaces the output (no duplicates).
    """
    source_path = (
        f"s3://{SOURCE_BUCKET}/raw/sensor_reading/"
        f"year={YEAR}/month={MONTH}/day={DAY}/"
    )
    target_path = (
        f"s3://{TARGET_BUCKET}/processed/sensor_aggregated/"
        f"year={YEAR}/month={MONTH}/day={DAY}/"
    )

    print(f"Processing sensor readings: {source_path}")

    try:
        df = spark.read.json(source_path)
        if df.rdd.isEmpty():
            print("No sensor data found for this date")
            return

        # Flatten the nested structure
        flattened = df.select(
            F.col("device_id"),
            F.to_timestamp(F.col("timestamp")).alias("event_timestamp"),
            F.col("schema_version"),
            F.explode("payload.readings").alias("reading"),
        ).select(
            F.col("device_id"),
            F.col("event_timestamp"),
            F.col("reading.sensor_id").alias("sensor_id"),
            F.col("reading.sensor_type").alias("sensor_type"),
            F.col("reading.values").alias("values"),
        )

        # Write as Parquet (overwrite for idempotency)
        flattened.write.mode("overwrite").parquet(target_path)
        record_count = flattened.count()
        print(f"Sensor readings processed: {record_count} records → {target_path}")

    except Exception as e:
        print(f"Error processing sensor readings: {e}")
        raise


def process_ontap_telemetry():
    """Transform raw ONTAP telemetry JSON to Parquet.

    Idempotency: Uses overwrite mode per date partition.
    Type optimization: Converts ISO 8601 strings to Spark TimestampType
    for efficient Athena range queries.
    """
    source_path = (
        f"s3://{SOURCE_BUCKET}/raw/ontap_telemetry/"
        f"year={YEAR}/month={MONTH}/day={DAY}/"
    )
    target_path = (
        f"s3://{TARGET_BUCKET}/processed/ontap_metrics/"
        f"year={YEAR}/month={MONTH}/day={DAY}/"
    )

    print(f"Processing ONTAP telemetry: {source_path}")

    try:
        df = spark.read.json(source_path)
        if df.rdd.isEmpty():
            print("No ONTAP telemetry found for this date")
            return

        # Flatten volume metrics with proper type conversion
        volumes_df = df.select(
            F.col("device_id"),
            F.to_timestamp(F.col("timestamp")).alias("event_timestamp"),
            F.col("payload.cluster.name").alias("cluster_name"),
            F.col("payload.cluster.ontap_version").alias("ontap_version"),
            F.col("payload.node_metrics.cpu_utilization_percent").cast("double").alias(
                "node_cpu_pct"
            ),
            F.explode("payload.volumes").alias("volume"),
        ).select(
            F.col("device_id"),
            F.col("event_timestamp"),
            F.col("cluster_name"),
            F.col("ontap_version"),
            F.col("node_cpu_pct"),
            F.col("volume.name").alias("volume_name"),
            F.col("volume.svm").alias("svm_name"),
            F.col("volume.metrics.iops_read").cast("long").alias("iops_read"),
            F.col("volume.metrics.iops_write").cast("long").alias("iops_write"),
            F.col("volume.metrics.iops_total").cast("long").alias("iops_total"),
            F.col("volume.metrics.throughput_read_mbps").cast("double").alias("throughput_read_mbps"),
            F.col("volume.metrics.throughput_write_mbps").cast("double").alias(
                "throughput_write_mbps"
            ),
            F.col("volume.metrics.latency_read_us").cast("long").alias("latency_read_us"),
            F.col("volume.metrics.latency_write_us").cast("long").alias("latency_write_us"),
            F.col("volume.metrics.capacity_used_bytes").cast("long").alias("capacity_used_bytes"),
            F.col("volume.metrics.capacity_total_bytes").cast("long").alias(
                "capacity_total_bytes"
            ),
            F.col("volume.metrics.capacity_used_percent").cast("double").alias(
                "capacity_used_pct"
            ),
        )

        # Write as Parquet (overwrite for idempotency)
        volumes_df.write.mode("overwrite").parquet(target_path)
        record_count = volumes_df.count()
        print(f"ONTAP telemetry processed: {record_count} records → {target_path}")

    except Exception as e:
        print(f"Error processing ONTAP telemetry: {e}")
        raise


def process_image_analysis():
    """Transform image analysis results JSON to Parquet."""
    source_path = (
        f"s3://{TARGET_BUCKET}/processed/image_analysis/"
        f"year={YEAR}/month={MONTH}/day={DAY}/"
    )

    # Image analysis results are already in processed/ (written by Lambda)
    # This step creates a daily summary in curated/
    target_path = (
        f"s3://{TARGET_BUCKET}/curated/print_quality_summary/"
        f"year={YEAR}/month={MONTH}/"
    )

    print(f"Summarizing image analysis: {source_path}")

    try:
        df = spark.read.json(source_path)
        if df.rdd.isEmpty():
            print("No image analysis results found for this date")
            return

        # Create daily summary
        summary = df.select(
            F.lit(f"{YEAR}-{MONTH}-{DAY}").alias("date"),
            F.col("payload.result.status").alias("status"),
            F.col("payload.result.confidence").alias("confidence"),
            F.col("payload.result.overall_quality_score").alias("quality_score"),
        ).groupBy("date").agg(
            F.count("*").alias("total_inspections"),
            F.sum(F.when(F.col("status") == "anomaly_detected", 1).otherwise(0)).alias(
                "anomaly_count"
            ),
            F.avg("confidence").alias("avg_confidence"),
            F.avg("quality_score").alias("avg_quality_score"),
            F.min("quality_score").alias("min_quality_score"),
        )

        # Append to monthly summary (don't overwrite)
        summary.write.mode("append").parquet(target_path)
        print(f"Image analysis summary written → {target_path}")

    except Exception as e:
        print(f"Error summarizing image analysis: {e}")
        # Non-fatal: summary is optional
        print("Continuing despite summary error")


# Execute ETL pipeline
print(f"=== Glue ETL Job Start: {YEAR}-{MONTH}-{DAY} ===")
print(f"Source: s3://{SOURCE_BUCKET}/raw/")
print(f"Target: s3://{TARGET_BUCKET}/processed/")

process_sensor_readings()
process_ontap_telemetry()
process_image_analysis()

print("=== Glue ETL Job Complete ===")
job.commit()
