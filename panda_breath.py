# panda_breath.py — Klipper extras module for BIQU Panda Breath
#
# Exposes the Panda Breath as a standard Klipper heater (heater_generic interface).
# Supports two firmware targets via a transport abstraction:
#
#   firmware: stock   — OEM WebSocket JSON protocol (ws://<host>/ws)
#                       Recommended firmware: v0.0.0 (only confirmed stable release)
#   firmware: esphome — ESPHome MQTT protocol (MQTT 3.1.1 over TCP)
#
# No external Python dependencies — stdlib only (socket, struct, hashlib, base64,
# os, json, threading, collections, time, logging).  The module is a single-file
# drop into /home/lava/klipper/klippy/extras/ with no install steps.
#
# printer.cfg — stock firmware:
#   [panda_breath]
#   firmware: stock
#   host: pandabreath.local
#   port: 80
#
#   [heater_generic panda_breath]
#   heater_pin: panda_breath:pwm
#   sensor_type: panda_breath
#   control: watermark
#   max_delta: 0.5
#   min_temp: 15
#   max_temp: 80
#
#   [verify_heater panda_breath]
#   check_gain_time: 120
#   hysteresis: 5
#   heating_gain: 1
#
# printer.cfg — ESPHome firmware:
#   [panda_breath]
#   firmware: esphome
#   mqtt_broker: 192.168.1.x
#   mqtt_port: 1883
#   mqtt_topic_prefix: panda-breath

import collections
import base64
import hashlib
import json
import logging
import os
import socket
import struct
import threading
import time

logger = logging.getLogger(__name__)

# How long to wait between reconnect attempts (seconds)
RECONNECT_DELAY = 5.
# How often the Klipper reactor timer drains the state queue (seconds)
REACTOR_POLL = 1.
# Log a warning if no temperature update received within this window (seconds)
TEMP_STALE_WARN = 60.


# ─── WebSocket transport (stock OEM firmware) ─────────────────────────────────

class _WebSocketTransport:
    """Minimal RFC 6455 WebSocket client for the Panda Breath OEM firmware.

    Runs a background thread that maintains a persistent connection to
    ws://<host>:<port>/ws, parses incoming JSON settings frames, and
    invokes on_message({'temperature': float}) when a temperature field
    is received.  Reconnects automatically on any error.

    Outbound commands use the {"settings": {...}} envelope the device expects.
    The last-sent command is re-sent on every reconnect so the device is
    always in the desired state after a connection drop.
    """

    def __init__(self, host, port, on_message, on_disconnect):
        self._host = host
        self._port = port
        self._on_message = on_message
        self._on_disconnect = on_disconnect
        self._sock = None
        self._running = False
        self._thread = None
        # Last target degrees — resent on reconnect to keep device in sync
        self._last_target = 0.
        self._last_auto = None
        self._last_drying = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="panda_breath_ws", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        sock = self._sock
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

    def set_target(self, degrees):
        self._last_target = degrees
        self._last_auto = None
        self._last_drying = None
        if degrees > 0:
            self._send_settings({"isrunning": 0})
            # Match the stock web UI's update order for better v1.0.3
            # compatibility while still using the same control fields.
            self._send_settings({"work_mode": 2})
            self._send_settings({"set_temp": int(degrees)})
            self._send_settings({"work_on": True})
        else:
            self._send_settings({"isrunning": 0})
            self._send_settings({"work_on": False})

    def set_auto_mode(self, enabled, target_c, filtertemp_c, hotbedtemp_c):
        self._last_target = 0.
        self._last_auto = (
            bool(enabled),
            int(target_c),
            int(filtertemp_c),
            int(hotbedtemp_c),
        )
        self._last_drying = None
        self._send_settings({"isrunning": 0})
        self._send_settings({"work_mode": 1})
        self._send_settings({"temp": int(target_c)})
        self._send_settings({"filtertemp": int(filtertemp_c)})
        self._send_settings({"hotbedtemp": int(hotbedtemp_c)})
        self._send_settings({"work_on": bool(enabled)})

    def start_drying(self, temp_c, hours):
        self._last_auto = None
        self._last_drying = (int(temp_c), int(hours))
        self._send_settings({"work_mode": 3})
        self._send_settings({"custom_temp": int(temp_c)})
        self._send_settings({"custom_timer": int(hours)})
        self._send_settings({"filament_temp": int(temp_c)})
        self._send_settings({"filament_timer": int(hours)})
        self._send_settings({"isrunning": 1})
        self._send_settings({"work_on": True})

    def stop_drying(self):
        self._last_drying = None
        self._send_settings({"isrunning": 0})
        self._send_settings({"work_on": False})

    # ── internal ──────────────────────────────────────────────────────────────

    def force_off(self):
        self._last_target = 0.
        self._last_auto = None
        self._last_drying = None
        off_sequence = ({"isrunning": 0}, {"work_on": False})
        for fields in off_sequence:
            self._send_settings(fields)
        for fields in off_sequence:
            self._send_settings_once(fields)

    def _send_settings(self, fields):
        """Wrap fields in {"settings": fields} and send as a WebSocket text frame."""
        self._ws_send(json.dumps({"settings": fields}))

    def _send_settings_once(self, fields):
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.)
            sock.connect((self._host, self._port))
            self._handshake(sock)
            self._send_frame(sock, json.dumps({"settings": fields}))
        except Exception as exc:
            logger.warning(
                "panda_breath: one-shot WS send failed settings=%s: %s",
                fields, exc)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    def _ws_send(self, text):
        sock = self._sock
        if sock is None:
            return
        self._send_frame(sock, text)

    def _send_frame(self, sock, text):
        payload = text.encode("utf-8")
        length = len(payload)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i & 3] for i, b in enumerate(payload))
        if length < 126:
            header = struct.pack("!BB", 0x81, 0x80 | length)
        elif length < 65536:
            header = struct.pack("!BBH", 0x81, 0xFE, length)
        else:
            header = struct.pack("!BBQ", 0x81, 0xFF, length)
        try:
            sock.sendall(header + mask + masked)
        except Exception as exc:
            logger.warning("panda_breath: WS send error: %s", exc)

    def _handshake(self, sock):
        """Perform the HTTP/1.1 → WebSocket upgrade handshake."""
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            "GET /ws HTTP/1.1\r\n"
            "Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).format(host=self._host, port=self._port, key=key)
        sock.sendall(request.encode())
        # Read until end of HTTP headers
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(1024)
            if not chunk:
                raise ConnectionError("WS handshake: connection closed")
            buf += chunk
        status_line = buf.split(b"\r\n")[0]
        if b"101" not in status_line:
            raise ConnectionError(
                "WS handshake failed: %s" % status_line.decode(errors="replace"))

    def _recv_exact(self, sock, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("WS: connection closed mid-frame")
            buf.extend(chunk)
        return bytes(buf)

    def _recv_frame(self, sock):
        """Read one WebSocket frame. Returns (opcode, payload_bytes).
        Handles multi-fragment messages by reassembling (rare in practice here).
        """
        header = self._recv_exact(sock, 2)
        # FIN bit and opcode
        opcode = header[0] & 0x0F
        masked = bool(header[1] & 0x80)
        length = header[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(sock, 2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(sock, 8))[0]
        mask_key = self._recv_exact(sock, 4) if masked else None
        payload = self._recv_exact(sock, length)
        if masked:
            payload = bytes(b ^ mask_key[i & 3] for i, b in enumerate(payload))
        return opcode, payload

    def _run(self):
        """Background I/O thread: connect, receive, reconnect on any failure."""
        while self._running:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10.)
                sock.connect((self._host, self._port))
                self._handshake(sock)
                sock.settimeout(45.)  # device sends pings; 45 s gives headroom
                self._sock = sock
                logger.info("panda_breath: WebSocket connected to %s:%s",
                            self._host, self._port)
                # Resend desired state so device is in sync after reconnect
                if self._last_drying is not None:
                    self.start_drying(*self._last_drying)
                elif self._last_auto is not None and self._last_auto[0]:
                    self.set_auto_mode(*self._last_auto)
                else:
                    self.set_target(self._last_target)
                while self._running:
                    opcode, payload = self._recv_frame(sock)
                    if opcode == 0x8:   # close
                        break
                    elif opcode == 0x9:  # ping → pong
                        pong = struct.pack("!BB", 0x8A, len(payload)) + payload
                        sock.sendall(pong)
                    elif opcode in (0x1, 0x2):  # text or binary
                        self._dispatch(payload)
            except Exception as exc:
                if self._running:
                    logger.warning(
                        "panda_breath: WS error (%s) — reconnect in %.0fs",
                        exc, RECONNECT_DELAY)
                    self._on_disconnect()
            finally:
                self._sock = None
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass
            if self._running:
                time.sleep(RECONNECT_DELAY)

    def _dispatch(self, payload):
        """Parse a JSON frame and push normalised state to the callback."""
        try:
            msg = json.loads(payload.decode("utf-8"))
        except Exception as exc:
            logger.debug("panda_breath: WS parse error: %s", exc)
            return
        settings = msg.get("settings")
        if not isinstance(settings, dict):
            return
        state = {}
        # Prefer the ADC-calibrated reading; fall back to raw
        temp = settings.get("cal_warehouse_temp", settings.get("warehouse_temper"))
        if temp is not None:
            try:
                state["temperature"] = float(temp)
            except (TypeError, ValueError):
                pass
        for key in ("work_mode", "set_temp", "remaining_seconds", "isrunning",
                    "filament_drying_mode"):
            if key in settings:
                state[key] = settings.get(key)
        if "temp" in settings:
            state["auto_target"] = settings.get("temp")
        if "filtertemp" in settings:
            state["auto_filtertemp"] = settings.get("filtertemp")
        if "hotbedtemp" in settings:
            state["auto_hotbedtemp"] = settings.get("hotbedtemp")
        if "filament_temp" in settings:
            state["filament_temp"] = settings.get("filament_temp")
        elif "custom_temp" in settings:
            state["filament_temp"] = settings.get("custom_temp")
        if "filament_timer" in settings:
            state["filament_timer"] = settings.get("filament_timer")
        elif "custom_timer" in settings:
            state["filament_timer"] = settings.get("custom_timer")
        if "work_on" in settings:
            raw = settings.get("work_on")
            if isinstance(raw, bool):
                state["work_on"] = raw
            else:
                try:
                    state["work_on"] = bool(int(raw))
                except Exception:
                    pass
        if state:
            self._on_message(state)


# ─── MQTT transport (ESPHome firmware) ────────────────────────────────────────

class _MqttTransport:
    """Minimal MQTT 3.1.1 client for the ESPHome Panda Breath firmware.

    Implements only the packet types needed:
      Send:    CONNECT, SUBSCRIBE, PUBLISH (QoS 0), PINGREQ, DISCONNECT
      Receive: CONNACK, SUBACK, PUBLISH (QoS 0), PINGRESP

    Subscribes to {prefix}/sensor/chamber_temperature/state and calls
    on_message({'temperature': float}) on each retained/incoming value.

    set_target() publishes to climate mode/target topics.
    The last command is re-published on every reconnect.
    """

    _PING_INTERVAL = 30.

    def __init__(self, broker, port, topic_prefix, on_message, on_disconnect):
        self._broker = broker
        self._port = port
        self._prefix = topic_prefix
        self._on_message = on_message
        self._on_disconnect = on_disconnect
        self._sock = None
        self._running = False
        self._thread = None
        self._last_target = 0.

    def start(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="panda_breath_mqtt", daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        sock = self._sock
        if sock is not None:
            try:
                # Best-effort DISCONNECT
                sock.sendall(b"\xe0\x00")
                sock.close()
            except Exception:
                pass

    def set_target(self, degrees):
        self._last_target = degrees
        if degrees > 0:
            self._publish(
                "%s/climate/chamber/target_temperature/set" % self._prefix,
                "%.1f" % degrees)
            self._publish(
                "%s/climate/chamber/mode/set" % self._prefix, "heat")
        else:
            self._publish(
                "%s/climate/chamber/mode/set" % self._prefix, "off")

    def force_off(self):
        self._last_target = 0.
        self._publish("%s/climate/chamber/mode/set" % self._prefix, "off")

    # ── MQTT packet helpers ───────────────────────────────────────────────────

    @staticmethod
    def _encode_remaining_length(n):
        out = bytearray()
        while True:
            byte = n & 0x7F
            n >>= 7
            if n:
                byte |= 0x80
            out.append(byte)
            if not n:
                break
        return bytes(out)

    @staticmethod
    def _mqtt_str(s):
        """UTF-8 string with 2-byte big-endian length prefix (MQTT spec)."""
        encoded = s.encode("utf-8")
        return struct.pack("!H", len(encoded)) + encoded

    def _build_connect(self, client_id="panda_breath_klipper",
                       keepalive=60, username=None, password=None):
        flags = 0x02  # clean session
        if username:
            flags |= 0x80
        if password:
            flags |= 0x40
        vh = (self._mqtt_str("MQTT")     # protocol name
              + b"\x04"                  # protocol level 4 = MQTT 3.1.1
              + bytes([flags])
              + struct.pack("!H", keepalive))
        payload = self._mqtt_str(client_id)
        if username:
            payload += self._mqtt_str(username)
        if password:
            payload += self._mqtt_str(password)
        body = vh + payload
        return b"\x10" + self._encode_remaining_length(len(body)) + body

    def _build_subscribe(self, topic, packet_id=1):
        payload = struct.pack("!H", packet_id) + self._mqtt_str(topic) + b"\x00"
        return b"\x82" + self._encode_remaining_length(len(payload)) + payload

    def _build_publish(self, topic, message):
        # QoS 0, no retain, no DUP
        vh = self._mqtt_str(topic)
        body = vh + message.encode("utf-8")
        return b"\x30" + self._encode_remaining_length(len(body)) + body

    @staticmethod
    def _build_pingreq():
        return b"\xc0\x00"

    # ── socket receive helpers ────────────────────────────────────────────────

    def _recv_exact(self, sock, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("MQTT: connection closed")
            buf.extend(chunk)
        return bytes(buf)

    def _recv_remaining_length(self, sock):
        multiplier, value = 1, 0
        for _ in range(4):
            byte = ord(self._recv_exact(sock, 1))
            value += (byte & 0x7F) * multiplier
            multiplier <<= 7
            if not (byte & 0x80):
                break
        return value

    def _recv_packet(self, sock):
        """Read one MQTT packet. Returns (packet_type_nibble, flags_nibble, body_bytes)."""
        first = ord(self._recv_exact(sock, 1))
        ptype = (first >> 4) & 0xF
        pflags = first & 0xF
        remaining = self._recv_remaining_length(sock)
        body = self._recv_exact(sock, remaining) if remaining else b""
        return ptype, pflags, body

    # ── publish helper (usable from reactor thread too) ───────────────────────

    def _publish(self, topic, message):
        sock = self._sock
        if sock is None:
            return
        pkt = self._build_publish(topic, message)
        try:
            sock.sendall(pkt)
        except Exception as exc:
            logger.warning("panda_breath: MQTT publish error: %s", exc)

    # ── background thread ─────────────────────────────────────────────────────

    def _run(self):
        while self._running:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(10.)
                sock.connect((self._broker, self._port))
                sock.sendall(self._build_connect())
                # Expect CONNACK (type 2)
                ptype, _, body = self._recv_packet(sock)
                if ptype != 2:
                    raise ConnectionError(
                        "MQTT: expected CONNACK (2), got %d" % ptype)
                if len(body) >= 2 and body[1] != 0:
                    raise ConnectionError(
                        "MQTT: CONNACK refused, code=%d" % body[1])
                # Subscribe to chamber temperature topic
                temp_topic = "%s/sensor/chamber_temperature/state" % self._prefix
                sock.sendall(self._build_subscribe(temp_topic, packet_id=1))
                # Expect SUBACK (type 9)
                ptype, _, _ = self._recv_packet(sock)
                if ptype != 9:
                    raise ConnectionError(
                        "MQTT: expected SUBACK (9), got %d" % ptype)
                sock.settimeout(self._PING_INTERVAL + 5.)
                self._sock = sock
                logger.info("panda_breath: MQTT connected to %s:%s",
                            self._broker, self._port)
                # Resend desired state after reconnect
                self.set_target(self._last_target)
                last_ping = time.monotonic()
                while self._running:
                    # Send PINGREQ on schedule
                    now = time.monotonic()
                    if now - last_ping >= self._PING_INTERVAL:
                        sock.sendall(self._build_pingreq())
                        last_ping = now
                    try:
                        ptype, pflags, body = self._recv_packet(sock)
                    except socket.timeout:
                        # Use timeout to drive ping; not a fatal error
                        continue
                    if ptype == 3:   # PUBLISH
                        self._dispatch_publish(pflags, body)
                    elif ptype == 13:  # PINGRESP — nothing to do
                        pass
                    elif ptype == 0:   # malformed / connection close
                        break
            except Exception as exc:
                if self._running:
                    logger.warning(
                        "panda_breath: MQTT error (%s) — reconnect in %.0fs",
                        exc, RECONNECT_DELAY)
                    self._on_disconnect()
            finally:
                self._sock = None
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass
            if self._running:
                time.sleep(RECONNECT_DELAY)

    def _dispatch_publish(self, flags, body):
        """Parse an incoming PUBLISH packet and call on_message if it's our topic."""
        # QoS is bits 2-1 of flags; QoS 0 has no packet ID
        qos = (flags >> 1) & 0x3
        offset = 0
        if len(body) < 2:
            return
        topic_len = struct.unpack_from("!H", body, offset)[0]
        offset += 2
        if offset + topic_len > len(body):
            return
        topic = body[offset:offset + topic_len].decode("utf-8", errors="replace")
        offset += topic_len
        if qos > 0:
            offset += 2  # skip packet ID (not used for QoS 0 publishes we send)
        payload = body[offset:].decode("utf-8", errors="replace").strip()
        if topic.endswith("/chamber_temperature/state"):
            try:
                self._on_message({"temperature": float(payload)})
            except (TypeError, ValueError):
                pass


# ─── Klipper heater class ──────────────────────────────────────────────────────

class PandaBreath:
    """Klipper extras module — exposes a virtual heater for Panda Breath.
    
    Registers a sensor factory and a virtual chip (pin) so that the user
    can define a standard [heater_generic] in their config.
    """

    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.name = config.get_name().split()[-1]

        # Config
        firmware = config.get("firmware", "stock")
        self.host = config.get("host")
        self.port = config.getint("port", 80)

        # state — modified by reactor poll
        self.temperature = 0.
        self.target = 0.
        self.smoothed_temp = 0.
        self.is_connected = False
        self.work_mode = 2
        self.work_on = False
        self.device_target = 0.
        self.auto_enabled = False
        self.auto_target = 45
        self.auto_filtertemp = 30
        self.auto_hotbedtemp = 80
        self.filament_temp = 0
        self.filament_timer = 0
        self.remaining_seconds = 0
        self.filament_drying_active = False
        self._in_shutdown = False
        self._external_off_lockout = False
        self._last_temp_time = 0.
        self._sensor = None
        self._virtual_pin = None
        self._heater = None
        self._heater_set_temp_orig = None

        # Thread-safe queue for background I/O
        self._state_queue = collections.deque()

        # Transport initialization
        if firmware == "stock":
            self._transport = _WebSocketTransport(
                self.host, self.port, self._enqueue, self._on_disconnect)
        elif firmware == "esphome":
            broker = config.get("mqtt_broker")
            mqtt_port = config.getint("mqtt_port", 1883)
            prefix = config.get("mqtt_topic_prefix", "panda-breath")
            self._transport = _MqttTransport(
                broker, mqtt_port, prefix, self._enqueue, self._on_disconnect)
        else:
            raise config.error("panda_breath: unknown firmware '%s'" % firmware)

        # 1. Register sensor factory so user can use: sensor_type: panda_breath
        pheaters = self.printer.load_object(config, 'heaters')
        pheaters.add_sensor_factory("panda_breath", self._create_sensor)

        # 2. Register virtual chip so user can use: heater_pin: panda_breath:pwm
        ppins = self.printer.lookup_object('pins')
        ppins.register_chip('panda_breath', self)

        # Klipper lifecycle
        self.printer.register_event_handler(
            "klippy:connect", self._handle_connect)
        self.printer.register_event_handler(
            "klippy:disconnect", self._handle_disconnect)
        self.printer.register_event_handler(
            "klippy:shutdown", self._handle_shutdown)

        self._poll_timer = self.reactor.register_timer(
            self._reactor_poll, self.reactor.NEVER)

        gcode = self.printer.lookup_object('gcode')
        gcode.register_command('PANDA_BREATH_AUTO', self._cmd_panda_breath_auto)
        gcode.register_command('PANDA_BREATH_DRY_START', self._cmd_panda_breath_dry_start)
        gcode.register_command('PANDA_BREATH_DRY_STOP', self._cmd_panda_breath_dry_stop)

    def _create_sensor(self, config):
        self._sensor = PandaBreathSensor(config, self)
        return self._sensor

    def setup_pin(self, pin_type, pin_params):
        if pin_params['pin'] == 'pwm':
            self._virtual_pin = PandaBreathVirtualPin(self)
            return self._virtual_pin
        raise self.printer.config.error(
            "Unknown panda_breath pin: %s" % (pin_params['pin'],))

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def _handle_connect(self):
        self._in_shutdown = False
        self._attach_heater_hook()
        self._transport.start()
        self.reactor.update_timer(self._poll_timer, self.reactor.NOW)
        self._force_device_off("connect")

    def _handle_disconnect(self):
        self._in_shutdown = True
        self._force_device_off("disconnect")
        self._transport.stop()
        self.reactor.update_timer(self._poll_timer, self.reactor.NEVER)
        
    def _handle_shutdown(self):
        """Emergency turn off the external heater if Klipper crashes."""
        self._in_shutdown = True
        self._force_device_off("shutdown")

    def _force_device_off(self, reason):
        self._clear_heater_target_state()
        self.target = 0.
        self.device_target = 0.
        self.auto_enabled = False
        self.work_on = False
        self.filament_drying_active = False
        self.remaining_seconds = 0
        self._external_off_lockout = True
        try:
            self._transport.force_off()
            return
        except AttributeError:
            self._transport.set_target(0.)
        except Exception as exc:
            logger.warning(
                "panda_breath: failed to force off on %s: %s", reason, exc)
            try:
                self._transport.set_target(0.)
            except Exception:
                pass

    def _attach_heater_hook(self):
        if self._heater_set_temp_orig is not None:
            return
        try:
            pheaters = self.printer.lookup_object('heaters')
            heater = pheaters.lookup_heater(self.name)
        except Exception as exc:
            logger.warning("panda_breath: unable to hook heater '%s': %s",
                           self.name, exc)
            return
        self._heater = heater
        self._heater_set_temp_orig = heater.set_temp

        def wrapped_set_temp(degrees):
            self._heater_set_temp_orig(degrees)
            if degrees > 0.:
                self._external_off_lockout = False
            self.set_device_target(degrees)

        heater.set_temp = wrapped_set_temp

    cmd_PANDA_BREATH_AUTO_help = (
        "Configure Panda Breath native auto mode "
        "(ENABLE=0|1 TARGET=<C> FILTERTEMP=<C> HOTBEDTEMP=<C>)"
    )

    def _cmd_panda_breath_auto(self, gcmd):
        enabled = bool(gcmd.get_int(
            'ENABLE', default=int(self.auto_enabled), minval=0, maxval=1))
        target = int(gcmd.get_float(
            'TARGET', default=float(self.auto_target), minval=0.0, maxval=80.0))
        filtertemp = int(gcmd.get_float(
            'FILTERTEMP', default=float(self.auto_filtertemp), minval=0.0, maxval=120.0))
        hotbedtemp = int(gcmd.get_float(
            'HOTBEDTEMP', default=float(self.auto_hotbedtemp), minval=0.0, maxval=120.0))
        self._set_auto_mode(enabled, target, filtertemp, hotbedtemp, gcmd=gcmd)

    def _set_auto_mode(self, enabled, target, filtertemp, hotbedtemp, gcmd=None):
        if not callable(getattr(self._transport, "set_auto_mode", None)):
            message = "Native Panda auto mode is only available with stock firmware transport"
            if gcmd is not None:
                raise gcmd.error(message)
            raise RuntimeError(message)
        if self._in_shutdown and enabled:
            message = "Cannot enable Panda auto mode while Klipper is shutdown"
            if gcmd is not None:
                raise gcmd.error(message)
            raise RuntimeError(message)
        self._external_off_lockout = False
        self._clear_heater_target_state()
        self.auto_enabled = bool(enabled)
        self.auto_target = int(target)
        self.auto_filtertemp = int(filtertemp)
        self.auto_hotbedtemp = int(hotbedtemp)
        self.work_mode = 1
        self.work_on = bool(enabled)
        self.target = 0.
        self.device_target = 0.
        try:
            self._transport.set_auto_mode(
                self.auto_enabled,
                self.auto_target,
                self.auto_filtertemp,
                self.auto_hotbedtemp,
            )
        except Exception as exc:
            logger.warning("panda_breath: failed to configure auto mode: %s", exc)
            if gcmd is not None:
                raise gcmd.error("Failed to configure Panda Breath auto mode")
            raise

    cmd_PANDA_BREATH_DRY_START_help = "Start Panda Breath filament drying (TEMP/HOURS)"

    def _cmd_panda_breath_dry_start(self, gcmd):
        temp = int(gcmd.get_float('TEMP', default=55., minval=0.0, maxval=80.0))
        hours = int(gcmd.get_float('HOURS', default=6., minval=1.0, maxval=12.0))
        if not callable(getattr(self._transport, "start_drying", None)):
            raise gcmd.error(
                "Panda Breath drying mode is only available with stock firmware transport")
        self._external_off_lockout = False
        self._clear_heater_target_state()
        self.auto_enabled = False
        self.target = 0.
        self.device_target = 0.
        self.work_on = True
        self.filament_temp = temp
        self.filament_timer = hours
        self.remaining_seconds = 0
        self.work_mode = 3
        self.filament_drying_active = True
        try:
            self._transport.start_drying(temp, hours)
        except Exception as exc:
            logger.warning("panda_breath: failed to start drying mode: %s", exc)
            raise gcmd.error("Failed to start Panda Breath drying mode")

    cmd_PANDA_BREATH_DRY_STOP_help = "Stop Panda Breath filament drying"

    def _cmd_panda_breath_dry_stop(self, gcmd):
        _ = gcmd
        self._force_device_off("dry stop command")

    def _clear_heater_target_state(self):
        self._attach_heater_hook()
        if self._heater_set_temp_orig is None:
            return
        try:
            self._heater_set_temp_orig(0.)
        except Exception as exc:
            logger.debug("panda_breath: unable to clear heater target state: %s", exc)

    # ── state queue ───────────────────────────────────────────────────────────

    def _enqueue(self, data):
        self._state_queue.append(data)

    def _on_disconnect(self):
        self.is_connected = False

    def _reactor_poll(self, eventtime):
        while self._state_queue:
            data = self._state_queue.popleft()
            self.is_connected = True
            temp = data.get("temperature")
            if temp is not None:
                self.temperature = float(temp)
                self.smoothed_temp = self.temperature
                self._last_temp_time = eventtime
            if "work_mode" in data:
                try:
                    self.work_mode = int(data.get("work_mode"))
                    if self.work_mode != 1:
                        self.auto_enabled = False
                except Exception:
                    pass
            if "work_on" in data:
                self.work_on = bool(data.get("work_on"))
                if self.work_mode == 1:
                    self.auto_enabled = self.work_on
            if "set_temp" in data:
                try:
                    self.device_target = float(data.get("set_temp"))
                except Exception:
                    pass
            if "auto_target" in data:
                try:
                    self.auto_target = int(data.get("auto_target"))
                except Exception:
                    pass
            if "auto_filtertemp" in data:
                try:
                    self.auto_filtertemp = int(data.get("auto_filtertemp"))
                except Exception:
                    pass
            if "auto_hotbedtemp" in data:
                try:
                    self.auto_hotbedtemp = int(data.get("auto_hotbedtemp"))
                except Exception:
                    pass
            if "filament_temp" in data:
                try:
                    self.filament_temp = int(data.get("filament_temp"))
                except Exception:
                    pass
            if "filament_timer" in data:
                try:
                    self.filament_timer = int(data.get("filament_timer"))
                except Exception:
                    pass
            if "remaining_seconds" in data:
                try:
                    self.remaining_seconds = int(data.get("remaining_seconds"))
                except Exception:
                    pass
            if "isrunning" in data:
                try:
                    self.filament_drying_active = bool(int(data.get("isrunning")))
                    if not self.filament_drying_active:
                        self.remaining_seconds = 0
                except Exception:
                    pass
            if "filament_drying_mode" in data:
                try:
                    self.work_mode = 3
                except Exception:
                    pass

        # Keep the heater callback fresh every poll cycle and use MCU print
        # time so verify_heater compares timestamps from the correct clock.
        if self._sensor and self._sensor.callback and self._last_temp_time > 0:
            try:
                mcu = self.printer.lookup_object('mcu')
                read_time = mcu.estimated_print_time(eventtime)
            except Exception:
                read_time = eventtime
            self._sensor.callback(read_time, self.temperature)
        
        if (self._last_temp_time > 0. 
                and eventtime - self._last_temp_time > TEMP_STALE_WARN):
            logger.warning(
                "panda_breath: temperature data stale (%.0fs)",
                eventtime - self._last_temp_time)
            self._last_temp_time = eventtime

        # Keep device target synchronized with heater target even if no PWM
        # callback arrives (seen on some modified Klipper builds).
        heater_target = self._lookup_heater_target()
        if heater_target is None:
            try:
                webhooks = self.printer.lookup_object('webhooks')
                all_status = webhooks.get_status(eventtime)
                hstatus = all_status.get('heater_generic %s' % self.name)
                if isinstance(hstatus, dict):
                    heater_target = hstatus.get('target')
            except Exception:
                pass
        if heater_target is not None and abs(float(heater_target) - self.target) > 0.01:
            heater_target = float(heater_target)
            if self.work_mode in (1, 3):
                logger.debug(
                    "panda_breath: ignoring synced heater target %.1f while mode=%s",
                    heater_target, self.work_mode)
            elif self._external_off_lockout and heater_target > 0.:
                logger.info(
                    "panda_breath: ignoring synced heater target %.1f after forced off",
                    heater_target)
            else:
                self.set_device_target(heater_target)
        
        return eventtime + REACTOR_POLL

    def _lookup_heater_target(self):
        try:
            pheaters = self.printer.lookup_object('heaters')
            if self._heater is None:
                try:
                    self._heater = pheaters.lookup_heater(self.name)
                except Exception:
                    self._heater = None
            if self._heater is not None:
                return float(getattr(self._heater, 'target_temp', 0.0))

            try:
                hobj = self.printer.lookup_object('heater_generic %s' % self.name)
                if hobj is not None:
                    return float(getattr(hobj, 'target_temp', 0.0))
            except Exception:
                pass

            heater = pheaters.heaters.get(self.name)
            if heater is None:
                for hname, hobj in pheaters.heaters.items():
                    if hname.endswith(self.name):
                        heater = hobj
                        break
            if heater is not None:
                return float(getattr(heater, 'target_temp', 0.0))

            if self._virtual_pin is None:
                return None
            for _, heater in pheaters.heaters.items():
                if getattr(heater, 'mcu_pwm', None) == self._virtual_pin:
                    return float(getattr(heater, 'target_temp', 0.0))
        except Exception:
            pass
        return None

    def set_device_target(self, degrees):
        """Send target to device. Only sends if changed or 0."""
        if self._in_shutdown and float(degrees) > 0.:
            logger.info(
                "panda_breath: ignoring target %.1f while Klipper is shutdown",
                float(degrees))
            return
        self.auto_enabled = False
        self.work_mode = 2
        self.target = float(degrees)
        self.device_target = float(degrees)
        self.work_on = self.target > 0.
        self.filament_drying_active = False
        self.remaining_seconds = 0
        self._transport.set_target(degrees)

    def get_status(self, eventtime):
        return {
            "temperature": self.temperature,
            "target": self.target,
            "smoothed_temp": self.smoothed_temp,
            "connected": self.is_connected,
            "work_mode": self.work_mode,
            "work_on": self.work_on,
            "device_target": self.device_target,
            "auto_enabled": self.auto_enabled,
            "auto_target": self.auto_target,
            "auto_filtertemp": self.auto_filtertemp,
            "auto_hotbedtemp": self.auto_hotbedtemp,
            "filament_temp": self.filament_temp,
            "filament_timer": self.filament_timer,
            "remaining_seconds": self.remaining_seconds,
            "filament_drying_active": self.filament_drying_active,
        }


class PandaBreathSensor:
    """Implements the Klipper sensor interface for heater_generic."""
    def __init__(self, config, module):
        self.printer = config.get_printer()
        self.module = module
        self.callback = None

    def get_temp(self, eventtime):
        return self.module.temperature, self.module.target

    def get_status(self, eventtime):
        return {
            "temperature": self.module.temperature,
            "target": self.module.target,
            "smoothed_temp": self.module.smoothed_temp,
        }

    def setup_minmax(self, min_temp, max_temp):
        pass

    def setup_callback(self, cb):
        self.callback = cb

    def get_report_time_delta(self):
        return 1.0

    def set_read_tolerance(self, range_check_val, range_check_time):
        pass


class PandaBreathVirtualPin:
    """A virtual PWM pin that intercepts heater power to sync target temperature."""
    def __init__(self, module):
        self.module = module
        self.last_value = 0.0

    def get_mcu(self):
        return self.module.printer.lookup_object('mcu')

    def set_pwm(self, print_time, value, cycle_time=None):
        target = self._lookup_heater_target()
        if target is not None:
            if target <= 0:
                if self.module.target != 0:
                    self.module.set_device_target(0)
            elif self.module._external_off_lockout:
                pass
            elif target != self.module.target or self.last_value == 0:
                self.module.set_device_target(target)
        self.last_value = value

    def _lookup_heater_target(self):
        try:
            pheaters = self.module.printer.lookup_object('heaters')
            for name, heater in pheaters.heaters.items():
                if getattr(heater, 'mcu_pwm', None) == self:
                    return heater.target_temp
        except Exception:
            pass
        return None

    def setup_max_duration(self, max_duration):
        pass

    def setup_cycle_time(self, cycle_time, shutdown_value=0.):
        pass


def load_config(config):
    return PandaBreath(config)
