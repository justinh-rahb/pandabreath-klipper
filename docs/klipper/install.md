# Install on Snapmaker U1

!!! warning "Module not yet written"
    `panda_breath.py` is still in development. These instructions describe the planned installation procedure for when it is ready.

---

## Prerequisites

- Snapmaker U1 running the [community extended firmware](https://snapmakeru1-extended-firmware.pages.dev) (devel build for development; basic or extended for production)
- SSH access to the U1
- BIQU Panda Breath connected to your WiFi network
- Panda Breath IP address or mDNS hostname (`PandaBreath.local`)

### U1 SSH credentials

| User | Password |
|---|---|
| `root` | `snapmaker` |
| `lava` | `snapmaker` |

```sh
ssh lava@<u1-ip>
```

---

## Step 1: Install the Python WebSocket library

The `websocket-client` package is not included in stock Klipper. On a devel extended firmware build, opkg/entware is available:

```sh
opkg install python3-websocket
```

On production builds, the package must be included in the firmware overlay. See the [U1 extended firmware development docs](https://snapmakeru1-extended-firmware.pages.dev/development) for overlay build instructions.

---

## Step 2: Install the Klipper extra

Copy `panda_breath.py` to the Klipper extras directory:

```sh
# From your workstation
scp panda_breath.py lava@<u1-ip>:/home/lava/klipper/klippy/extras/
```

Or on the device directly if you have the file there:

```sh
cp panda_breath.py /home/lava/klipper/klippy/extras/
```

---

## Step 3: Configure `printer.cfg`

Add the following section to your `printer.cfg`:

```ini
[panda_breath]
host: PandaBreath.local   # or use the IP address directly
port: 80
```

Then reference it as a heater in your temperature fan, macros, or print start GCode:

```ini
# Example: treat as a standard chamber heater
[heater_generic panda_breath]
# (the module registers itself; no additional config needed here)
```

---

## Step 4: Restart Klipper

```sh
sudo systemctl restart klipper
```

Or use the Fluidd/Mainsail UI to restart the Klipper service.

---

## Step 5: Verify

In the Klipper log (`/tmp/klippy.log`), you should see:

```
panda_breath: connected to ws://PandaBreath.local/ws
panda_breath: cal_warehouse_temp=24.3
```

In Fluidd/Mainsail, the Panda Breath should appear as a temperature sensor and heater.

---

## Orca Slicer integration

Orca Slicer can set chamber temperature automatically for materials that need it. In your filament profile, set the **Chamber temperature** field. Orca will emit:

```gcode
SET_HEATER_TEMPERATURE HEATER=panda_breath TARGET=45
```

No custom GCode or printer profile changes are needed beyond ensuring `panda_breath` is registered as a heater in Klipper.

---

## Troubleshooting

**Device not found / connection refused**

- Verify the device is on your WiFi: `ping PandaBreath.local`
- Try using the IP address directly in `printer.cfg` instead of the mDNS hostname
- Check the device's AP fallback: if not connected to WiFi, it creates `Panda_Breath_XXXXXXXXXX` (password: `987654321`, IP: `192.168.254.1`)

**`ModuleNotFoundError: websocket`**

- The `websocket-client` Python package is not installed. Run `opkg install python3-websocket` and restart Klipper.

**Temperature stuck at 0 or not updating**

- The device pushes temperature periodically from its `temp_task`. If the WebSocket connection is established but no temperature arrives, check that the firmware is v0.0.0 (v1.0.1+ may have regressions). See [Firmware](../firmware.md).

**Heater turns on but chamber doesn't heat**

- Confirm the Panda Breath is powered (mains AC connected, main power switch on)
- The device controls all heater duty-cycling internally; the module only sends `work_on: true`
