"""Connection check: ``python -m device``.

Opens the port from config.json using the configured retry policy and reports
what happened, without starting the UI.
"""

from __future__ import annotations

import logging
import sys

from settings import CONFIG_PATH, AppConfig
from .serial_link import SerialLink, SerialLinkError, available_ports


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    config = AppConfig.load()
    print(f"config      {CONFIG_PATH}")
    print(f"port        {config.serial.port} @ {config.serial.baudrate} baud")
    print(f"retry       {config.retry.attempts} attempts, "
          f"{config.retry.delay}s delay, x{config.retry.backoff} backoff")
    print(f"available   {', '.join(available_ports()) or 'none'}")

    link = SerialLink(config.serial, config.retry)
    try:
        link.connect()
    except SerialLinkError as exc:
        print(f"\nFAILED      {exc}")
        return 1
    else:
        print("\nOK          port opened")
        link.close()
        return 0


if __name__ == "__main__":
    sys.exit(main())
