"""Application configuration, stored as an INI file at the project root.

The file is created with defaults on first read, so a fresh checkout runs
without any manual setup.
"""

from __future__ import annotations

import configparser
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping, get_type_hints

from paths import app_dir

# Next to the executable in a build, so edits survive a restart.
CONFIG_PATH = app_dir() / "config.ini"

HEADER = """\
; Platform Calibration settings.
;
; [serial] port      serial port of the device, e.g. COM5 on Windows or
;                    /dev/ttyUSB0 on Linux. Run
;                    `python -m device` to list ports.
;          baudrate  link speed, must match the device firmware.
;          parity    N, E, O, M or S.  timeouts are in seconds.
;
; [retry]  attempts  total tries, including the first one.
;          delay     seconds to wait before the second attempt.
;          backoff   delay multiplier applied after each failure.
;          max_delay upper bound on the wait between attempts.
"""


@dataclass
class SerialSettings:
    """Serial port parameters for the calibration device."""

    port: str = "COM5"
    baudrate: int = 115200
    bytesize: int = 8
    parity: str = "N"  # N, E, O, M or S
    stopbits: float = 1
    timeout: float = 1.0  # read timeout, seconds
    write_timeout: float = 1.0


@dataclass
class RetrySettings:
    """How hard to try when the port is busy or the device is still booting."""

    attempts: int = 5  # total tries, including the first
    delay: float = 1.0  # seconds before the second attempt
    backoff: float = 1.5  # multiplier applied to the delay after each failure
    max_delay: float = 8.0  # cap on the wait between attempts


@dataclass
class AppConfig:
    serial: SerialSettings = field(default_factory=SerialSettings)
    retry: RetrySettings = field(default_factory=RetrySettings)

    # --- persistence -------------------------------------------------------

    @classmethod
    def load(cls, path: Path | str = CONFIG_PATH, *, create: bool = True) -> "AppConfig":
        """Read the config file. Writes defaults first if it does not exist."""
        path = Path(path)
        if not path.exists():
            config = cls()
            if create:
                config.save(path)
            return config

        parser = configparser.ConfigParser()
        try:
            parser.read(path, encoding="utf-8")
        except configparser.Error as exc:
            raise ValueError(f"{path} is not a valid INI file: {exc}") from exc

        return cls(
            serial=_section(SerialSettings, "serial", parser),
            retry=_section(RetrySettings, "retry", parser),
        )

    def save(self, path: Path | str = CONFIG_PATH) -> Path:
        """Write the settings back out. Only the header comments survive."""
        path = Path(path)
        parser = configparser.ConfigParser()
        for name, values in self.to_dict().items():
            parser[name] = {key: str(value) for key, value in values.items()}

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            handle.write(HEADER + "\n")
            parser.write(handle)
        return path

    # --- conversion --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _section(model: type, name: str, parser: configparser.ConfigParser) -> Any:
    """Build a settings dataclass from one INI section.

    Missing sections and keys fall back to the dataclass defaults, and unknown
    keys are ignored, so an older config file keeps working.
    """
    values: Mapping[str, str] = parser[name] if parser.has_section(name) else {}
    hints = get_type_hints(model)
    kwargs = {
        f.name: _coerce(hints[f.name], values[f.name], f"{name}.{f.name}")
        for f in fields(model)
        if f.name in values
    }
    return model(**kwargs)


def _coerce(target: type, raw: str, where: str) -> Any:
    raw = raw.strip()
    try:
        if target is bool:
            return configparser.ConfigParser.BOOLEAN_STATES[raw.lower()]
        if target is int:
            return int(raw)
        if target is float:
            return float(raw)
    except (ValueError, KeyError) as exc:
        raise ValueError(
            f"{where}: expected {target.__name__}, got {raw!r}"
        ) from exc
    return raw
