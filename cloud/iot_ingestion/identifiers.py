"""Validation for untrusted identifiers that reach S3 keys and object metadata.

Why this exists
---------------
`handler._build_key` interpolated `device_id` straight from the MQTT payload into
an S3 key. Measured before the fix:

    '../../../etc/shadow' -> 'ingest/../../../etc/shadow/year=2026/.../<id>.json'
    'a\r\nX-Injected: 1'  -> 'ingest/a\r\nX-Injected: 1/year=2026/.../<id>.json'

S3 does not normalise `..`, so the object is reachable under that literal key.
The consumers do normalise: this pipeline writes through an FSx for ONTAP S3
Access Point, where a key becomes a path in a real filesystem namespace, and
Athena/Glue read the `ingest/<device_id>/year=.../` layout as Hive partitions. A
`..` segment therefore escapes the intended prefix rather than merely looking
odd, and a CR/LF lands in a `PutObject` metadata header value.

The authenticated identity of an MQTT publisher is its IoT Core client ID and
the topic it was allowed to publish to, not a field inside the payload it
controls. `resolve_device_id` prefers the values IoT Core attaches (via the
rule's SQL, see cloud/iot_ingestion/template.yaml) and treats the payload field
as a last resort that still has to pass validation.

Reference: https://docs.aws.amazon.com/iot/latest/developerguide/thing-policy-variables.html
"""

from __future__ import annotations

import re

# A device id becomes exactly one S3 key segment. Allowing '/' would let a
# publisher invent partition levels; allowing '.' as a whole segment ('.', '..')
# is the traversal above. Hyphen, underscore and colon cover the identifier
# shapes SORACOM/Greengrass/IoT Core actually emit.
DEVICE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class UnsafeIdentifierError(ValueError):
    """Raised when an identifier cannot be used in a key or a header."""


def validate_device_id(device_id: object) -> str:
    """Return `device_id` unchanged, or raise `UnsafeIdentifierError`.

    Deliberately rejecting rather than sanitising: silently rewriting
    '../../x' to 'x' would merge two publishers into one partition, and the
    caller could not tell that it happened.
    """
    if not isinstance(device_id, str):
        raise UnsafeIdentifierError(
            f"device_id must be a string, got {type(device_id).__name__}"
        )
    if not DEVICE_ID_RE.match(device_id):
        raise UnsafeIdentifierError(
            "device_id must match "
            f"{DEVICE_ID_RE.pattern} (rejected: {device_id!r})"
        )
    # '.', '..' and '/'-bearing values are already excluded: the first
    # character class forbids a leading dot, and '/' is absent from both
    # classes. Tests assert this rather than a second guard clause here.
    return device_id


def resolve_device_id(event: dict, fallback: str = "unknown") -> str:
    """Pick the most trustworthy device id available on an event.

    Order of preference:
      1. `client_id` / `clientId` — set by the IoT Core rule from
         `clientid()`, which the publisher cannot forge.
      2. `topic_device_id` — extracted by the rule from the topic filter the
         publisher was authorised for.
      3. `device_id` / `source_id` — payload fields, publisher-controlled.

    A value that fails validation is not silently replaced: the caller gets an
    `UnsafeIdentifierError` so the message is rejected and shows up in metrics,
    rather than being written under a mangled key.
    """
    for field in ("client_id", "clientId", "topic_device_id", "device_id", "source_id"):
        value = event.get(field)
        if value is None or value == "":
            continue
        return validate_device_id(value)
    return validate_device_id(fallback)
