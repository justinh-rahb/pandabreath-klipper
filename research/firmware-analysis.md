# Panda Breath Firmware Binary Analysis

Binaries analyzed: `panda_breath_v1.0.1.bin`, `panda_breath_v1.0.2.bin`
Tool: `esptool v5.2.0`, `strings -n 4`

## Binary Metadata

| Field | v1.0.1 | v1.0.2 |
|---|---|---|
| Size | 1,123,136 bytes | 1,122,560 bytes |
| Chip | ESP32-C3 | ESP32-C3 |
| ESP-IDF | v5.1.4-dirty | v5.1.4-dirty |
| Entry point | 0x40380438 | 0x40380438 |
| Flash | 4MB, 80MHz, DIO | 4MB, 80MHz, DIO |
| App version string | `1` | `2f5dab0` (git hash) |
| Compile time | Dec 10 2025 18:11:15 | Jan 22 2026 11:18:24 |
| Project name | `panda_breath` | `panda_breath` |

Both images are **unsigned, no secure boot, no flash encryption**. OTA is via plain HTTP upload (`/ota` endpoint).

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

| Task name | Purpose |
|---|---|
| `temp_task` | ADC polling for chamber and PTC sensors |
| `ptc_task` | PTC heater PWM control |
| `button_task` | Physical button handling with IRQ |
| `mqtt_task` | Bambu MQTT client |
| `bambu_mqtt` | Bambu printer MQTT connection |
| `bambu_udp` | Bambu printer discovery (UDP) |
| `_mdns_service_task` | mDNS advertisement (`PandaBreath.local`) |
| `dns_server` | AP mode captive portal DNS server |

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
- `wifi_info` — WiFi credentials (SSID, password)
- `bambu_mqtt_info` — printer serial + access code
- `ui_info` — UI settings

## Key Difference: v1.0.1 vs v1.0.2

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

- [ ] Connect to a live device and probe all undocumented fields via WebSocket
- [ ] Test whether `set_temp` vs `temp` is the correct writable field for target temperature
- [ ] Test `filament_timer`, `custom_temp`, `custom_timer`, `remaining_seconds` behavior
- [ ] Determine if `filtertemp` is a threshold setting or a sensor reading
- [ ] Dump web UI assets from the device (`/` HTTP endpoint) to understand the full control API
- [ ] Test WebSocket reconnection behavior and message rate
- [ ] Sniff OTA update flow to understand if there's a version check mechanism
