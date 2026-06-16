"""Load synthetic events directly into ClickHouse (no Kafka required).

Fastest path to a working demo: generates v3 events and inserts them straight
into kafka_events_raw, triggering all Materialized Views (quality_events,
payload_manifest, anomaly_events, etc.).

Use this for quick dashboard demos. For the full Kafka path, use the Kafka
source table (002_kafka_source_table.sql) + synthetic_events.py with KAFKA_ENABLED.

Usage:
    pip install clickhouse-connect
    python3 load_events_direct.py --count 200
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tests"))
sys.path.insert(0, str(Path(__file__).parent.parent / "edge" / "raspberry-pi" / "common"))

import synthetic_events as se  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Load synthetic events into ClickHouse directly")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8123)
    args = parser.parse_args()

    try:
        import clickhouse_connect
    except ImportError:
        print("ERROR: pip install clickhouse-connect")
        return 1

    client = clickhouse_connect.get_client(host=args.host, port=args.port)

    # Column order matches kafka_events_raw DDL
    columns = [
        "event_id", "event_type", "domain", "event_category", "source_id",
        "asset_type", "asset_id", "site_id", "line_id", "equipment_id",
        "sensor_id", "timestamp", "ingest_time", "schema_version",
        "payload_uri", "payload_type", "content_type", "checksum",
        "size_bytes", "lineage_id", "processing_status", "metadata", "is_synthetic",
    ]

    rows = []
    event_types = list(se.GENERATORS.keys())
    import random
    for _ in range(args.count):
        et = random.choice(event_types)
        e = se.GENERATORS[et]()
        rows.append([
            e["event_id"], e["event_type"], e["domain"], e["event_category"],
            e["source_id"], e["asset_type"], e["asset_id"], e["site_id"],
            e["line_id"], e["equipment_id"], e["sensor_id"],
            e["timestamp"].replace("Z", "").replace("T", " ")[:23],
            e["ingest_time"].replace("Z", "").replace("T", " ")[:23],
            e["schema_version"], e["payload_uri"], e["payload_type"],
            e["content_type"], e["checksum"], e["size_bytes"] or 0,
            e["lineage_id"], e["processing_status"],
            json.dumps(e["metadata"], ensure_ascii=False),
            True,  # is_synthetic
        ])

    client.insert("kafka_events_raw", rows, column_names=columns)
    print(f"Inserted {len(rows)} events into kafka_events_raw")

    # Show MV results
    for tbl in ["quality_events", "payload_manifest", "anomaly_events", "feedback_events"]:
        try:
            cnt = client.query(f"SELECT count() FROM {tbl}").result_rows[0][0]
            print(f"  {tbl}: {cnt} rows")
        except Exception as e:
            print(f"  {tbl}: (not queryable: {e})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
