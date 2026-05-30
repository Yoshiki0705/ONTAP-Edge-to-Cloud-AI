# Cellular Fallback Modules (Option)

These modules are for sites **without wired LAN** where SORACOM cellular
connectivity is the only option.

For the primary architecture (wired LAN → ONTAP NFS), use `../simple_capture.py`.

## When to use these modules

- No wired LAN available at the site
- SORACOM SIM is the only connectivity
- Data cannot be written to ONTAP NFS directly

## Modules

| File | Purpose |
|------|---------|
| `main.py` | Full-featured capture loop with buffer and health monitoring |
| `uploader.py` | HTTP upload to SORACOM unified endpoint with retry |
| `buffer.py` | SQLite-based local buffer for offline resilience |
| `health.py` | Device health reporting via SORACOM |
| `config.py` | Configuration (environment variables) |
| `edge-camera.service` | systemd unit file |

## Primary architecture (use instead)

```
simple_capture.py → NFS → ONTAP → FPolicy → Lambda → Bedrock
```
