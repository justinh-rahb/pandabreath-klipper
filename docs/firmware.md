# Firmware

> Analysis of all released firmware binaries and a historical v0.0.0 full flash dump.
> Tools: `esptool v5.2.0`, `strings -n 4`.
> No source code has been published by BTT.

---

## Version Summary

| Field | v0.0.0 | v1.0.1 | v1.0.2 | v1.0.3 | v1.0.4 |
|---|---|---|---|---|---|
| Size | 4MB (full flash) | 1,123,136 | 1,122,560 | 1,318,176 | 1,347,680 |
| Compile time | Aug 25 2025 | Dec 10 2025 | Jan 22 2026 | Feb 25 2026 | May 28 2026 |
| FW version string | — | — | — | V1.0.3 | V1.0.4 |
| Chip | ESP32-C3 | ESP32-C3 | ESP32-C3 | ESP32-C3 | ESP32-C3 |
| ESP-IDF | v5.1.4-dirty | v5.1.4-dirty | v5.1.4-dirty | v5.1.4-dirty | v5.1.4-dirty |
| String count | — | — | 7,320 | 11,201 | 11,669 |
| Secure boot | No | No | No | No | No |
| Flash encryption | No | No | No | No | No |

## Current stock-firmware note

The current release is **V1.0.4** (May 28 2026), which adds native MQTT with Home Assistant auto-discovery. Key version milestones:

- **V1.0.3** (Feb 2026) — added `printer_type` selector (BambuLab / Klipper), `filament_drying_mode` WS command, Bambu MQTT client, PTC sensor fault UI dialogs, responsive web UI improvements
- **V1.0.4** (May 2026) — added `btt_mqtt` client with HA auto-discovery (14 entities), HA broker bind/unbind UI, new WS fields (`target_temp`, `filter_temp`, `heater_temp`, `drying_running`, `drying_remaining_min`, `filament_button`, `chamber_temp`, `printer_bind/ip/name/sn`)

Use `1.0.3+` for the stock-firmware Klipper path, especially for native auto-mode workflows.

The `v0.0.0` material below remains relevant as reverse-engineering provenance, because the historical full-flash dump is still the richest source of embedded UI and protocol detail included in this repo.

---

## Partition Layout (v0.0.0)

| Partition | Type | Offset | Size |
|---|---|---|---|
| nvs | data/nvs | 0x9000 | 20K |
| otadata | data/otadata | 0xE000 | 8K |
| app0 | app/ota_0 | 0x10000 | 1920K |
| app1 | app/ota_1 | 0x1F0000 | 1920K |
| spiffs | data/fat | 0x3D0000 | 188K |
| coredump | data/coredump | 0x3FF000 | 4K |

On the v0.0.0 flash dump, the SPIFFS partition is fully erased (all `0xFF`). Web UI assets are embedded directly in the app binary's DROM segment, not in SPIFFS.

---

## RTOS Tasks

| Task name | Purpose | Since |
|---|---|---|
| `temp_task` | ADC polling for chamber and PTC sensors; pushes temperature over WebSocket | v1.0.1 |
| `ptc_task` | PTC heater PWM/relay duty-cycle control | v1.0.1 |
| `button_task` | Physical button handling with IRQ | v1.0.1 |
| `mqtt_task` | ESP MQTT client task (shared) | v1.0.1 |
| `bambu_mqtt` | Bambu printer MQTT connection | v1.0.1 |
| `bambu_udp` | Bambu printer discovery (UDP broadcast) | v1.0.3 |
| `btt_mqtt` | HA broker MQTT connection (auto-discovery) | v1.0.4 |
| `_mdns_service_task` | mDNS advertisement (`PandaBreath.local`) | v1.0.1 |
| `dns_server` | AP mode captive portal DNS server | v1.0.1 |

---

## HTTP Endpoints

| Endpoint | Notes |
|---|---|
| `/` | Web UI (assets embedded in firmware as compressed bundle) |
| `/ws` | WebSocket upgrade endpoint |
| `/ota` | OTA firmware update (HTTP POST) |
| `/generate_204` | Captive portal detection (Google connectivity check) |

WebSocket server confirmed via IDF httpd upgrade strings:
```
Upgrade: websocket
Sec-WebSocket-Version: 13
httpd_ws_respond_server_handshake
```

---

## NVS Storage Keys

Stored in ESP32 NVS flash under the `panda_breath` namespace:

| Key | Contents |
|---|---|
| `wifi_info` | `{hostname, sta.ssid, sta.password, ap.ssid, ap.password, ap.on}` |
| `bambu_mqtt_info` | `{name, sn, access_code, ip}` (Bambu printer binding) |
| `ha_mqtt_info` | `{ip, port, user, password}` (HA broker binding; v1.0.4+) |
| `ui_info` | UI/language settings |
| `settings_temp` | Target temperature |
| `settings_hotbed_temp` | Hotbed threshold for auto mode |
| `work_on` | Last on/off state |
| `current_mode` | Last operating mode |
| `custom_temp` | Custom mode temperature |
| `custom_timer` | Custom mode timer |

Save triggers: `NVS_REQ_SAVE_WIFI`, `NVS_REQ_SAVE_PANDA_BREATH`, `NVS_REQ_FACTORY_RESET`

---

## Key Differences Between Versions

### v1.0.1 → v1.0.2: Thermal protection removed

!!! warning "Thermal protection regression"
    v1.0.1 contained extensive PTC self-calibration and thermal runaway detection logic. **None of these strings appear in v1.0.2.**

Strings present in v1.0.1, absent in v1.0.2:
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

The self-calibration-on-first-heat described in v1.0.1 release notes was apparently removed or completely rewritten in v1.0.2.

### v1.0.2 → v1.0.3: Klipper support + major code growth

String count jumped from 7,320 to 11,201 (+53%). Key additions:

- **`printer_type` WS field** — `PRINTER_BBL = 1`, `PRINTER_KLIPPER = 2`; web UI dropdown with `['BambuLab', 'Klipper']` — controls communication mode only, does not change auto-mode behavior
- **`filament_drying_mode` writable** — WS commands for values 1 (PLA), 2 (PETG), 3 (custom)
- **Bambu MQTT client** — `bambu_mqtt` + `bambu_udp` tasks; reads `bed_target_temper`, `bed_temper`, `nozzle_temper`, `gcode_state`
- **`filter_temp` UI** — filter temperature threshold now editable
- **PTC sensor fault UI** — dialogs for `ptc_sensor_status` 1 (open circuit) and 2 (short circuit)

### v1.0.3 → v1.0.4: Native HA MQTT auto-discovery

Binary grew from 1,318,176 to 1,347,680 bytes (+29KB). Key additions:

- **`btt_mqtt` client** — independent MQTT connection to a user-configured HA broker
- **HA auto-discovery** — publishes `homeassistant/...` config topics for 14 entities (sensors, switches, selects, numbers)
- **HA bind UI** — web UI card with broker IP, port, username, password fields
- **`ha_mqtt_info` NVS key** — persists broker config across reboots
- **New WS/MQTT fields**: `target_temp` (0–60°C), `filter_temp` (0–120°C), `heater_temp` (40–120°C), `drying_running`, `drying_remaining_min`, `chamber_temp`, `filament_button`, `printer_bind/ip/name/sn`
- **MQTT topic structure**: `<prefix>/<id>/state`, `<prefix>/<id>/command`, `<prefix>/<id>/availability`

**Repository guidance:** use `1.0.3+` for the current OEM Klipper path. v1.0.4's `target_temp` MQTT entity may also work as a WS command key — needs live validation.

---

## v0.0.0 Full Flash Dump

File: `Panda_Breath/Firmware/0.0.0/0.0.0.0_clean.bin` — a full 4MB `esptool flash_read` from a real device running v0.0.0, factory reset before capture.

- Contains complete web UI JavaScript in the DROM segment
- This embedded JS is the **protocol source of truth** — it shows the exact field names and message formats the device uses
- SPIFFS partition is fully erased — web UI is not stored separately, it is part of the app binary
- v0.0.0 had a typo: default hostname was `PandaBreathe` (extra 'e') — fixed in later firmware

Key JS discoveries:

- `ws_send_data(root, members)` — root can be `'settings'`, `'wifi'`, `'sta'`, `'ap'`, `'printer'`
- `isrunning` field starts/stops drying cycle (1=start, 0=stop)
- Filament timer is in **hours** (converted to seconds client-side)
- Default drying time hardcoded: 12 hours
- `factory_reset: 1` and `reset: 1` are valid settings commands
- Multiple WS clients supported simultaneously

---

## Reverse Engineering Notes

- No TLS certificate pinning for Bambu MQTT — uses `rejectUnauthorized: false` equivalent (standard for Bambu)
- Web interface assets embedded as a compressed bundle (`zip_index.html` string visible)
- mDNS service registered as `PandaBreath` on `.local`
- AP mode SSID format: `Panda_Breath_%02X%02X%02X%02X%02X%02X` (MAC address-based)
- Default AP password: `987654321` (confirmed in BTT Wiki)
- No authentication on WebSocket — fully open on the local network

---

## Flashing

=== "macOS"
    ```sh
    esptool.py --chip esp32c3 --port /dev/cu.usbserial-XXXX --baud 460800 \
      write-flash 0x0 0.0.0.0_clean.bin
    ```
    Port will be `/dev/cu.usbserial-*` or `/dev/cu.wchusbserial*` (CH340K)

=== "Linux"
    ```sh
    esptool.py --chip esp32c3 --port /dev/ttyUSB0 --baud 460800 \
      write-flash 0x0 0.0.0.0_clean.bin
    ```

Full flash write starting at address `0x0` overwrites bootloader, partition table, app, and NVS.

**Bootloader mode:** Hold BOOT (K4/SW4) while pressing RESET, or use the auto-reset circuit via DTR/RTS (handled automatically by esptool with the CH340K).
