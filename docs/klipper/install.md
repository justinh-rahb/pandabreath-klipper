# Install the Klipper Module

## Prerequisites

- A Klipper host with access to its `klippy/extras/` directory
- A BIQU Panda Breath on your network
- For `firmware: stock`: a hostname or IP your Klipper host can resolve
- For `firmware: esphome`: an MQTT broker reachable by both the device and the Klipper host

## Step 1: Copy `panda_breath.py`

`panda_breath.py` uses only Python standard library modules. No package installation is required.

Copy the file into your Klipper `extras/` directory. Common locations include:

- `/home/pi/klipper/klippy/extras/`
- `/home/mks/klipper/klippy/extras/`
- `/home/lava/klipper/klippy/extras/`

Example:

```sh
cp panda_breath.py /path/to/klipper/klippy/extras/
```

## Step 2: Add `printer.cfg` sections

Use the heater name `panda_breath`. The module hooks that heater by name.

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
