# pandabreath-klipper

Klipper extras module to integrate the **BIQU Panda Breath** smart chamber heater/filter with **Klipper-based printers** (primary target: Snapmaker U1).

## Project Goal

The Panda Breath has no native Klipper support yet. BTT has not released the firmware source. The primary supported path plus two experimental alternatives:

1. **Stock firmware path** — Klipper `extras/` module that speaks the device's WebSocket JSON API. Use firmware `1.0.3+` for best Klipper support. Current release: **V1.0.4** (May 2026) with native HA MQTT auto-discovery. V1.0.3 added `printer_type: 2` (Klipper) as a communication mode.
2. **~~ESPHome path~~** *(largely redundant)* — Reflash with ESPHome for TRIAC fan control, configurable PTC relay, and MQTT. **v1.0.4's native HA MQTT auto-discovery provides similar HA integration without reflashing**, making this path redundant for most use cases. Retained in repo for reference only.
3. **KlipperMCU path** — Reflash the ESP32-C3 with a custom ESP-IDF firmware that speaks the Klipper MCU binary protocol over UART0 (via the onboard CH340K USB-C bridge). The Panda Breath becomes a native `[mcu panda_breath]` — no Python extras module, no MQTT broker, Klipper's own PID and thermal safety apply directly. Fan control is internal to firmware (TRIAC phase-angle via zero-crossing ISR). See `klipper-firmware/`.

The Klipper module (`panda_breath.py`) supports stock and ESPHome via a transport abstraction: `firmware: stock` uses the WebSocket transport; `firmware: esphome` uses the MQTT transport. From Klipper's perspective the interface is identical either way.

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
- Current release: **V1.0.4** (May 2026) — adds native HA MQTT auto-discovery
- V1.0.3 (Mar 2026) — adds Klipper `printer_type`, `filament_drying_mode` writes, PTC sensor fault UI
- V1.0.2 (Jan 2026) — buggy; silently removed PTC thermal runaway detection
- V1.0.1 (Dec 2025) — first update; has thermal/timing issues
- V0.0.0 (Aug 2025) — factory firmware; only confirmed stable version; embedded web UI JS is the protocol source of truth
- Source not yet published; BTT tracking: https://github.com/bigtreetech/Panda_Breath
- License: CC-BY-NC-ND-4.0 (non-commercial)
- OTA update via HTTP POST to `/ota` endpoint (not WebSocket); max app size 0x480000 bytes
- Full 4MB flash dump of V0.0.0 obtained via `esptool flash_read` from a real device

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
{ "settings": { "set_temp": 45 } }           // set target temperature (°C)
{ "settings": { "hotbedtemp": 60 } }         // hotbed temp that triggers auto mode
```

### Field reference (confirmed from binary strings + community)

| Field | Dir | Type | Description |
|---|---|---|---|
| `work_on` | ↔ | bool | Power on/off |
| `work_mode` | ↔ | int | 1=Auto (follows bed temp), 2=Always On, 3=Filament Drying |
| `hotbedtemp` | ↔ | int | Bed temp threshold that triggers auto mode |
| `warehouse_temper` | ←device | float | Current chamber temperature reading |
| `cal_warehouse_temp` | ←device | float | Calibrated chamber temperature (prefer this) |
| `cal_ptc_temp` | ←device | float | Calibrated PTC temperature |
| `set_temp` | →device | int | Writable field to set target chamber temperature (Confirmed) |
| `temp` | ←device | int | Target temp readback (may be read-only) |
| `filtertemp` | ←device | int | Filter temperature threshold |
| `filament_temp` | ↔ | int | Filament drying target temperature |
| `filament_timer` | ↔ | int | Filament drying duration (hours) |
| `filament_drying_mode` | ↔ | int | 1=PLA, 2=PETG, 3=custom (writable v1.0.3+) |
| `custom_temp` | ↔ | int | Custom mode temperature (40–60°C) |
| `custom_timer` | ↔ | int | Custom mode timer (1–99h) |
| `remaining_seconds` | ←device | int | Countdown timer (drying mode) |
| `fw_version` | ←device | string | Firmware version string |
| `ptc_sensor_status` | ←device | int | PTC thermistor health: 0=OK, 1=open, 2=short (v1.0.3+) |
| `warehouse_sensor_status` | ←device | int | Chamber thermistor health |
| `ptc_heater_status` | ←device | int | PTC heater element status |
| `printer_type` | ↔ | int | 1=BambuLab, 2=Klipper (v1.0.3+) — communication mode only, does not change auto-mode behavior |
| `isrunning` | →device | int | Start (1) / stop (0) filament drying cycle |
| `reset` | →device | int | Reboot device (`{'reset': 1}`) |
| `factory_reset` | →device | int | Factory reset (`{'factory_reset': 1}`) |
| `language` | →device | string | UI language (`'en'`, `'zh'`) |
| `set_ap` | →device | ? | Trigger AP/hotspot mode |
| `target_temp` | ↔ | int | Target temperature 0–60°C (v1.0.4+ HA alias; module mirrors with legacy `set_temp`/`temp`) |
| `filter_temp` | ↔ | int | Filter trigger temp 0–120°C (v1.0.4+ HA alias for `filtertemp`) |
| `heater_temp` | →device? | int | Heater trigger temp 40–120°C (v1.0.4+ — **needs live WS testing**) |
| `drying_running` | ↔ | bool | Start/stop drying ON/OFF (v1.0.4+ HA alias; module mirrors with legacy `isrunning`) |
| `chamber_temp` | ←device | float | Chamber temperature (v1.0.4+ HA alias for `warehouse_temper`) |
| `filament_button` | ←device | int | Physical button state, values 1/2/3 (v1.0.4+) |
| `drying_remaining_min` | ←device | int | Drying time remaining in minutes (v1.0.4+) |
| `printer_bind` | ←device | string | Printer bind status (v1.0.4+) |
| `printer_ip` | ←device | string | Bound printer IP (v1.0.4+) |
| `printer_name` | ←device | string | Bound printer name (v1.0.4+) |
| `printer_sn` | ←device | string | Bound printer serial number (v1.0.4+) |

**Note:** `set_temp` is definitively the writable key for setting the target temperature via WebSocket, while `temp` is used for the legacy native-auto target. v1.0.4 introduces `target_temp` as a writable HA/MQTT field (0–60°C). The module keeps `set_temp`/`temp` for backward compatibility and mirrors `target_temp` as an alias. The device's auto mode reads `bed_temper`/`nozzle_temper`/`gcode_state` from the Bambu MQTT connection; this won't work with Klipper, so the default Klipper heater path uses `work_mode: 2` (always_on).

### Native MQTT Protocol (v1.0.4+)

v1.0.4 adds a `btt_mqtt` client (independent of the Bambu `bambu_mqtt` client) that connects to a user-configured MQTT broker and publishes Home Assistant auto-discovery configs.

**Topic structure:** `<prefix>/<device_id>/state` (published), `<prefix>/<device_id>/command` (subscribed), `<prefix>/<device_id>/availability` (LWT).

**HA auto-discovery entities** published to `homeassistant/...` topics: `chamber_temp`, `work_on`, `mode`, `filament_drying_mode`, `target_temp` (0–60°C), `filter_temp` (0–120°C), `heater_temp` (40–120°C), `custom_temp` (40–60°C), `custom_timer` (1–99h), `drying_running`, `drying_remaining_min`, `printer_sn`, `printer_bind`, `printer_ip`, `printer_name`.

MQTT command payloads use JSON matching the WS `settings` format. NVS key: `ha_mqtt_info`.

**This native HA MQTT makes the ESPHome reflash path largely redundant** — v1.0.4 stock firmware provides HA integration without reflashing.

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
- Entware package manager available in devel builds (`DEVEL=1` flag) — but **no pre-built opkg repo exists yet**; one will need to be sourced/built when the U1 overlay is developed
- Web UI selectable: Fluidd or Mainsail
- Overlay-based build system — Klipper patches go in `overlays/firmware-extended/20-klipper-patches/patches/home/lava/klipper/klippy/`
- Build: `./dev.sh make extract` → edit overlays → build profile `basic` or `extended`
- `DEVEL=1` flag enables opkg/entware

## Integration Architecture

**Approach:** Klipper `extras/` plugin (`panda_breath.py`) — a single self-contained file, **no external Python dependencies**.

**Design decision:** Expose as a standard Klipper heater. The baseline control path uses `SET_HEATER_TEMPERATURE HEATER=panda_breath`. Stock firmware also exposes optional passthrough commands (`PANDA_BREATH_AUTO`, `PANDA_BREATH_DRY_START`, `PANDA_BREATH_DRY_STOP`) for OEM native modes.

### Transport abstraction

The module contains two transport classes sharing a common internal interface (`connect`, `set_target`, state callback). `PandaBreath.__init__` instantiates the correct one from the `firmware:` config key:

```
PandaBreath (Klipper heater_generic)
    ├── get_temp() / set_temp() / check_busy()   ← identical either way
    └── self.transport ─┬─ WebSocketTransport    (firmware: stock)
                        └─ MqttTransport         (firmware: esphome)
```

Both transports run a background I/O thread and push state updates into a thread-safe deque that the Klipper reactor timer drains.

### What the module does
1. Instantiates the appropriate transport based on `firmware:` config key
2. Transport maintains a persistent connection and reconnects on drop
3. Reports current temperature via `get_temp()` — prefers `cal_warehouse_temp`, then `chamber_temp`, then `warehouse_temper` (stock), or `chamber_temperature` MQTT topic (ESPHome)
4. Implements standard Klipper heater interface — `set_temp()` / `get_temp()` / `check_busy()`
5. When target > 0: stock sends `{isrunning: 0, drying_running: false}`, `work_mode: 2`, `{set_temp: t, target_temp: t}`, then `{work_on: true}`; ESPHome publishes to climate mode/target topics
6. When target = 0: stock sends `{isrunning: 0, drying_running: false, target_temp: 0}` and `{work_on: false}`; ESPHome publishes `mode: off`
7. Forces device off on Klipper connect, disconnect, and shutdown
8. Resends last desired state after reconnect
9. Stock firmware registers optional passthrough GCode commands (`PANDA_BREATH_AUTO`, `PANDA_BREATH_DRY_START`, `PANDA_BREATH_DRY_STOP`)

### What the module does NOT do
- No opinionated `M141`/`M191` macros in the module itself (templates in `config/`)
- No mode-switching logic beyond what the user explicitly requests

### `printer.cfg` config blocks

**Stock firmware (default; use firmware `1.0.3+`):**
```ini
[panda_breath]
firmware: stock
host: pandabreath.local   # or IP address
port: 80

[heater_generic panda_breath]
heater_pin: panda_breath:pwm
sensor_type: panda_breath
control: watermark
max_delta: 0.5
min_temp: 15
max_temp: 80

[verify_heater panda_breath]
check_gain_time: 360
hysteresis: 5
heating_gain: 1

[gcode_macro M141]
description: Set chamber temperature (Panda Breath)
gcode:
    {% set s = params.S|default(0)|float %}
    SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET={s}

[gcode_macro M191]
description: Wait for chamber temperature (Panda Breath)
gcode:
    {% set s = params.S|default(0)|float %}
    M141 S{s}
    {% if s > 0 %}
        TEMPERATURE_WAIT SENSOR="heater_generic panda_breath" MINIMUM={s}
    {% endif %}
```

**ESPHome firmware:**
```ini
[panda_breath]
firmware: esphome
mqtt_broker: 192.168.1.x
mqtt_port: 1883
mqtt_topic_prefix: panda-breath
```

### Key Klipper patterns to follow
- `extras/heater_generic.py` — primary reference; this is what we're implementing
- `extras/temperature_sensor.py` — reference for sensor registration pattern
- Klipper reactor for non-blocking I/O: `self.reactor.register_timer()`

### Python dependencies — stdlib only
`panda_breath.py` uses **only Python standard library** — no `websocket-client`, no `paho-mqtt`.
- WebSocket transport: `socket` + `hashlib` + `base64` + `struct` + `json` (~150 lines, implements the subset of RFC 6455 actually used)
- MQTT transport: `socket` + `struct` + `json` (~200 lines, implements CONNECT/SUBSCRIBE/PUBLISH/PINGREQ only)

This means the U1 overlay is a single file drop — no opkg, no entware packages, no build-time installs required. This is critical because no pre-built opkg repo exists yet for the U1 extended firmware.

## Known Constraints

- **Use firmware `1.0.3+` for stock Klipper path.** V1.0.3 adds `printer_type: 2` (Klipper communication mode) and PTC sensor fault UI. V1.0.4 adds native HA MQTT auto-discovery. V1.0.2 silently removed PTC thermal runaway detection.
- BTT has not published WebSocket API docs — all protocol knowledge is from reverse engineering
- **No confirmed state-query command** (stock firmware) — button/UI changes don't push WS messages (confirmed v0.0.0); no "get state" request exists in JS source; reconnecting may be the only way to get a full state snapshot (unverified). Module tracks its own sent state rather than querying.
- The device WebSocket drops and needs reconnection — reliability of WS connection is a concern
- No authentication on the WebSocket — only a concern on untrusted networks
- **v1.0.4 field compatibility** — the module parses `chamber_temp`, `target_temp`, `filter_temp`, `heater_temp`, `drying_running`, `drying_remaining_min`, and `filament_button`. Writes keep the confirmed legacy WS keys and mirror low-risk aliases; live validation is still needed before replacing legacy keys.
- **ESPHome path is largely redundant** — v1.0.4's native HA MQTT auto-discovery provides HA integration without reflashing, making the ESPHome reflash path unnecessary for most users
- **Snapmaker U1 modified Klipper enforces strict duck-typing**. Generic proxies must securely spoof `get_name()`, `short_name`, and `check_busy()` or the U1's custom power-loss and extrusion macros will crash into an `Internal error`. `panda_breath.py` has been updated to proactively cover this.
- **No pre-built opkg repo for U1 extended firmware** — Entware is present on devel builds but packages must be sourced/built manually; this is a future task when building the U1 overlay
- **ESPHome GPIO pins resolved** — three GPIO pin assignments (TH0 chamber NTC → GPIO0, TH1 PTC NTC → GPIO1, RLY_MOSFET relay → GPIO18) inferred by cross-referencing schematic module pad numbers with ESP32-C3-MINI-1 datasheet; continuity testing on real hardware recommended to confirm

## Development Approach

### Klipper module (`panda_breath.py`)
1. Implement `WebSocketTransport` with inline stdlib WebSocket client
2. Implement `MqttTransport` with inline stdlib MQTT client (CONNECT/SUBSCRIBE/PUBLISH/PINGREQ only)
3. Implement `PandaBreath` heater class with transport abstraction
4. Test both transports with standalone scripts before integrating with Klipper
5. Test on U1 with extended firmware (SSH access)
6. Handle reconnection, error states, and thermal-runaway-safe defaults

### ~~ESPHome firmware (`esphome/`)~~ — deprioritized
*v1.0.4's native HA MQTT auto-discovery makes this path largely redundant. Retained for reference.*
1. ~~Resolve three placeholder GPIO substitutions~~ — resolved (GPIO0, GPIO1, GPIO18)
2. ~~Verify GPIO0/GPIO7 zero-crossing conflict~~ — resolved
3. Flash ESPHome, validate NTC readings against OEM firmware values
4. Tune `min_power` for fan stall threshold
5. Validate thermal safety cutoff (PTC element overheat interval)

### KlipperMCU firmware (`klipper-firmware/`)
Based on nikhil-robinson/klipper_esp32; adapted for ESP32-C3 + Panda Breath hardware.
1. ~~Resolve three placeholder GPIOs in `board/panda_breath_pins.h` (TH0/TH1/RLY_MOSFET) via hardware continuity testing~~ — resolved via module datasheet cross-reference (GPIO0, GPIO1, GPIO18); continuity testing recommended to confirm
2. Build: `cd klipper-firmware && idf.py set-target esp32c3 && idf.py build`
3. Flash: `idf.py -p /dev/cu.wchusbserial* flash`
4. Copy `components/klipper/klipper/out/klipper.dict` to Klipper host alongside `printer.cfg`
5. Connect Panda Breath USB-C to U1; verify `/dev/ttyUSB0` appears
6. Validate: temperature reads, heater control, fan runs during heater-on
**Key differences from klipper_esp32:**
- `sdkconfig.defaults`: `CONFIG_IDF_TARGET="esp32c3"`, UART pins TX=21/RX=20
- `main.c`: `DECL_CONSTANT_STR("MCU", "esp32c3")`, calls `fan_init()` before scheduler
- `CMakeLists.txt`: `driver` instead of `esp_driver_usb_serial_jtag`; adds `board/fan.c`
- New: `board/panda_breath_pins.h`, `board/fan.c` (TRIAC phase-angle, internal)
- All other board files (adc.c already has ESP32-C3 table, timer.c uses gptimer, etc.) work unchanged

### U1 extended firmware overlay (future)
1. Source/build opkg packages needed for any remaining dependencies
2. Create overlay that drops `panda_breath.py` into `/home/lava/klipper/klippy/extras/`
3. Build and test on real U1 hardware

## File Structure
```
panda_breath.py          # Klipper extras module — stock + ESPHome, stdlib only
test_ws.py               # standalone WebSocket probe/test tool (stock firmware)
esphome/
  panda_breath.yaml      # ESPHome config (GPIOs inferred from module datasheet — continuity test recommended)
  secrets.yaml           # credentials — gitignored
  secrets.yaml.example   # template
  README.md              # ESPHome setup, TODOs, validation steps, recovery
klipper-firmware/        # Pathway 3: KlipperMCU ESP-IDF firmware (ESP32-C3)
  CMakeLists.txt         # ESP-IDF project root (project name: panda_breath)
  sdkconfig.defaults     # esp32c3 target, UART0 at 250000 baud (TX=21/RX=20)
  main/
    main.c               # app_main → FreeRTOS task → fan_init + sched_main
    Kconfig.projbuild    # Klipper + UART console Kconfig options
  components/klipper/
    CMakeLists.txt       # Klipper MCU C sources + board layer + CTR extraction
    board/
      panda_breath_pins.h  # GPIO assignments (3 inferred from module datasheet — continuity test recommended)
      fan.c              # TRIAC phase-angle fan control (ZCD ISR + esp_timer)
      adc.c              # ESP32-C3 ADC (adc_oneshot API, NTC channels)
      gpio.c             # GPIO out/in using ESP-IDF LL macros
      timer.c            # 1MHz gptimer, timer_dispatch_many in alarm callback
      console.c          # UART0 via uart_driver_install (CH340K bridge)
      autoconf.h         # Klipper config → ESP-IDF sdkconfig bridge
      [+ other board files copied from klipper_esp32]
    klipper/             # git submodule: nikhil-robinson/klipper (ESP32-adapted fork)
  printer.cfg.example    # Klipper [mcu panda_breath] + [heater_generic chamber] config
reference/               # local dev copies of reference repos (gitignored)
  klipper_esp32/         # nikhil-robinson/klipper_esp32 — upstream reference
  klipper/               # nikhil-robinson/klipper fork — ESP-IDF adapted Klipper MCU C
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
- [Klipper Router](https://github.com/paxx12/klipper-router) — JSON-RPC bridge for multi-instance Klipper setups (by paxx12); potential complement to KlipperMCU path
- [Klipper extras API reference](https://www.klipper3d.org/API_Server.html)
