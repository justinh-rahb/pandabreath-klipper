# pandabreath-klipper

Klipper extras module to integrate the **BIQU Panda Breath** smart chamber heater/filter with **Klipper-based printers** (primary target: Snapmaker U1).

## Project Goal

The Panda Breath has no native Klipper support yet. BTT has not released the firmware source. The plan is to write a Klipper `extras/` module that speaks the device's WebSocket JSON API and exposes it to Klipper as a temperature sensor + heater, making it fully scriptable via macros and `printer.cfg`.

## Device: BIQU Panda Breath

**Hardware** (schematic reverse-engineered from real device — see [research/hardware-schematic.md](research/hardware-schematic.md))
- Controller: ESP32-C3 (WiFi 2.4GHz; USB-C flashing via CH340K)
- Heater: 300W PTC, relay-switched (MGR-GJ-5-L SSR, on/off only; firmware duty-cycles for regulation)
- Fans: 2× 75×75×30mm, TRIAC phase-angle speed control (BT136-800E + MOC3021S + zero-crossing)
- Chamber temp: NTC 100K thermistor on dedicated ADC channel (33K 0.1% divider) — this is `warehouse_temper`
- PTC temp: second NTC 100K on separate ADC channel — for thermal runaway protection only
- Buttons: 4× LED-backlit tactile switches (K1–K4); K1–K3 are K6-6140S01 with per-button LEDs
- AC input: 110–220V → HLK-PM01 (5V) → AS1117-3.3 (3.3V MCU)
- Logic: 3.3V

**Firmware**
- Current release: V1.0.2 (buggy — V1.0.1+ has thermal/timing issues)
- V0.0.0 (Aug 25 2025) is the only confirmed stable version
- Source not yet published; BTT tracking: https://github.com/bigtreetech/Panda_Breath
- License: CC-BY-NC-ND-4.0 (non-commercial)
- OTA update via HTTP POST to `/ota` endpoint (not WebSocket); max app size 0x480000 bytes
- Full 4MB flash dump of V0.0.0 obtained via `esptool flash_read` from a real device — contains embedded web UI JS which is the protocol source of truth

**Network**
- Default hostname: `PandaBreath.local`
- AP fallback SSID: `Panda_Breath_XXXXXXXXXX`, password: `987654321`, IP: `192.168.254.1`
- Control interface: WebSocket at `ws://<ip>/ws` (port 80, no auth)

## WebSocket Protocol

All messages are JSON with a top-level `settings` key. The device sends state updates; you send commands in the same format.

### Inbound (device → client) — state updates
```json
{ "settings": { "work_on": true } }
{ "settings": { "work_mode": 2 } }
{ "settings": { "hotbedtemp": 60 } }
{ "settings": { "temp": 45 } }
{ "settings": { "warehouse_temper": 38.5 } }
```

### Outbound (client → device) — commands
```json
{ "settings": { "work_on": true } }          // enable/disable device
{ "settings": { "work_mode": 1 } }           // 1=auto, 2=always_on, 3=filament_drying
{ "settings": { "temp": 45 } }               // set target temperature (°C)
{ "settings": { "hotbedtemp": 60 } }         // hotbed temp that triggers auto mode
```

### Field reference (confirmed from binary strings + community)

| Field | Dir | Type | Description |
|---|---|---|---|
| `work_on` | ↔ | bool | Power on/off |
| `work_mode` | ↔ | int | 1=Auto (follows bed temp), 2=Always On, 3=Filament Drying |
| `hotbedtemp` | ↔ | int | Bed temp threshold that triggers auto mode |
| `warehouse_temper` | ←device | float | Current chamber temperature reading |
| `set_temp` | →device | int | **Likely** the writable field to set target temp (needs live verification) |
| `temp` | ←device | int | Target temp readback (may be read-only) |
| `filtertemp` | ? | int | Filter temperature (threshold or sensor reading — TBD) |
| `filament_temp` | ↔ | int | Filament drying target temperature |
| `filament_timer` | ↔ | int | Filament drying duration |
| `filament_drying_mode` | ←device | bool/int | Filament drying active flag |
| `custom_temp` | ↔ | int | Custom mode temperature |
| `custom_timer` | ↔ | int | Custom mode timer |
| `remaining_seconds` | ←device | int | Countdown timer (drying mode) |
| `fw_version` | ←device | string | Firmware version string |
| `ptc_sensor_status` | ←device | int | PTC thermistor health |
| `warehouse_sensor_status` | ←device | int | Chamber thermistor health |
| `ptc_heater_status` | ←device | int | PTC heater element status |
| `cal_ptc_temp` | ←device | float | Calibrated PTC temperature |
| `cal_warehouse_temp` | ←device | float | Calibrated chamber temperature |
| `isrunning` | →device | int | Start (1) / stop (0) filament drying cycle |
| `reset` | →device | int | Reboot device (`{'reset': 1}`) |
| `factory_reset` | →device | int | Factory reset (`{'factory_reset': 1}`) |
| `language` | →device | string | UI language (`'en'`, `'zh'`) |
| `set_ap` | →device | ? | Trigger AP/hotspot mode |

**Note:** `set_temp` vs `temp` distinction discovered via binary strings — needs live device verification. The device's auto mode reads `bed_temper`/`nozzle_temper`/`gcode_state` from the Bambu MQTT connection; this won't work with Klipper, so the Klipper module should manage auto logic directly and use `work_mode: 2` (always_on).

See [research/firmware-analysis.md](research/firmware-analysis.md) for binary analysis and [research/protocol-from-v0.0.0.md](research/protocol-from-v0.0.0.md) for the definitive protocol reference (extracted from embedded JS in the v0.0.0 full flash dump).

## Target Platform: Snapmaker U1

- Runs a **modified Klipper + Moonraker** (Snapmaker-proprietary; open-source release promised by March 2026)
- Extended community firmware: https://snapmakeru1-extended-firmware.pages.dev — GitHub: https://github.com/paxx12/SnapmakerU1
- The U1 has a **passive cavity thermometer** only — no active chamber heater built in
- The Panda Breath is officially listed as U1-compatible by BIQU
- Klipper extras drop into `/home/lava/klipper/klippy/extras/` on the U1

**U1 Extended Firmware — key facts for development:**
- SSH credentials: `root` / `snapmaker` and `lava` / `snapmaker`
- Klipper path on device: `/home/lava/klipper/`
- Entware package manager available in devel builds (`opkg install python3-websocket` etc.)
- Web UI selectable: Fluidd or Mainsail
- Overlay-based build system — Klipper patches go in `overlays/firmware-extended/20-klipper-patches/patches/home/lava/klipper/klippy/`
- Build: `./dev.sh make extract` → edit overlays → build profile `basic` or `extended`
- `DEVEL=1` flag enables opkg/entware

## Integration Architecture

**Approach:** Klipper `extras/` plugin (`panda_breath.py`) — a single file.

**Design decision:** Expose as a standard Klipper heater only. No custom GCode commands. Orca Slicer already handles chamber temperature via `SET_HEATER_TEMPERATURE [HEATER=panda_breath]` — adding custom GCodes would duplicate that and create complexity for no gain.

### What the module does
1. Maintains a persistent WebSocket connection to the device (reconnects on drop)
2. **Listens for temperature** — `temp_task` on device pushes `warehouse_temper`/`cal_warehouse_temp` periodically; no confirmed query command exists. On reconnect the device may push initial state (`init one:` pattern seen in strings — unverified). Klipper is the authority on desired state, so we track what we sent rather than querying.
3. Reports current temperature; prefer `cal_warehouse_temp` (ADC-calibrated) over `warehouse_temper` (raw)
4. Implements standard Klipper heater interface — `set_temp()` / `get_temp()` / `check_busy()`
5. When target > 0: sends `work_mode: 2` (always_on) + `work_on: true`
6. When target = 0: sends `work_on: false`
7. Uses Klipper reactor for I/O (`reactor.register_timer`) — no raw asyncio

### What the module does NOT do
- No `PANDA_BREATH_*` GCode commands
- No custom macros
- No mode-switching logic (user sets target temp; the module turns the device on/off)

### `printer.cfg` config block (target)
```ini
[panda_breath]
host: pandabreath.local   # or IP address
port: 80
```

### Key Klipper patterns to follow
- `extras/heater_generic.py` — primary reference; this is what we're implementing
- `extras/temperature_sensor.py` — reference for sensor registration pattern
- Klipper reactor for non-blocking I/O: `self.reactor.register_timer()`

### Python WebSocket on U1
- **Production:** ship `websocket-client` as a firmware overlay (installed at build time via entware/opkg)
- **Development/testing:** use devel extended firmware build (`DEVEL=1`) which has opkg available, then `opkg install python3-websocket`

## Known Constraints

- Firmware bugs in V1.0.1+ mean some features (auto mode, temp setting) may be unreliable
- BTT has not published WebSocket API docs — all protocol knowledge is from reverse engineering
- **No confirmed state-query command** — button/UI changes don't push WS messages (confirmed v0.0.0); no "get state" request exists in JS source; reconnecting may be the only way to get a full state snapshot (unverified). Module tracks its own sent state rather than querying.
- The device WebSocket drops and needs reconnection — reliability of WS connection is a concern
- No authentication on the WebSocket — only a concern on untrusted networks
- Snapmaker U1 modified Klipper may have subtle differences from upstream — test on real hardware

## Development Approach

1. Start with a standalone Python test script to validate WebSocket protocol
2. Build the Klipper extras module against upstream Klipper
3. Test on U1 with extended firmware (SSH access)
4. Handle reconnection, error states, and thermal-runaway-safe defaults
5. Provide sample macros for common workflows (pre-heat chamber before print, filament drying, etc.)

## File Structure (planned)
```
panda_breath.py          # Klipper extras module — the deliverable
test_ws.py               # standalone WebSocket probe/test tool
research/                # firmware analysis and protocol notes
docs/
  klipper_install.md     # installation instructions for U1
```

## References

- [BIQU Panda Breath product page](https://biqu.equipment/products/biqu-panda-breath-smart-air-filtration-and-heating-system-with-precise-temperature-regulation)
- [BTT Wiki — Panda Breath](https://global.bttwiki.com/Panda_Breath.html)
- [Panda Breath GitHub (BTT, firmware not yet published)](https://github.com/bigtreetech/Panda_Breath)
- [Snapmaker U1 Klipper discussion](https://klipper.discourse.group/t/the-snapmaker-u1-its-an-iot-device-with-klipper/25549)
- [U1 Extended Firmware docs](https://snapmakeru1-extended-firmware.pages.dev)
- [U1 Extended Firmware — development](https://snapmakeru1-extended-firmware.pages.dev/development)
- [U1 Extended Firmware GitHub](https://github.com/paxx12/SnapmakerU1)
- [Klipper extras API reference](https://www.klipper3d.org/API_Server.html)
