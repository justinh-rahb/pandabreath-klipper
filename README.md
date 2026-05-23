# pandabreath-klipper

Klipper integration and firmware research for the **BIQU Panda Breath** smart chamber heater and air filter.

## What this repo provides

The [BIQU Panda Breath](https://biqu.equipment/products/biqu-panda-breath-smart-air-filtration-and-heating-system-with-precise-temperature-regulation) is a 300W chamber heater and air filter with OEM WiFi control, but no official Klipper support. The primary supported path in this repository is the stock OEM firmware plus `panda_breath.py`. Two additional reflash directions exist, but both remain experimental:

| Path | Device firmware | Klipper side | Notes |
|---|---|---|---|
| Stock | OEM firmware | `panda_breath.py` | Current practical path |
| ESPHome | ESPHome reflash | `panda_breath.py` | Incomplete and untested |
| KlipperMCU | Custom ESP-IDF reflash | Native `[mcu]` | Exploratory and mostly theoretical right now |

For the stock and ESPHome paths, `panda_breath.py` registers:

- a custom `sensor_type: panda_breath`
- a virtual `heater_pin: panda_breath:pwm`

You still define the actual `[heater_generic panda_breath]` in `printer.cfg`.

## Status

- [x] Protocol reverse-engineered from firmware strings, live OEM behavior, and full flash analysis
- [x] Klipper extras module for the stock WebSocket transport
- [x] Optional stock-firmware passthrough commands for native auto and drying modes
- [ ] ESPHome reflash path is unfinished, untested, and currently de-emphasized
- [ ] Native KlipperMCU reflash path is still exploratory and untested

## Quick start

On a generic Klipper host such as MainsailOS, clone or copy this repository onto
the printer host, then run:

```sh
./install.sh --host PandaBreath.local
sudo systemctl restart klipper
```

The installer defaults to MainsailOS-style paths:

- `~/klipper/klippy/extras/panda_breath.py`
- `~/printer_data/config/panda_breath.cfg`
- `~/printer_data/config/printer.cfg`

Use `./install.sh --dry-run` first to preview changes, or pass `--klipper-dir`,
`--extras-dir`, `--config-dir`, or `--printer-cfg` for non-standard hosts.
The generated Klipper fragment is rendered from the templates in [`config/`](config/).
M141/M191 compatibility macros are included by default; pass `--no-macros`
for only the device and heater sections.

For stock firmware, `install.sh` also binds the Panda Breath to the Klipper host
by default. If the host has multiple network interfaces, pass `--printer-ip`.
Use `--no-bind` for a config-only install.

Manual install is still just:

1. Copy [`panda_breath.py`](panda_breath.py) into your Klipper `extras/` directory.
2. Add one `[panda_breath]` section plus one matching `[heater_generic panda_breath]` section.
3. Restart Klipper.

### Stock firmware

```ini
[panda_breath]
firmware: stock
host: PandaBreath.local   # or an IP / hostname your Klipper host can resolve
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
```

### ESPHome firmware (experimental)

```ini
; Experimental path — not fully fleshed out or validated
[panda_breath]
firmware: esphome
mqtt_broker: 192.168.1.10
mqtt_port: 1883
mqtt_topic_prefix: panda-breath
```

The baseline control path is standard Klipper heater control:

```gcode
SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=45
SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=0
```

## Stock-only optional commands

Recent commits added passthrough commands for OEM native modes:

- `PANDA_BREATH_AUTO ENABLE=<0|1> TARGET=<C> FILTERTEMP=<C> HOTBEDTEMP=<C>`
- `PANDA_BREATH_DRY_START TEMP=<C> HOURS=<1-12>`
- `PANDA_BREATH_DRY_STOP`

These are optional advanced controls for the stock transport. The broadest-compatibility Klipper path remains normal `heater_generic` control in `work_mode: 2`.

For current OEM firmware, BTT's Panda Breath wiki lists `V1.0.3` as adding the ability to bind Klipper printers. Use `1.0.3+` for stock-firmware native auto-mode workflows.

The stock-firmware maintenance CLI can be used for manual rebinds or unbinds:

```sh
python3 panda_breath_cli.py version --host PandaBreath.local
python3 panda_breath_cli.py bind-klipper --host PandaBreath.local --printer-ip 192.168.1.25
python3 panda_breath_cli.py unbind --host PandaBreath.local
```

## Notes on actual module behaviour

- The stock transport connects to `ws://<host>:<port>/ws`.
- The module prefers `cal_warehouse_temp` and falls back to `warehouse_temper`.
- On forced-off events, the module explicitly turns the device off on Klipper connect, disconnect, and shutdown.
- The module resends its last desired state after reconnect.
- Stock firmware host resolution is generic socket resolution. IPs, DNS names, and mDNS names can work if the Klipper host can resolve them.

## Documentation

- [Docs site home](docs/index.md)
- [Klipper integration overview](docs/klipper/index.md)
- [Klipper install guide](docs/klipper/install.md)
- [`printer.cfg` reference](docs/klipper/printer-cfg.md)
- [ESPHome path (experimental)](docs/esphome/index.md)
- [KlipperMCU path (exploratory)](docs/klipper-mcu/index.md)
- [Protocol reference](docs/protocol.md)
- [Firmware analysis](docs/firmware.md)
- [Hardware notes](docs/hardware.md)

## Downstream integrations

This repository is the upstream source for downstream firmware integrations. Those downstream projects may add higher-level UX, mode selectors, macros, or appliance-specific packaging on top of the module here.

## Device notes

- Use OEM firmware `1.0.3+` for the current stock-firmware Klipper path, especially if you want native auto-mode support.
- Earlier analysis in this repo found regression signals in `v1.0.2`, including apparent removal of some PTC thermal-protection logic.
- The stock WebSocket API has no authentication.
- Physical button and web UI state changes do not reliably produce full state push updates to Klipper.

[![Buy Me A Coffee](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/wildtang3nt)

## License

This project code and documentation are licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).

The BIQU Panda Breath hardware and OEM firmware are © 2025 BIQU and remain under their respective licenses.
