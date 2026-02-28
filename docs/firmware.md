# Firmware

> Analysis of `panda_breath_v1.0.1.bin`, `panda_breath_v1.0.2.bin`, and the v0.0.0 full flash dump.
> Tools: `esptool v5.2.0`, `strings -n 4`.
> No source code has been published by BTT.

---

## Version Summary

| Field | v0.0.0 | v1.0.1 | v1.0.2 |
|---|---|---|---|
| Size | 4MB (full flash) | 1,123,136 bytes | 1,122,560 bytes |
| Compile time | Aug 25 2025 14:26:17 | Dec 10 2025 18:11:15 | Jan 22 2026 11:18:24 |
| App version string | *(not extracted)* | `1` | `2f5dab0` (git hash) |
| Chip | ESP32-C3 | ESP32-C3 | ESP32-C3 |
| ESP-IDF | v5.1.4-dirty | v5.1.4-dirty | v5.1.4-dirty |
| Entry point | — | `0x40380438` | `0x40380438` |
| Flash | — | 4MB, 80MHz, DIO | 4MB, 80MHz, DIO |
| Secure boot | No | No | No |
| Flash encryption | No | No | No |

**v0.0.0 (Aug 2025) is the only community-confirmed stable release.**

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

| Task name | Purpose |
|---|---|
| `temp_task` | ADC polling for chamber and PTC sensors; pushes temperature over WebSocket |
| `ptc_task` | PTC heater PWM/relay duty-cycle control |
| `button_task` | Physical button handling with IRQ |
| `mqtt_task` | Bambu MQTT client |
| `bambu_mqtt` | Bambu printer MQTT connection |
| `bambu_udp` | Bambu printer discovery (UDP broadcast) |
| `_mdns_service_task` | mDNS advertisement (`PandaBreath.local`) |
| `dns_server` | AP mode captive portal DNS server |

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
| `ui_info` | UI/language settings |
| `settings_temp` | Target temperature |
| `settings_hotbed_temp` | Hotbed threshold for auto mode |
| `work_on` | Last on/off state |
| `current_mode` | Last operating mode |
| `custom_temp` | Custom mode temperature |
| `custom_timer` | Custom mode timer |

Save triggers: `NVS_REQ_SAVE_WIFI`, `NVS_REQ_SAVE_PANDA_BREATH`, `NVS_REQ_FACTORY_RESET`

---

## v1.0.1 → v1.0.2 Key Difference

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

The self-calibration-on-first-heat described in v1.0.1 release notes was apparently removed or completely rewritten in v1.0.2. Community members report v1.0.2 is still considered buggy — the thermal protection may have regressed rather than improved.

**Use v0.0.0 until a stable v1.x release is confirmed.**

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
