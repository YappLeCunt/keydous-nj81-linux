"""FEA_CMD command layer for the Keydous NJ81 family (YC500 / YC200).

Command byte map recovered from the Electron app (YC200Common keyboard
class, which YC500Common and the yc500_nj81* devices inherit):

    SET_*  0..127    GET_* = SET_* + 128 (except a few pinned values)

    FEA_CMD_SET_REV     = 0      FEA_CMD_GET_REV     = 128
    FEA_CMD_SET_RESERT  = 2      FEA_CMD_GET_BATTERY = 131
    FEA_CMD_SET_REPORT  = 4      FEA_CMD_GET_REPORT  = 132
    FEA_CMD_SET_PROFILE = 5      FEA_CMD_GET_PROFILE = 133
    FEA_CMD_SET_KBOPTION= 6      FEA_CMD_GET_KBOPTION= 134
    FEA_CMD_SET_LEDPARAM= 7      FEA_CMD_GET_LEDPARAM= 135
    FEA_CMD_SET_SLEDPARAM=8      FEA_CMD_GET_SLEDPARAM=136
    FEA_CMD_SET_KEYMATRIX=9      FEA_CMD_GET_KEYMATRIX=137
    FEA_CMD_SET_KEYENABLE=10     FEA_CMD_GET_KEYENABLE=138
    FEA_CMD_SET_MACRO   = 11     FEA_CMD_GET_MACRO   = 139
    FEA_CMD_SET_USERPIC = 12     FEA_CMD_GET_USERPIC = 140
    FEA_CMD_SET_AUDIO   = 13
    FEA_CMD_SET_WINDOS  = 14
    FEA_CMD_GET_INFOR   = 143
    FEA_CMD_SET_FN      = 16     FEA_CMD_GET_FN      = 144
    FEA_CMD_SET_DEBOUNCE= 17     FEA_CMD_GET_DEBOUNCE= 145
    FEA_CMD_SET_SLEEPTIME=18     FEA_CMD_GET_SLEEPTIME=146
    FEA_CMD_SET_BOOTLOATER=127

All reports are 64 payload bytes: byte[0] = command, byte[1..] = params,
byte[7]/[8] = checksum depending on scheme.
"""

from . import checksum

import time


class Cmd:
    SET_REV = 0
    GET_REV = 128
    SET_RESERT = 2
    SET_BATTERY_LP = 3
    GET_BATTERY = 131
    SET_REPORT = 4
    GET_REPORT = 132
    SET_PROFILE = 5
    GET_PROFILE = 133
    SET_KBOPTION = 6
    GET_KBOPTION = 134
    SET_LEDPARAM = 7
    GET_LEDPARAM = 135
    SET_SLEDPARAM = 8
    GET_SLEDPARAM = 136
    SET_KEYMATRIX = 9
    GET_KEYMATRIX = 137
    SET_KEYENABLE = 10
    GET_KEYENABLE = 138
    SET_MACRO = 11
    GET_MACRO = 139
    SET_USERPIC = 12
    GET_USERPIC = 140
    SET_AUDIO = 13
    SET_WINDOS = 14
    GET_INFOR = 143
    SET_FN = 16
    GET_FN = 144
    SET_DEBOUNCE = 17
    GET_DEBOUNCE = 145
    SET_SLEEPTIME = 18
    GET_SLEEPTIME = 146
    SET_BOOTLOATER = 127
    # TFT / OLED screen
    SET_OLEDGIFDATA = 36
    SETTFTLCDDATA = 37
    GETTFTLCDDATA = 165
    SET_SCREEN_24BITDATA = 41
    GET_SCREEN_24BITDATA = 169
    GETOLED_VERSION = 173
    SET_OLEDBOOTLOADER = 48
    GET_OLEDBOOTLOADER = 176
    SET_OLEDBOOTSTART = 49
    GET_OLEDBOOTCHECKSUM = 177
    # YC500 "simple" (single-key) commands
    SET_KEYMATRIX_SIMPLE = 19
    GET_KEYMATRIX_SIMPLE = 147
    SET_USERPIC_SIMPLE = 20
    GET_USERPIC_SIMPLE = 148
    SET_FN_SIMPLE = 21
    GET_FN_SIMPLE = 149
    SET_MACRO_SIMPLE = 22
    GET_MACRO_SIMPLE = 150


class Keyboard:
    """High-level operations. `dev` is a transport with .command()."""

    def __init__(self, dev):
        self.dev = dev

    # -- queries ----------------------------------------------------------
    def firmware_version(self):
        """2-byte LE version at response[1:3]."""
        r = self.dev.command(Cmd.GET_REV)
        return int.from_bytes(r[1:3], "little")

    def device_info(self):
        """Human-readable info report (GET_INFOR)."""
        r = self.dev.command(Cmd.GET_INFOR)
        return r

    def battery(self):
        """(percent, status) matching the vendor decoding:
        percent = reply[1], reply[2]: 1 = charging, 2 = full, else
        not charging.  The wired interface reports 0 percent while
        charging on USB; the real level is only reported by the
        wireless link (BT / 2.4G)."""
        r = self.dev.command(Cmd.GET_BATTERY)
        status = {1: "charging", 2: "full"}.get(r[2], "not charging")
        return r[1], status

    def battery_lp(self):
        """Low-battery warning threshold from reply[3] of GET_BATTERY."""
        return self.dev.command(Cmd.GET_BATTERY)[3]

    def profile(self):
        return self.dev.command(Cmd.GET_PROFILE)[1]

    def set_profile(self, profile: int):
        buf = bytearray(64)
        buf[0] = Cmd.SET_PROFILE
        buf[1] = profile & 0xFF
        # BIT7 is REQUIRED here: with NONE the firmware ignores the switch
        # (verified on 0x0513 - GET_PROFILE stays unchanged).
        self.dev.send_feature(checksum.apply(buf, checksum.BIT7))
        time.sleep(0.8)          # firmware applies profile asynchronously
        return profile

    def debounce(self):
        """Debounce in ms. GET_DEBOUNCE reply: [0]=echo, [1]=profile,
        [2]=value."""
        r = self.dev.command(Cmd.GET_DEBOUNCE)
        return r[2]

    def set_debounce(self, ms: int):
        buf = bytearray(64)
        buf[0] = Cmd.SET_DEBOUNCE
        buf[2] = ms & 0xFF
        self.dev.send_feature(checksum.apply(buf, checksum.BIT7))
        time.sleep(0.5)
        return ms

    def sleep_time(self):
        """(time_bt, time_24, deep_bt, deep_24) in minutes.

        GET_SLEEPTIME reply has the four u16 LE values at bytes 1, 3, 5, 7
        (verified on 0x0513: 120/120/1680/1680)."""
        r = self.dev.command(Cmd.GET_SLEEPTIME)
        return (r[1] | r[2] << 8, r[3] | r[4] << 8,
                r[5] | r[6] << 8, r[7] | r[8] << 8)

    def set_sleep_time(self, time_bt=None, time_24=None, deep_bt=None,
                       deep_24=None):
        """Write sleep timers in minutes. Params are placed at bytes 8..15
        (vendor layout); readback returns them at bytes 1..8."""
        cur = self.sleep_time()
        time_bt = cur[0] if time_bt is None else time_bt
        time_24 = cur[1] if time_24 is None else time_24
        deep_bt = cur[2] if deep_bt is None else deep_bt
        deep_24 = cur[3] if deep_24 is None else deep_24
        buf = bytearray(64)
        buf[0] = Cmd.SET_SLEEPTIME
        for off, value in ((8, time_bt), (10, time_24),
                           (12, deep_bt), (14, deep_24)):
            buf[off] = value & 0xFF
            buf[off + 1] = (value >> 8) & 0xFF
        self.dev.send_feature(checksum.apply(buf, checksum.BIT7))
        time.sleep(0.5)
        return self.sleep_time()

    def set_battery_lp(self, percent: int):
        """Low-battery warning threshold percent (SET_BATTERY_LP 0x02)."""
        buf = bytearray(64)
        buf[0] = Cmd.SET_BATTERY_LP
        buf[1] = max(0, min(100, int(percent)))
        self.dev.send_feature(checksum.apply(buf, checksum.BIT7))
        time.sleep(0.5)
        return buf[1]

    def report_rate(self):
        """Polling rate in Hz."""
        buf = bytearray(64)
        buf[0] = Cmd.GET_REPORT
        buf[1] = self.profile()
        r = self.dev.command(Cmd.GET_REPORT, bytes([buf[1]]))
        return {1: 1000, 2: 500, 4: 250, 8: 125}.get(r[2], r[2])

    def set_report_rate(self, hz: int):
        code = {1000: 1, 500: 2, 250: 4, 125: 8}.get(hz, 0)
        buf = bytearray(64)
        buf[0] = Cmd.SET_REPORT
        buf[1] = self.profile()
        buf[2] = code
        self.dev.send_feature(checksum.apply(buf, checksum.BIT7))

    def keyboard_option(self):
        """Returns dict of the KBOPTION bitfield at response[2]."""
        buf = bytearray(64)
        buf[0] = Cmd.GET_KBOPTION
        buf[1] = self.profile()
        r = self.dev.command(Cmd.GET_KBOPTION, bytes([buf[1]]))
        opt = r[2]
        return {
            "win_key_lock": bool(opt & 0x01),
            "system": bool(opt & 0x04),
            "wasd_arrow_exchange": bool(opt & 0x08),
            "led_off": bool(opt & 0x10),
            "s_led_off": bool(opt & 0x20),
            "keyboard_mode": bool(opt & 0x40),
            "keyboard_lock": bool(opt & 0x80),
            "fn_matrix": r[3],
            "power_save": r[4],
        }

    def set_keyboard_option(self, *, win_key_lock=None, system=None,
                            wasd_arrow_exchange=None, led_off=None,
                            s_led_off=None, keyboard_mode=None,
                            keyboard_lock=None, fn_matrix=None,
                            power_save=None):
        cur = self.keyboard_option()
        opt = 0
        if win_key_lock is not None:
            cur["win_key_lock"] = win_key_lock
        if system is not None:
            cur["system"] = system
        if wasd_arrow_exchange is not None:
            cur["wasd_arrow_exchange"] = wasd_arrow_exchange
        if led_off is not None:
            cur["led_off"] = led_off
        if s_led_off is not None:
            cur["s_led_off"] = s_led_off
        if keyboard_mode is not None:
            cur["keyboard_mode"] = keyboard_mode
        if keyboard_lock is not None:
            cur["keyboard_lock"] = keyboard_lock
        opt = (int(cur["win_key_lock"]) | int(cur["system"]) << 2
               | int(cur["wasd_arrow_exchange"]) << 3
               | int(cur["led_off"]) << 4 | int(cur["s_led_off"]) << 5
               | int(cur["keyboard_mode"]) << 6
               | int(cur["keyboard_lock"]) << 7)
        buf = bytearray(64)
        buf[0] = Cmd.SET_KBOPTION
        buf[1] = self.profile()
        buf[2] = opt
        buf[3] = cur["fn_matrix"] if fn_matrix is None else fn_matrix
        buf[4] = cur["power_save"] if power_save is None else power_save
        self.dev.send_feature(checksum.apply(buf, checksum.BIT7))

    # -- reset ------------------------------------------------------------
    def reset(self):
        """Restore factory defaults / reset device.

        The vendor sends SET_RESERT (0x02) with a BIT7 checksum. This is
        destructive: it resets the active profile and stored mappings.
        """
        buf = bytearray(64)
        buf[0] = Cmd.SET_RESERT
        self.dev.send_feature(checksum.apply(buf, checksum.BIT7))

    # -- LED --------------------------------------------------------------
    def set_light(self, mode: int, *, speed: int = 0, value: int = 4,
                  param: int = None, r: int = 0, g: int = 0, b: int = 0,
                  dazzle: bool = False):
        """Set LED effect (YC500 numbering, see LED_MODES).

        byte layout: [1]=mode [2]=4-speed [3]=value [4]=param [5..7]=RGB,
        [8]=BIT8 checksum. The checksum is REQUIRED: without it the
        device shows the effect transiently but does not commit it
        (GET_LEDPARAM keeps returning the previous setting).

        The NJ81 vendor profile defines value as a 0..4 effect level. Using
        out-of-range values (the old Linux default was 128) causes visibly
        incorrect animation. Param low nibble: 7 (NORMAL) displays the
        exact RGB we send, 6 (DAZZLE) cycles colors automatically
        ("Dazzle" in the vendor app), 0-5 select preset COMMONCOLOR ids.
        Direction modes keep their direction bits in the high nibble.
        """
        if param is None:
            param = YC500_PARAM.get(mode, 0)
            if dazzle and mode in LED_DAZZLE_MODES:
                param = (param & 0xF0) | 6
        value = max(0, min(4, int(value)))
        if mode == 0:
            value = 0
        buf = bytearray(64)
        buf[0] = Cmd.SET_LEDPARAM
        buf[1] = mode & 0xFF
        buf[2] = (4 - speed) & 0xFF      # MAXSPEED=4
        buf[3] = value & 0xFF
        buf[4] = param & 0xFF
        rgb = (r << 16) | (g << 8) | b
        buf[5] = (rgb >> 16) & 0xFF
        buf[6] = (rgb >> 8) & 0xFF
        buf[7] = rgb & 0xFF
        self.dev.send_feature(checksum.apply(buf, checksum.BIT8))

    def get_light(self):
        """Read current LED effect (YC500 layout)."""
        r = self.dev.command(Cmd.GET_LEDPARAM)
        speed = 4 - r[2]
        rgb = (r[5] << 16) | (r[6] << 8) | r[7]
        if rgb == 0xFB0EFA:
            rgb = 0xFFFFFF
        return {"mode": r[1], "speed": speed, "value": r[3],
                "param": r[4], "option": (r[4] >> 4) & 0x0F,
                "dazzle": (r[4] & 0x0F) == 6,
                "rgb": rgb}


# YC500 (NJ81) LED modes - numbering differs from older yc200 boards.
LED_MODES = {
    "off": 0,
    "always_on": 1,
    "breath": 2,
    "neon": 3,
    "wave": 4,
    "ripple": 5,
    "raindrop": 6,
    "snake": 7,
    "press_action": 8,
    "coverage": 9,
    "sine_wave": 10,
    "kaleidoscope": 11,
    "line_wave": 12,
    "user_picture": 13,
    "laser": 14,
    "circle_wave": 15,
    "dazzling": 16,
    "rain_down": 17,
    "meteor": 18,
    "press_action_off": 19,
    "music_follow3": 20,
    "screen_color": 21,
    "music_follow2": 22,
    "train": 23,
    "fireworks": 24,
}

# Default param byte per mode (YC500). Verified on NJ81 fw 0x0513:
# the low nibble selects a preset COMMONCOLOR (0=white, 1..6) and is
# substituted for the sent RGB; param 7 (NORMAL) / 8 (DAZZLE) make the
# firmware display the exact RGB we send. Direction modes keep their
# direction bits in the high nibble (wave: right=0,left=1,down=2,up=3;
# snake/kaleidoscope/line-wave/circle-wave/fireworks: 0 vs 16), music
# modes use 4, user picture uses USEROP (0/16/32/48/64).
# Trigger modes 8/9/19 intentionally use param 0; for those modes the
# firmware treats it as the trigger/action setting rather than a color.
YC500_PARAM = {
    0: 7, 1: 7, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7, 7: 7, 8: 0, 9: 0,
    10: 7, 11: 7, 12: 7, 13: 0, 14: 7, 15: 7, 16: 7, 17: 7,
    18: 7, 19: 0, 20: 4, 21: 7, 22: 4, 23: 7, 24: 7,
}

# Modes that support the Dazzle (color cycling) low nibble 6. Matches the
# vendor UI: every RGB-capable mode except off, neon, and user picture.
LED_DAZZLE_MODES = {1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 16, 17,
                    18, 19, 23, 24}

YC500_OPTIONS = {
    "wave": {0: "right", 1: "left", 2: "down", 3: "up"},
    "snake": {0: "z", 16: "return"},
    "kaleidoscope": {0: "out", 16: "in"},
    "line_wave": {0: "right", 16: "left"},
    "circle_wave": {0: "anti-clockwise", 16: "clockwise"},
    "fireworks": {0: "right", 16: "left"},
    "music_follow2": {4: "upright", 16 + 4: "separate", 32 + 4: "intersect"},
    "music_follow3": {4: "upright", 16 + 4: "separate", 32 + 4: "intersect"},
}


class Matrix:
    """Key-matrix read/write (YC500 NJ81).

    The matrix is 128 positions x 4 bytes. Commands:

      read chunk : GET_KEYMATRIX (137), byte[1]=profile, byte[2]=chunk 0..7
      set key    : SET_KEYMATRIX_SIMPLE (19),
                   byte[1]=profile, byte[2]=position, byte[8..11]=config
      fn layer   : GET_FN_SIMPLE (149) / SET_FN_SIMPLE (21)

    Responses to matrix reads do not echo the command byte.
    """

    MATRIX_SIZE = 128
    CHUNKS = 8

    def __init__(self, dev):
        self.dev = dev

    def _read_chunks(self, cmd, profile=0):
        chunks = []
        for chunk in range(self.CHUNKS):
            r = self.dev.command_raw(cmd, bytes([profile, chunk]))
            chunks.append(r)
        return b"".join(chunks)

    def read(self, profile=0):
        """Return list of 128 4-byte key configs."""
        data = self._read_chunks(Cmd.GET_KEYMATRIX, profile)
        return [list(data[i * 4:i * 4 + 4])
                for i in range(self.MATRIX_SIZE)]

    def read_fn(self, profile=0):
        # YC500/NJ81 firmware reads the Fn layer through the inherited
        # GET_FN command. GET_FN_SIMPLE is a write-side command family.
        data = self._read_chunks(Cmd.GET_FN, profile)
        return [list(data[i * 4:i * 4 + 4])
                for i in range(self.MATRIX_SIZE)]

    def set_key(self, position: int, cfg, profile=0):
        assert 0 <= position < self.MATRIX_SIZE
        buf = bytearray(64)
        buf[0] = Cmd.SET_KEYMATRIX_SIMPLE
        buf[1] = profile
        buf[2] = position
        buf[8:12] = cfg
        self.dev.send_feature(checksum.apply(buf, checksum.BIT7))
        time.sleep(0.05)

    def set_fn_key(self, position: int, cfg, profile=0):
        assert 0 <= position < self.MATRIX_SIZE
        buf = bytearray(64)
        buf[0] = Cmd.SET_FN_SIMPLE
        buf[1] = profile
        buf[2] = position
        buf[8:12] = cfg
        self.dev.send_feature(checksum.apply(buf, checksum.BIT7))
        time.sleep(0.05)

    def reset_key(self, position: int, profile=0):
        self.set_key(position, [0, 0, 0, 0], profile)

    def remap(self, position: int, hid_code: int, profile=0):
        self.set_key(position, [0, 0, hid_code & 0xFF, 0], profile)


class Macro:
    """Macro storage (GET/SET_MACRO 0x8B/0x0B, verified on fw 0x0513).

    Read: GET_MACRO (0x8B) [1]=index, [2]=chunk 0..3 -> 256 raw bytes.
    Write: SET_MACRO (0x0B) [1]=index, then 56-byte blocks
    ([2]=chunk, [3]=56, [4]=last-flag) followed by the data bytes.

    Event stream (vendor `buffToMacroEvents`):
      u16LE count (repeat count), then 2-byte events [hid, flags] where
      flags bit7 = up, low 7 bits = delay (0..127 ms).  A delay > 127 ms
      is stored as [hid, flags, d0, d1] with d0/d1 = u16LE delay and the
      next event starting after those 4 bytes.
    """

    SLOTS = 32
    CHUNKS = 4

    def __init__(self, dev):
        self.dev = dev

    def read(self, index: int):
        if not 0 <= index < self.SLOTS:
            raise ValueError("macro index must be 0..31")
        stream = bytearray()
        for chunk in range(self.CHUNKS):
            buf = bytearray(64)
            buf[0] = Cmd.GET_MACRO
            buf[1] = index
            buf[2] = chunk
            self.dev.send_feature(checksum.apply(buf, checksum.BIT7))
            stream += self.dev.get_feature()
            time.sleep(0.02)
        return self.decode(bytes(stream))

    def write(self, index: int, events, repeat: int = 1):
        """Store a macro. `events` is a list of dicts:
        {"hid": int, "up": bool, "delay": int ms}."""
        if not 0 <= index < self.SLOTS:
            raise ValueError("macro index must be 0..31")
        payload = self.encode(events, repeat)
        # pad to a 56-byte multiple
        if len(payload) % 56:
            payload += b"\x00" * (56 - len(payload) % 56)
        chunks = (len(payload) + 55) // 56
        for chunk in range(chunks):
            buf = bytearray(64)
            buf[0] = Cmd.SET_MACRO
            buf[1] = index
            buf[2] = chunk
            buf[3] = 56
            buf[4] = 1 if chunk == chunks - 1 else 0
            buf[5:5 + 56] = payload[chunk * 56:chunk * 56 + 56]
            self.dev.send_feature(checksum.apply(buf, checksum.BIT7))
            time.sleep(0.05)
        time.sleep(0.3)
        return index

    @staticmethod
    def encode(events, repeat: int = 1):
        buf = bytearray([repeat & 0xFF, (repeat >> 8) & 0xFF])
        for ev in events:
            hid = int(ev["hid"]) & 0xFF
            flag = 0x80 if ev.get("up") else 0
            delay = int(ev.get("delay", 0))
            if delay <= 127:
                buf += bytes([hid, flag | delay])
            else:
                buf += bytes([hid, flag, delay & 0xFF, (delay >> 8) & 0xFF])
        buf += b"\x00\x00\x00\x00"
        return bytes(buf)

    @staticmethod
    def decode(data):
        """Return {"repeat": int, "events": [...]} from a raw macro buffer."""
        repeat = data[0] | data[1] << 8
        events = []
        a = 2
        n = data[a:a + 4]
        a += 4
        while a <= len(data):
            if n[0] == 249:
                events.append({"type": "mouse_move", "dx": n[2], "dy": n[3]})
                if n[1]:
                    events.append({"type": "delay", "ms": n[1] >> 1})
                elif a + 2 <= len(data):
                    events.append({"type": "delay",
                                   "ms": data[a] | data[a + 1] << 8})
                    a += 2
            elif 4 <= n[0] <= 239:
                events.append({"type": "keyboard",
                               "hid": n[0],
                               "up": bool(n[1] & 0x80)})
                if n[1] & 0x7F:
                    events.append({"type": "delay", "ms": n[1] & 0x7F})
                    a -= 2
                else:
                    events.append({"type": "delay",
                                   "ms": n[2] | n[3] << 8})
            else:
                events.append({"type": "special", "code": n[0]})
                if n[1] & 0x7F:
                    events.append({"type": "delay", "ms": n[1] & 0x7F})
                    a -= 2
                else:
                    events.append({"type": "delay", "ms": n[2] | n[3] << 8})
            n = data[a:a + 4]
            if n == b"\x00\x00\x00\x00" or not n:
                break
            a += 4
        return {"repeat": repeat,
                "events": [e for e in events
                           if not (e["type"] == "delay" and e["ms"] == 0)]}


class UserPicture:
    """Per-key RGB storage used by the NJ81 user-picture effect.

    YC500 firmware does not accept a conventional bitmap for this feature.
    It stores one RGB888 color for each matrix position and picture layer.
    The vendor's simple command is 0x14 with a BIT7 checksum.
    """

    LAYERS = 5
    POSITIONS = 128

    def __init__(self, dev):
        self.dev = dev

    def set_pixel(self, layer: int, position: int, r: int, g: int, b: int):
        if not 0 <= layer < self.LAYERS:
            raise ValueError("picture layer must be 0..4")
        if not 0 <= position < self.POSITIONS:
            raise ValueError("picture position must be 0..127")
        buf = bytearray(64)
        buf[0] = Cmd.SET_USERPIC_SIMPLE
        buf[1] = layer
        buf[2] = position
        buf[8] = max(0, min(255, int(r)))
        buf[9] = max(0, min(255, int(g)))
        buf[10] = max(0, min(255, int(b)))
        self.dev.send_feature(checksum.apply(buf, checksum.BIT7))
        time.sleep(0.02)

    def set_pixels(self, layer: int, pixels):
        """Write ``(position, r, g, b)`` entries to one picture layer."""
        for position, r, g, b in pixels:
            self.set_pixel(layer, position, r, g, b)

    def read_pixels(self, layer: int = 0):
        """Read one picture layer as a list of 128 (r, g, b) tuples.

        GET_USERPIC (0x8C): [1]=layer, [2]=chunk 0..5. The six replies
        concatenate into 384 raw bytes (no command echo): slot N lives at
        offset N*3. Verified on fw 0x0513.
        """
        if not 0 <= layer < self.LAYERS:
            raise ValueError("picture layer must be 0..4")
        stream = bytearray()
        for chunk in range(6):
            buf = bytearray(64)
            buf[0] = Cmd.GET_USERPIC
            buf[1] = layer
            buf[2] = chunk
            self.dev.send_feature(checksum.apply(buf, checksum.BIT7))
            stream += self.dev.get_feature()
            time.sleep(0.02)
        return [(stream[pos * 3], stream[pos * 3 + 1], stream[pos * 3 + 2])
                for pos in range(self.POSITIONS)]


class Screen:
    """RGB565 screen (NJ81: 160x80, vendor LED config isRgb 16).

    Verified end-to-end on hardware: the screen image is stored per layer
    (0..4), and the screen only enters custom-image view after the host
    activates LED mode 13 (user_picture) with ``param = layer * 16``.

    Upload uses SETTFTLCDDATA (0x25). The device must first be armed with
    GETTFTLCDDATA (0xA5), which carries the frame geometry, the pixel
    length, and the non-black bounding box; it answers byte[1] == 1 when
    ready. Pixel data is column-major RGB565 BIG-endian (hi byte first,
    verified on hardware with a gray ramp) over an exclusive box
    ``[left, right) x [top, bottom)`` (the vendor's ``yfn`` transpose:
    x outer, y inner), 56 bytes per report, BIT7 checksum.
    """

    WIDTH = 160
    HEIGHT = 80

    def __init__(self, dev):
        self.dev = dev

    def probe(self, frame=0, total_frames=0, delay=0, size=0,
              box=(0, 0, 0, 0), tries=10):
        left, top, right, bottom = box
        buf = bytearray(64)
        buf[0] = Cmd.GETTFTLCDDATA
        buf[1] = frame & 0xFF
        buf[2] = total_frames & 0xFF
        buf[3] = delay & 0xFF
        buf[4] = size & 0xFF
        buf[5] = (size >> 8) & 0xFF
        buf[6] = 0
        buf[8] = left & 0xFF
        buf[9] = top & 0xFF
        buf[10] = right & 0xFF
        buf[11] = bottom & 0xFF
        buf[12] = (left >> 8) & 0xFF
        buf[13] = (top >> 8) & 0xFF
        buf[14] = (right >> 8) & 0xFF
        buf[15] = (bottom >> 8) & 0xFF
        buf[16] = (size >> 16) & 0xFF
        buf[17] = (size >> 24) & 0xFF
        data = bytes(buf[1:18])
        for _ in range(tries):
            r = self.dev.command(Cmd.GETTFTLCDDATA, data, scheme=checksum.BIT7)
            if len(r) > 1 and r[1] == 1:
                return True
            time.sleep(0.1)
        return False

    def upload_rgb565(self, pixels, frame=0, total_frames=1, delay=0,
                      box=(0, 0, 0, 0)):
        """Upload column-major RGB565 BIG-endian data for ``box``.

        ``box`` is exclusive: [left, right) x [top, bottom). The caller
        must activate LED mode 13 with ``param = layer * 16`` afterwards
        to make the screen enter custom-image view."""
        if len(pixels) % 2:
            raise ValueError("RGB565 data must be an even number of bytes")
        left, top, right, bottom = box
        if not (0 <= left < right <= self.WIDTH
                and 0 <= top < bottom <= self.HEIGHT):
            raise ValueError("bounding box is outside the 160x80 screen")
        width = right - left
        height = bottom - top
        if len(pixels) != width * height * 2:
            raise ValueError("pixel data does not match the bounding box")
        if not self.probe(frame=frame, total_frames=total_frames,
                          delay=delay, size=len(pixels), box=box):
            raise ValueError("screen did not become ready (probe failed)")
        for offset in range(0, len(pixels), 56):
            chunk = pixels[offset:offset + 56]
            buf = bytearray(64)
            buf[0] = Cmd.SETTFTLCDDATA
            buf[1] = frame & 0xFF
            buf[2] = total_frames & 0xFF
            buf[3] = delay & 0xFF
            buf[4] = (offset // 56) & 0xFF
            buf[5] = ((offset // 56) >> 8) & 0xFF
            buf[6] = len(chunk)
            buf[8:8 + len(chunk)] = chunk
            self.dev.send_feature(checksum.apply(buf, checksum.BIT7))
            time.sleep(0.005)
        return len(pixels)
