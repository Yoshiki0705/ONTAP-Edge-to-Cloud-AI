"""Entry point for Greengrass S3 AP client component.

Runs as a long-lived Greengrass component, accepting data via
local IPC (file system watcher) and flushing to S3 AP.
"""

import logging
import sys
import time
from pathlib import Path

from .component import S3APClientComponent
from .config import ComponentConfig

logger = logging.getLogger(__name__)


def main() -> None:
    """Component main loop."""
    config = ComponentConfig()

    logging.basicConfig(
        level=config.log_level,
        format='{"time":"%(asctime)s","level":"%(levelname)s","component":"s3ap-client","msg":"%(message)s"}',
        stream=sys.stdout,
    )

    logger.info("Initializing S3 AP client component...")
    component = S3APClientComponent(config)

    try:
        component.start()

        # Watch local data directory for new files
        # In production, this would be replaced by IPC subscription
        # from camera/sensor components
        watch_dir = Path(config.buffer.db_path).parent / "incoming"
        watch_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Watching for incoming files: %s", watch_dir)

        while True:
            # Check for new files in incoming directory
            for file_path in sorted(watch_dir.iterdir()):
                if file_path.is_file() and not file_path.name.startswith("."):
                    content_type = _detect_content_type(file_path)
                    try:
                        component.ingest_file(
                            file_path=file_path,
                            content_type=content_type,
                        )
                        # Remove from incoming after buffering
                        file_path.unlink()
                    except Exception as e:
                        logger.error("Failed to ingest %s: %s", file_path.name, e)

            time.sleep(1)  # Poll interval for incoming directory

    except KeyboardInterrupt:
        logger.info("Interrupted.")
    finally:
        component.stop()


def _detect_content_type(path: Path) -> str:
    """Detect content type from file extension."""
    ext_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".json": "application/json",
        ".parquet": "application/x-parquet",
        ".csv": "text/csv",
        ".gz": "application/gzip",
    }
    return ext_map.get(path.suffix.lower(), "application/octet-stream")


if __name__ == "__main__":
    main()
