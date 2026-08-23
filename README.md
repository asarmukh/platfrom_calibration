# Platform Calibration

Desktop UI for the force-platform calibration workflow, built with PySide6 from
the *Platform Calibration v2* design and the ТЗ in `docs/`.

The window opens the serial port from `config.ini` on startup, then drives the
whole calibration conversation: factory gain factors, calibration factors, the
reading stream a run produces, and the forces and centre of pressure computed
from it. Neither platform type is preselected: picking SINGLE or DOUBLE brings
up that many pad cards with their defaults, and entering a Platform ID is what
makes them usable — the ТЗ shows the values at startup but forbids any action
until the platform is addressed.

## Tests

```sh
pip install -r requirements-dev.txt
pytest
```

The suite is written against the ТЗ section by section: frame layouts and CRC,
the section 6 formulas, and what each button puts on the wire. See
`docs/OPERATION.md` for the behaviour it pins down.

`python tests/render_views.py` renders the window's states to
`tests/_views/*.png` for a visual check.

## Run

```sh
pip install -r requirements.txt
python app.py
```

The status bar reports `connecting to COM5…`, then either
`connected to COM5 at 115200 baud` (green) or `could not open COM5 — ports
available: …` (red) with a **RETRY** button. Hovering the message shows the
driver's full error, and the same detail is logged to the terminal.

Check the connection without starting the UI:

```sh
python -m device
```

## Building an executable

```sh
pip install -r requirements-dev.txt
pyinstaller platform_calibration.spec
```

The result is a single `dist/PlatformCalibration.exe` (~43 MB, Qt is most of
it) that runs without Python installed. Copy just that file wherever you need
it.

- **config.ini is not bundled.** The app writes it next to the executable on
  first run, so the port and baud rate stay editable — that is what `paths.py`
  is for: assets are read from the unpacked bundle, `config.ini` from the
  executable's own folder.
- **Console window.** `console=True` in `platform_calibration.spec`, because the
  ТЗ asks for a log of every command and answer. Flip it to `False` only if the
  operator is not supposed to see one.
- **Icon**: `assets/logo.ico` — the arrow from `assets/logo.svg` on the panel colour.
- Startup takes a couple of seconds: a one-file build unpacks itself to a
  temporary folder first. For an instant start, replace `EXE(...)` with the
  standard `EXE(...) + COLLECT(...)` pair to get a folder build instead.

Closing the window releases the serial port. Force-killing the process from
Task Manager can leave the bootloader's child process holding it — a one-file
build runs as two processes.

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
config.ini                serial port + retry settings
assets/                   logo.svg, logo.jpeg, logo.ico
paths.py                  project root / bundle directory (PyInstaller aware)
app.py                    entry point, command logic, frame routing
calc.py                   forces and centre of pressure (ТЗ section 6)
device/
  settings.py             config schema: dataclasses, defaults, load/save
  protocol.py             frame layouts, CRC, stream framing (ТЗ 2 and 7)
  serial_link.py          serial connection with retry/backoff (no Qt)
  connection.py           Qt controller: connects on a worker thread
  __main__.py             connection check CLI
widgets/
  theme.py                colours, fonts and the global Qt style sheet
  common.py               labels, fields, buttons, segmented control
  header_bar.py           title bar
  sidebar.py              platform type, platform ID, device actions, totals
  workspace.py            empty state + calibration view, section heading
  pad_card.py             pad channel map (ch0–ch6) with its forces and cop columns
  cop_plot.py             centre-of-pressure mini plot (custom painted)
tests/                    the ТЗ as an executable specification
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
- **Views.** Two content states — the prompt for a platform ID and the pad view
  — held in a `QStackedWidget`. The prompt is what shows until an ID is entered.
- **Variants.** `PadRow` carries the double-platform options from the design
  (`show_forces` for the per-pad Fx/Fy/Fz column, `cop="total"` for the taller
  total-cop plot), and `ChannelBlock` hides the calibration row in the GF view.
- **Letter spacing** is applied through `QFont.setLetterSpacing`, since Qt style
  sheets have no `letter-spacing` property.
