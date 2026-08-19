"""Greengrass custom S3 Access Point client component.

Writes IoT data directly to FSx for ONTAP S3 Access Points,
bypassing S3 standard buckets. Provides local disk buffering
and exponential backoff retry for offline resilience.
"""
