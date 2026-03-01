# Install on Snapmaker U1

---

## Prerequisites

- Snapmaker U1 running the [community extended firmware](https://snapmakeru1-extended-firmware.pages.dev)
- SSH access to the U1
- BIQU Panda Breath connected to your WiFi network
- Panda Breath IP address or mDNS hostname (`PandaBreath.local`)
- If using ESPHome firmware path: an MQTT broker reachable by both the Panda Breath and the U1

### U1 SSH credentials

| User | Password |
|---|---|
| `root` | `snapmaker` |
| `lava` | `snapmaker` |

```sh
ssh lava@<u1-ip>
```

---

## Step 1: Copy the Klipper extra

`panda_breath.py` has no external Python dependencies — it uses only the standard library. No package installation is required.

Copy the file to the Klipper extras directory from your workstation:

```sh
scp panda_breath.py lava@<u1-ip>:/home/lava/klipper/klippy/extras/
```

Or directly on the device:

```sh
cp panda_breath.py /home/lava/klipper/klippy/extras/
```

---

## Step 2: Configure `printer.cfg`

Add one of the following sections depending on which firmware your Panda Breath is running.

=== "Stock firmware (OEM v0.0.0)"

    ```ini
    [panda_breath]
    firmware: stock
    host: PandaBreath.local   # or IP address
    port: 80
    ```

    !!! tip "Recommended firmware"
        Use OEM v0.0.0 — it is the only confirmed stable release. v1.0.1+ have thermal regression bugs and v1.0.2 silently removed PTC thermal runaway detection. See [Firmware](../firmware.md).

=== "ESPHome firmware"

    ```ini
    [panda_breath]
    firmware: esphome
    mqtt_broker: 192.168.1.x   # IP of your MQTT broker
    mqtt_port: 1883
    mqtt_topic_prefix: panda-breath
    ```

    An MQTT broker (e.g. Mosquitto) must be reachable from both the Panda Breath and the U1. See [ESPHome](../esphome/index.md) for setup details.

The module registers itself as a Klipper heater named `panda_breath`. No additional `[heater_generic]` or `[temperature_sensor]` blocks are needed.

---

## Step 3: Restart Klipper

```sh
sudo systemctl restart klipper
```

Or use the Fluidd/Mainsail UI to restart the Klipper service.

---

## Step 4: Verify

In the Klipper log (`/tmp/klippy.log`), you should see a connection message within a few seconds:

=== "Stock firmware"

    ```
    panda_breath: WebSocket connected to PandaBreath.local:80
    ```

=== "ESPHome firmware"

    ```
    panda_breath: MQTT connected to 192.168.1.x:1883
    ```

In Fluidd/Mainsail, the Panda Breath should appear as a temperature sensor and heater. Chamber temperature will populate once the device's `temp_task` pushes its first reading (typically within 5 seconds of connection).

---

## Orca Slicer integration

Orca Slicer sets chamber temperature automatically based on the filament profile. In your filament profile, set the **Chamber temperature** field. Orca will emit:

```gcode
SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=45
```

No custom GCode or printer profile changes are needed beyond ensuring `panda_breath` is registered as a heater in Klipper.

---

## Troubleshooting

**Device not found / connection refused (stock firmware)**

- Verify the device is on your WiFi: `ping PandaBreath.local`
- Try the IP address directly instead of the mDNS hostname — mDNS can be unreliable on some networks
- If the device isn't on WiFi, it falls back to AP mode: SSID `Panda_Breath_XXXXXXXXXX`, password `987654321`, IP `192.168.254.1`

**MQTT connection refused (ESPHome firmware)**

- Verify the broker is running and reachable from the U1: `mosquitto_pub -h <broker-ip> -t test -m hello`
- Check `mqtt_broker` in `printer.cfg` is the broker IP, not the Panda Breath IP
- Confirm the ESPHome device is connected to WiFi and the broker address in `esphome/panda_breath.yaml` matches

**Temperature stuck at 0 or not updating**

- Stock: temperature is pushed periodically by the device's `temp_task`. If the WebSocket connects but no temperature arrives within ~30 seconds, check that the Panda Breath is running v0.0.0 — v1.0.1+ may have regressions. See [Firmware](../firmware.md).
- ESPHome: check that ESPHome is publishing to `panda-breath/sensor/chamber_temperature/state` — verify with `mosquitto_sub -h <broker> -t 'panda-breath/#' -v`

**Heater turns on but chamber doesn't heat**

- Confirm mains AC is connected and the main power switch on the Panda Breath is on
- The device manages all internal heater relay duty-cycling; the module only sends `work_on: true`

**`ImportError` or `AttributeError` on Klipper start**

- Verify the file was copied to the correct path: `/home/lava/klipper/klippy/extras/panda_breath.py`
- Confirm there are no leftover `*.pyc` files from a different Python version in the same directory
