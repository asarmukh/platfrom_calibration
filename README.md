# Platform Calibration

Desktop UI for the force-platform calibration workflow, built with PySide6 from
the *Platform Calibration v2* design.

The window opens the serial port from `config.ini` on startup and shows the
result in the status bar. The calibration widgets themselves are still
presentation-only — no readings, no calculations — but Read / Write / Start stay
disabled until the device is actually connected.

## Run

```sh
pip install -r requirements.txt
python main.py
```

The status bar reports `connecting to COM5…`, then either
`connected to COM5 at 115200 baud` (green) or `could not open COM5 — ports
available: …` (red) with a **RETRY** button. Hovering the message shows the
driver's full error, and the same detail is logged to the terminal.

Check the connection without starting the UI:

```sh
python -m device
```

## Configuration

`config.ini` at the project root holds the connection settings. It is created
with defaults the first time it is read, so nothing has to exist up front.

```ini
[serial]
port = COM5
baudrate = 115200
timeout = 1.0

[retry]
attempts = 5
delay = 1.0
backoff = 1.5
max_delay = 8.0
```

- **serial** — `port`, `baudrate`, plus `bytesize`, `parity`, `stopbits`,
  `timeout` and `write_timeout`. Set `port` to whatever
  `python -m device` lists as available.
- **retry** — `attempts` includes the first try; the wait starts at `delay`
  seconds and is multiplied by `backoff` after each failure, capped at
  `max_delay`.

`config.ini` holds the values; `settings.py` holds the schema behind them — the
defaults, the type of each field and the load/save code.

Unknown keys and sections are ignored, and missing ones fall back to the
defaults in `settings.py`, so an older config file keeps working. Values are
type-checked on load: `baudrate = fast` fails with
`serial.baudrate: expected int, got 'fast'` rather than surfacing later as a
serial error. Rewriting the file through `AppConfig.save()` keeps the header
comments but drops any others.

## Connecting

```python
from settings import AppConfig
from device import SerialLink, SerialLinkError

config = AppConfig.load()
link = SerialLink(config.serial, config.retry)
try:
    with link:                      # connects with retry, closes on exit
        link.port.write(b"...")
except SerialLinkError as exc:
    print(exc)
```

`connect()` takes two optional arguments: `on_attempt(attempt, total, error)`
to report progress, and `cancel` — a `threading.Event` that aborts the loop
*and* the backoff wait, so a UI can cancel a connection that is still retrying.
`SerialLink` has no Qt imports, so it can run on a worker thread.

## Layout

```
main.py                   launcher
config.ini                serial port + retry settings
app.py                    QApplication + MainWindow (header / sidebar / workspace)
settings.py               config schema: dataclasses, defaults, load/save
theme.py                  colours, fonts and the global Qt style sheet
device/
  serial_link.py          serial connection with retry/backoff (no Qt)
  connection.py           Qt controller: connects on a worker thread
  __main__.py             connection check CLI
widgets/
  common.py               labels, fields, buttons, segmented control
  header_bar.py           title bar
  sidebar.py              platform type, platform ID, device actions, totals
  workspace.py            empty state + calibration view, section heading
  pad_card.py             pad channel map (ch0–ch6) with its forces and cop columns
  cop_plot.py             centre-of-pressure mini plot (custom painted)
```

The modules are top-level, so **run everything from the project root** — that is
what puts `theme`, `config`, `device` and `widgets` on the import path. If the
app ever needs to be `pip install`ed or imported from another project, the
modules would have to move back under a package folder.

## Notes on the port

- **Fonts.** The design uses Barlow Condensed, Barlow and JetBrains Mono. If they
  are not installed, `theme.family()` falls back to the closest system faces
  (Segoe UI / Cascadia Mono), so the layout holds either way. Installing the
  three families gives an exact match.
- **Views.** The design has two content states — an empty prompt and the pad
  view — held in a `QStackedWidget`. The pad view is shown by default so the
  full design is visible; switching is a one-line change once logic exists.
- **Variants.** `PadRow` already accepts the double-platform options from the
  design (`show_forces` for the per-pad Fx/Fy/Fz column, `cop="total"` for the
  taller total-cop plot), and `ChannelBlock` can hide the calibration row for the
  GF-only view.
- **Letter spacing** is applied through `QFont.setLetterSpacing`, since Qt style
  sheets have no `letter-spacing` property.
