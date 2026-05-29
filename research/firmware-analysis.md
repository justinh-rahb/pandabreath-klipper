# Panda Breath Firmware Binary Analysis

Binaries analyzed: `panda_breath_v1.0.1.bin` through `panda_breath_v1.0.4.bin`
Tool: `esptool v5.2.0`, `strings -n 4`

## Binary Metadata

| Field | v0.0.0 | v1.0.1 | v1.0.2 | v1.0.3 | v1.0.4 |
|---|---|---|---|---|---|
| Size | Full flash (4MB) | 1,123,136 B | 1,122,560 B | 1,318,176 B (+17%) | 1,347,680 B (+2.2%) |
| Chip | ESP32-C3 | ESP32-C3 | ESP32-C3 | ESP32-C3 | ESP32-C3 |
| ESP-IDF | v5.1.4-dirty | v5.1.4-dirty | v5.1.4-dirty | v5.1.4-dirty | v5.1.4-dirty |
| Compile time | Aug 25 2025 | Dec 10 2025 | Jan 22 2026 | Mar 2026 | May 2026 |
| String count | N/A (embedded JS) | ~7,320 | ~7,320 | ~11,201 (+53%) | ~11,669 |
| Project name | `panda_breath` | `panda_breath` | `panda_breath` | `panda_breath` | `panda_breath` |

All images are **unsigned, no secure boot, no flash encryption**. OTA is via plain HTTP upload (`/ota` endpoint).

**Chip correction:** The device uses an **ESP32-C3** (not ESP32-C3-Mini as previously noted in some docs). Community-confirmed.

## WebSocket Protocol Fields (from strings)

All fields confirmed present in both versions. All appear under a `settings` JSON envelope.

### Fields confirmed from binary

| Field | Direction | Type | Notes |
|---|---|---|---|
| `settings` | both | object | top-level envelope for all messages |
| `work_on` | both | bool | power enable/disable |
| `work_mode` | both | int | 1=auto, 2=always_on, 3=filament_drying |
| `warehouse_temper` | device→client | float | current chamber temperature (°C) |
| `filtertemp` | ? | int/float | **UNDOCUMENTED** — filter temperature |
| `hotbedtemp` | both | int | auto mode trigger: bed temp threshold |
| `filament_temp` | ? | int | **UNDOCUMENTED** — filament drying target temp |
| `filament_timer` | ? | int | **UNDOCUMENTED** — filament drying timer duration |
| `filament_drying_mode` | ? | bool/int | **UNDOCUMENTED** — filament drying active flag |
| `set_temp` | client→device | int | **UNDOCUMENTED** — likely the writable target temp setter (vs `temp` which may be read-only) |
| `custom_temp` | ? | int | **UNDOCUMENTED** — custom temperature value |
| `custom_timer` | ? | int | **UNDOCUMENTED** — custom timer value |
| `remaining_seconds` | device→client | int | **UNDOCUMENTED** — countdown timer (filament drying?) |
| `fw_version` | device→client | string | **UNDOCUMENTED** — firmware version string |
| `set_ap` | client→device | ? | **UNDOCUMENTED** — trigger AP mode? |
| `app_temp` | ? | int | **UNDOCUMENTED** — unclear distinction from other temps |

### Status/telemetry fields

| Field | Type | Notes |
|---|---|---|
| `ptc_sensor_status` | int/bool | PTC thermistor sensor health status |
| `warehouse_sensor_status` | int/bool | Chamber thermistor sensor health status |
| `ptc_heater_status` | int/bool | PTC heater element status |
| `cal_ptc_temp` | float | Calibrated PTC temperature reading |
| `cal_warehouse_temp` | float | Calibrated chamber temperature reading |

### Printer binding fields (received via Bambu MQTT)

The device connects to the printer via **MQTT over TLS** (`mqtts`) using Bambu Lab's protocol.
It subscribes to `device/<serial>/report` and publishes to `device/<serial>/request`.

Fields received from printer and used for auto mode logic:

| Field | Notes |
|---|---|
| `nozzle_temper` | Nozzle temperature from printer |
| `bed_temper` | Bed current temperature from printer |
| `bed_target_temper` | Bed target temperature from printer |
| `gcode_state` | Print state (idle/printing/paused/etc) |
| `ams_status` | AMS filament system status |
| `chamber_light` | Chamber light state |
| `print_error` | Print error code |

**Implication for Klipper integration:** For the Panda Breath's auto mode to work with Klipper, the Klipper module must either:
1. Send bed/nozzle temperature data to the device via WebSocket (if supported), OR
2. Implement the auto trigger logic in the Klipper module itself (watch `heater_bed.temperature` and send `work_on`/`work_off` commands directly), OR
3. Keep the device in `work_mode: 2` (always_on) and let Klipper control it fully

Option 3 is the most reliable given that the Bambu MQTT integration won't work on Klipper.

## RTOS Tasks

| Task name | Version | Purpose |
|---|---|---|
| `temp_task` | all | ADC polling for chamber and PTC sensors |
| `ptc_task` | all | PTC heater PWM control |
| `button_task` | all | Physical button handling with IRQ |
| `mqtt_task` | all | Bambu MQTT client task |
| `bambu_mqtt` | v1.0.3+ | Bambu printer MQTT connection (renamed/split from `mqtt_task`) |
| `bambu_udp` | v1.0.3+ | Bambu printer discovery (UDP broadcast) |
| `btt_mqtt` | v1.0.4+ | Native HA MQTT client (independent of Bambu MQTT) |
| `_mdns_service_task` | all | mDNS advertisement (`PandaBreath.local`) |
| `dns_server` | all | AP mode captive portal DNS server |

## HTTP Server Endpoints (from strings)

| Endpoint | Notes |
|---|---|
| `/ota` | OTA firmware update upload |
| `/generate_204` | Captive portal detection (Google connectivity check) |
| `zip_index.html` | Suggests web UI assets are stored as a gzip/zip bundle |

WebSocket server is confirmed via ESP32 IDF httpd websocket upgrade strings:
```
Upgrade: websocket
Sec-WebSocket-Version: 13
httpd_ws_respond_server_handshake
```

## Storage

Uses **NVS (Non-Volatile Storage)** via `app_nvs` for:
- `wifi_info` — WiFi credentials (SSID, password, hostname, AP config)
- `bambu_mqtt_info` — printer name, serial, access code, IP
- `ha_mqtt_info` — HA MQTT broker IP, port, username, password (v1.0.4+)
- `ui_info` — language and UI settings
- `panda_breath` namespace — `settings_temp`, `settings_hotbed_temp`, `work_on`, `current_mode`, `custom_temp`, `custom_timer`

## Version Diffs

### v1.0.1 → v1.0.2: PTC thermal detection removed

v1.0.1 contained extensive PTC self-calibration/thermal runaway detection logic with debug strings:
```
PTC heating stopped, reset detect status
PTC heating start detect, start temp: %d, start time: %lldms
ptc heating detect finished, start temp: %d, current temp: %d, rise: %d
warehouse heating detect finished, ...
ntc sensor installation error
ntc sensor installation normal
PTC heating abnormal: temp rise too low (%d < %d) !!!
PTC heating normal: temp rise %d
Sensor abnormal, reset PTC heating detect
```

**None of these strings appear in v1.0.2.** The self-calibration on first heat (which V1.0.1 release notes mentioned) was apparently removed or completely rewritten in v1.0.2, possibly explaining why v1.0.2 is still considered buggy by community members — the thermal protection may have regressed.

### v1.0.2 → v1.0.3: Klipper support, drying modes, PTC fault UI (+53% string growth)

Binary size jumped from 1,122,560 to 1,318,176 bytes (+17%). String count grew from ~7,320 to ~11,201 (+53%).

**New features identified via `diff strings_v1.0.2.txt strings_v1.0.3.txt`:**
- `printer_type` field: `1` = BambuLab, `2` = Klipper — controls how the device communicates to the host (does not change auto-mode behavior)
- `filament_drying_mode` writable: `1` = PLA, `2` = PETG, `3` = custom
- PTC sensor fault detection UI dialogs restored: `ptc_sensor_status` values 0=OK, 1=open circuit, 2=short circuit
- `filter_temp` editable in web UI
- Embedded web UI JavaScript now visible in binary strings (complete control flow, field handlers, data types)
- `bambu_mqtt` and `bambu_udp` task names appear (Bambu client split/rename)
- Bambu printer binding UI refinements

**Open question:** PTC sensor fault *detection* UI was re-added, but it's unclear if the actual thermal *cutoff* logic (removed in v1.0.2) was fully restored.

### v1.0.3 → v1.0.4: Native HA MQTT auto-discovery (+2.2% growth)

Binary size grew from 1,318,176 to 1,347,680 bytes (+2.2%). String count: ~11,201 to ~11,669.

**New features identified via `diff strings_v1.0.3.txt strings_v1.0.4.txt`:**
- `btt_mqtt` RTOS task: native HA MQTT client, independent of the Bambu `bambu_mqtt` client
- Home Assistant auto-discovery payloads published to `homeassistant/...` topics
- 14 HA entities with full definitions: `chamber_temp`, `work_on`, `mode`, `filament_drying_mode`, `target_temp` (0–60°C), `filter_temp` (0–120°C), `heater_temp` (40–120°C), `custom_temp` (40–60°C), `custom_timer` (1–99h), `drying_running`, `drying_remaining_min`, `printer_sn`, `printer_bind`, `printer_ip`, `printer_name`
- MQTT topic structure: `<prefix>/<device_id>/state`, `<prefix>/<device_id>/command`, `<prefix>/<device_id>/availability` (LWT)
- `ha_mqtt_info` NVS key for broker credentials
- New WS/MQTT fields: `target_temp`, `filter_temp`, `heater_temp`, `drying_running`, `drying_remaining_min`, `filament_button`, `chamber_temp`, `printer_bind`, `printer_ip`, `printer_name`, `printer_sn`
- HA MQTT broker bind UI in web interface

**Impact:** v1.0.4's native HA MQTT auto-discovery makes the ESPHome reflash path largely redundant for Home Assistant users. The Klipper stock transport now keeps the confirmed legacy WebSocket keys and mirrors compatible v1.0.4 aliases (`target_temp`, `filter_temp`, `drying_running`); live validation is still needed before replacing the legacy keys.

## Reverse Engineering Notes

- No TLS certificate pinning visible for Bambu MQTT — uses `rejectUnauthorized: false` equivalent (standard for Bambu)
- Web interface assets appear embedded as a compressed bundle (`zip_index.html` string)
- mDNS service registered as `PandaBreath` on `.local`
- AP mode SSID format: `Panda_Breath_%02X%02X%02X%02X%02X%02X` (MAC-based)
- Default AP password is `987654321` (confirmed in BTT Wiki, visible via AP behavior)
- No authentication on WebSocket — the WS endpoint is fully open on the local network

## Flashing

To flash a full image (e.g., the v0.0.0 clean dump) to a real device over USB-C:

```sh
esptool.py --chip esp32c3 --port /dev/ttyUSB0 --baud 460800 write-flash 0x00000 0.0.0.0_clean.bin
```

- Full flash write starting at address `0x00000` (overwrites bootloader, partition table, app, NVS — everything)
- On macOS the port will likely be `/dev/cu.usbserial-*` or `/dev/cu.wchusbserial*` (CH340K)
- Device must be in bootloader mode: hold BOOT (K4/SW4) while pressing RESET, or use the auto-reset circuit via DTR/RTS

## v0.0.0 Full Flash Dump

File: `Panda_Breath/Firmware/0.0.0/0.0.0.0_clean.bin` — a full 4MB `esptool flash_read` from a real device running V0.0.0, factory reset before capture.

- Compile date: **Aug 25 2025** (older than v1.0.1's Dec 2025)
- The SPIFFS partition is fully erased (all 0xFF) — web UI assets are embedded directly in the app binary
- Contains complete web UI JavaScript in the DROM segment — this is the **protocol source of truth**
- See `protocol-from-v0.0.0.md` for full extracted protocol documentation

Key discoveries from the embedded JS:
- `ws_send_data(root, members)` — root can be `'settings'`, `'wifi'`, `'sta'`, `'ap'`, `'printer'`
- `isrunning` field starts/stops drying cycle (1=start, 0=stop)
- Filament timer is in **hours** (converted to seconds client-side)
- Default drying time hardcoded: 12 hours
- `factory_reset: 1` and `reset: 1` are valid settings commands
- Multiple WS clients supported simultaneously
- v0.0.0 had a typo: hostname default was `PandaBreathe` (extra 'e') — fixed in later firmware

## Next Steps for Protocol Research

### Resolved via binary analysis or live testing

- [x] `set_temp` is the writable target temperature key; `temp` is ignored (confirmed live)
- [x] `filtertemp` is a filter temperature threshold (editable via `filter_temp` in v1.0.3+ UI)
- [x] `filament_drying_mode` is writable: 1=PLA, 2=PETG, 3=custom (v1.0.3+ embedded JS)
- [x] `ptc_sensor_status` values: 0=OK, 1=open circuit, 2=short circuit (v1.0.3+ UI dialogs)
- [x] Web UI control flow extracted from v0.0.0 embedded JS and v1.0.3+ binary strings

### Pending — needs live device testing

- [ ] Does `target_temp` work as a WS command key on v1.0.4? (confirmed as HA MQTT entity 0–60°C; may supersede `set_temp`)
- [ ] Do `filter_temp` and `heater_temp` work as WS command keys? (confirmed as HA entities)
- [ ] Does `drying_running` ON/OFF work as a WS alternative to `isrunning`?
- [ ] Does the device push an initial state snapshot on new client connect? (`init one:` pattern in firmware strings)
- [ ] Is PTC thermal cutoff logic actually restored in v1.0.3+? (UI dialogs exist but cutoff uncertain)
- [ ] What does `filament_button` state field report? (appears to be physical button state, values 1/2/3)
- [ ] What is the WebSocket message rate for temperature updates?
- [ ] Does v1.0.4 HA MQTT work end-to-end with an external broker?
- [ ] Is there a version check or rollback prevention in the OTA flow?
