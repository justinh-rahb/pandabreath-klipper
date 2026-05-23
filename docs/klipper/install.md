# Install the Klipper Module

## Prerequisites

- A Klipper host with access to its `klippy/extras/` directory
- A BIQU Panda Breath on your network
- For `firmware: stock`: a hostname or IP your Klipper host can resolve
- For `firmware: esphome`: an MQTT broker reachable by both the device and the Klipper host

## Step 1: Run the installer

`panda_breath.py` uses only Python standard library modules. No package installation is required.

On a MainsailOS-style host, run from this repository:

```sh
./install.sh --host PandaBreath.local
sudo systemctl restart klipper
```

The installer copies `panda_breath.py` to Klipper's `extras/` directory, writes
`panda_breath.cfg`, and adds `[include panda_breath.cfg]` to `printer.cfg`.
By default it targets:

- `~/klipper/klippy/extras/`
- `~/printer_data/config/panda_breath.cfg`
- `~/printer_data/config/printer.cfg`

The generated `panda_breath.cfg` is rendered from the source fragments in
`config/`, which can also be copied manually or reused by downstream packages.
Those fragments are split into stock, ESPHome, heater, and macro blocks. M141
and M191 compatibility macros are included by default; use `--no-macros` for a
minimal fragment.

For stock firmware, the installer also binds the Panda Breath to this Klipper
host by default. If the host has multiple network interfaces, pass
`--printer-ip` explicitly. Use `--no-bind` for a config-only install.

Useful options:

```sh
# Preview without writing anything
./install.sh --host 192.168.1.50 --dry-run

# Install on a host with non-standard paths
./install.sh \
  --host 192.168.1.50 \
  --klipper-dir /home/pi/klipper \
  --config-dir /home/pi/printer_data/config

# ESPHome firmware path
./install.sh \
  --firmware esphome \
  --mqtt-broker 192.168.1.10 \
  --mqtt-topic-prefix panda-breath

# Install without M141/M191 compatibility macros
./install.sh --host PandaBreath.local --no-macros

# Bind to a specific Klipper host address
./install.sh --host PandaBreath.local --printer-ip 192.168.1.25

# Install files/config only, without device binding
./install.sh --host PandaBreath.local --no-bind
```

The old manual path still works if you prefer to manage config yourself. Copy
the file into your Klipper `extras/` directory. Common locations include:

- `/home/pi/klipper/klippy/extras/`
- `/home/mks/klipper/klippy/extras/`
- `/home/lava/klipper/klippy/extras/`

Example:

```sh
cp panda_breath.py /path/to/klipper/klippy/extras/
```

## Step 2: Add or review `printer.cfg` sections

Use the heater name `panda_breath`. The module hooks that heater by name.

If you used the installer, these sections are in `panda_breath.cfg` and your
`printer.cfg` should contain `[include panda_breath.cfg]`.

=== "Stock firmware"

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

    !!! tip
        Use OEM firmware `1.0.3+` for the current stock-firmware Klipper path. BTT's Panda Breath wiki lists `V1.0.3` as adding Klipper printer binding support.

=== "ESPHome firmware"

    ```ini
    [panda_breath]
    firmware: esphome
    mqtt_broker: 192.168.1.10
    mqtt_port: 1883
    mqtt_topic_prefix: panda-breath

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

## Step 3: Restart Klipper

Restart Klipper using your normal service manager or web UI.

## Step 4: Verify

Look in `klippy.log` for a connection message:

=== "Stock firmware"

    ```
    panda_breath: WebSocket connected to PandaBreath.local:80
    ```

=== "ESPHome firmware"

    ```
    panda_breath: MQTT connected to 192.168.1.10:1883
    ```

Then test the normal heater path:

```gcode
SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=45
SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=0
```

Temperature should begin updating once the device pushes its first reading.

## Optional stock-only commands

If you are using OEM stock firmware, the module also exposes:

- `PANDA_BREATH_AUTO ENABLE=<0|1> TARGET=<C> FILTERTEMP=<C> HOTBEDTEMP=<C>`
- `PANDA_BREATH_DRY_START TEMP=<C> HOURS=<1-12>`
- `PANDA_BREATH_DRY_STOP`

These are optional advanced controls. They are not needed for basic Klipper heater operation.

For native auto-mode workflows on stock firmware, prefer `1.0.3+`.

The installer runs the binding command by default for stock firmware. The
separate Python CLI can still query, rebind, or unbind manually:

```sh
python3 panda_breath_cli.py version --host PandaBreath.local
python3 panda_breath_cli.py bind-klipper --host PandaBreath.local --printer-ip 192.168.1.25
python3 panda_breath_cli.py unbind --host PandaBreath.local
```

`bind-klipper` requires stock firmware `V1.0.3` or newer by default. The module's
basic `heater_generic` control does not require using this binding command.

## Troubleshooting

**Stock firmware connection issues**

- Verify the Panda Breath is reachable from the Klipper host.
- If `PandaBreath.local` does not resolve on your system, use the device IP directly.
- If the device is not on WiFi, it falls back to AP mode at `192.168.254.1`.

**ESPHome MQTT issues**

- Verify `mqtt_broker` points to the broker, not the Panda Breath.
- Confirm the broker is reachable from both the device and the Klipper host.
- Confirm `mqtt_topic_prefix` matches the ESPHome config.

**Temperature does not update**

- Stock: the device pushes readings periodically; no manual poll command is required.
- ESPHome: confirm the broker is receiving `.../sensor/chamber_temperature/state`.

**The heater appears but control is inconsistent**

- Make sure the heater section is named `[heater_generic panda_breath]`.
- Make sure `heater_pin` is `panda_breath:pwm` and `sensor_type` is `panda_breath`.
- Remove stale copies of older `panda_breath.py` files if more than one exists on the host.
