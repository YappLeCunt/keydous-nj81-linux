# Keydous NJ81 firmware protocol

Reverse-engineered from the vendor software (Windows Electron app
`dist/index.js` 2023, `iot_driver.exe` 2023 + 2026, and the macOS daemon
`iot_v217.dmg` / v2.17). All values below were **verified against a live
NJ81, firmware `0x0513`** over USB - including the screen image upload,
Fn-layer writes, music/screen follow streams, and factory reset.

Verified-on-hardware summary of what works on `0x0513`:

* every GET listed below (firmware, battery, profile, report rate,
  options, base matrix, Fn matrix, LED state, user picture)
* base-layer key writes (`SET_KEYMATRIX_SIMPLE`)
* **Fn-layer writes** (`SET_FN_SIMPLE`) - take effect (verified live)
* LED effects, incl. exact-RGB param 7 and effect level 0..4
* screen image upload (160x80 RGB565, three-phase) + layer activation
* `SET_AUDIO` (music follow) and `SET_WINDOS` (screen follow) streams
* factory reset via command `0x02` (BIT7) and the 4-corner key combo
* profile switching (`SET_PROFILE 0x05` with **BIT7** - NONE is ignored,
  so the old "always profile 0" note was wrong) - 6 profiles, 0..5
* power reads/writes: debounce (`0x91`/`0x11`), sleep timers
  (`0x92`/`0x12`), battery low-power threshold (`0x03`; write is
  accepted but does not persist on `0x0513`)

Not supported on `0x0513`: macro storage. `GET_MACRO (0x8B)` and
`GET_MACRO_SIMPLE (0x96)` return no valid macro data (the read is
ignored and the feature-report read echoes stale state), so the GUI
does not expose a macro editor.

---

## 1. Device identity (USB)

| field | value |
|---|---|
| VID | `0x3151` (ROYUAN / Shenzhen Rongyuan) |
| PID | `0x4010` (direct USB), `0x4011` (2.4G dongle, `dongle_common`) |
| device name | `ROYUAN Keydous NJ81` |
| HID interfaces | 0: keyboard, 1: consumer/system, 2: vendor feature |
| feature interface | iface 2, usage page `0xffff`, usage `2` |
| feature report | 64 bytes, no report id |

Firmware revisions: `0x0513` reads back as `13 05` (LE) → 1299.

## 2. Transport (Linux)

The vendor daemon uses hidapi feature reports. On Linux, **SET feature
reports work but GET returns zeros when `usbhid` owns the interface** (the
interface has no input report, so the kernel HID path breaks reads).
The working transport is **raw USB control transfers** on interface 2:

| op | bmRequestType | bRequest | wValue | wIndex | data |
|---|---|---|---|---|---|
| SET_REPORT | `0x21` | `0x09` | `0x0300` | 2 | 64 bytes |
| GET_REPORT | `0xA1` | `0x01` | `0x0300` | 2 | 64 bytes |

`usbhid` must be detached first via `USBDEVFS_DISCONNECT_CLAIM`
(`_IOR('U', 27, struct usbdevfs_disconnect_claim)`, driver `"usbhid"`,
flag `0x01`). After some SETs (e.g. report-rate change) the device wedges
(`EPIPE`/`EPROTO`, or stale/garbage responses); a `USBDEVFS_RESET`
restores it.

## 3. Feature-report framing

Every command is a 64-byte feature report:

```
byte 0    command (FEA_CMD)
byte 1..  parameters
byte 7/8  checksum (scheme-dependent)
```

### Checksums (`check_sum_type`)

| scheme | value | computation |
|---|---|---|
| `BIT7` | 0 | `byte[7] = 0xFF - (Σ byte[0..6] & 0xFF)` |
| `BIT8` | 1 | `byte[8] = 0xFF - (Σ byte[0..7] & 0xFF)` |
| `NONE` | 2 | none |

The response echoes the command byte in `byte[0]` (except bulk matrix
reads) followed by the result data.

## 4. Command map (yc500 family = NJ81)

GET = SET + 128 unless noted.

| SET | GET | name | payload / response |
|---|---|---|---|
| 0x00 | 0x80 | REV | resp `[1:3]` = firmware (LE 16) |
| 0x02 | — | RESERT | factory reset (BIT7, byte[1..] = 0) |
| 0x03 | — | BATTERY_LP | `[1]` low-battery warn % (write accepted, not persisted on 0x0513) |
| — | 0x83 | BATTERY | resp `[1]`=%, `[2]`: 1 charging, 2 full, else uncharging, `[3]`=LP threshold |
| 0x04 | 0x84 | REPORT | `[1]`=profile, `[2]`=rate code (1=1k,2=500,4=250,8=125 Hz) |
| 0x05 | 0x85 | PROFILE | `[1]`=profile number - requires **BIT7** (NONE is ignored); 6 profiles 0..5 |
| 0x06 | 0x86 | KBOPTION | `[2]` bitfield, `[3]` fn-matrix, `[4]` power-save (see §7) |
| 0x07 | 0x87 | LEDPARAM | see §6 |
| 0x08 | 0x88 | SLEDPARAM | side LED |
| 0x09 | 0x89 | KEYMATRIX | matrix read: `[1]`=profile, `[2]`=chunk 0..7, 8×64=512 B |
| 0x0A | 0x8A | KEYENABLE | key enable mask |
| 0x0B | 0x8B | MACRO | `[1]`=index, `[2]`=chunk 0..3 - ignored on 0x0513 (see §8) |
| 0x0C | 0x8C | USERPIC | RGB picture (read = 6-7 chunks of RGB bytes, see §9) |
| 0x0D | — | AUDIO | music-follow stream (see §13) |
| 0x0E | — | WINDOS | screen data stream (see §13) |
| — | 0x8F | INFOR | device info |
| 0x10 | 0x90 | FN | Fn-layer matrix, same chunk layout as KEYMATRIX |
| 0x11 | 0x91 | DEBOUNCE | resp `[2]` debounce ms; set `[2]`=value |
| 0x12 | 0x92 | SLEEPTIME | resp u16LE at `[1],[3],[5],[7]` = BT/2.4G sleep + deep sleep min; set at `[8..15]` |
| 0x18 | 0x98 | USERGIFSTART | GIF upload start (Y300/gif boards) |
| 0x19 | 0x99 | USERGIF | GIF frame data |
| 0x24 | — | OLEDGIFDATA | monochrome OLED image/GIF upload |
| 0x25 | 0xA5 | TFTLCDDATA | RGB565 screen upload / arm probe (see §10) |
| 0x29 | 0xA9 | SCREEN_24BITDATA | 24-bit screen upload variant |
| 0x2B | 0xAB | OLEDEFFECT | screen effect selector (OLED boards) |
| 0x30 | 0xB0 | OLEDBOOTLOADER | enter OLED bootloader (`55 AA 55 AA` magic) |
| 0x31 | 0xB1 | OLEDBOOTSTART / CHECKSUM | OLED boot packet count / final sum |
| 0xAD | — | GETOLED_VERSION | OLED version probe: echoes 0xAD if present |
| 0x7E | — | INTO_TEST | enter test mode |
| 0x7F | — | SET_BOOTLOATER | enter bootloader (OTA) |

### YC500 "simple" (single-key) commands — used by NJ81

| SET | GET | name | layout |
|---|---|---|---|
| 0x13 | 0x93 | KEYMATRIX_SIMPLE | `[1]`=profile, `[2]`=position, `[8..11]`=key config |
| 0x14 | 0x94 | USERPIC_SIMPLE | single-color pixel set |
| 0x15 | 0x95 | FN_SIMPLE | Fn layer, same layout (writes verified working) |
| 0x16 | 0x96 | MACRO_SIMPLE | `[1]`=index, `[2]`=chunk, `[3]`=len, `[4]`=last flag |
| 0x17 | 0x97 | CMD_AUTOOSEN | `[1]` 0/1 |

**Trap:** `GET_FN_SIMPLE (0x95)` is *not* a valid Fn read on `0x0513` -
it returns garbage/shifted data (often the base matrix). Always read the
Fn layer with `GET_FN (0x90)`, `byte[1]`=profile, `byte[2]`=chunk 0..7.
This mistake made Fn writes look "ignored" in early development.

`USERPIC_SIMPLE` writes one RGB888 value for one matrix slot:

```
byte[0]    0x14
byte[1]    picture layer 0..4
byte[2]    matrix position 0..127
byte[7]    BIT7 checksum
byte[8:11] red, green, blue
```

The vendor UI samples an image into visible-key colors, sends these packets,
then selects LED mode 13 with param `layer * 16`. The Linux GUI follows the
same order. `GET_USERPIC_SIMPLE` is declared by the vendor but not used by
it, so the GUI keeps the upload preview as its source of truth.

OLED / TFT commands (0x22..0x2B, 0x30..0x31) exist for OLED variants.

### Screen / TFT image upload (NJ81: RGB565 160x80)

The NJ81 screen is 160x80 RGB565 (`otherSetting.Ku` =
`LED:{isRgb:"16", kbW:160, kbH:80, size:2, layer:["1".."5"]}`) - the
physical module may differ, but this is the framebuffer the firmware
uses, verified end-to-end. Upload is three phases:

1. Arm with `GETTFTLCDDATA` (0xA5), BIT7 checksum, 17 data bytes:
   `[frame=layer, totalFrames=1, delay=0, sizeLo, sizeHi, 0, 0, left,
   top, right, bottom, leftHi, topHi, rightHi, bottomHi, sizeHi2,
   sizeHi3]` — the device answers `byte[1] == 1` when ready.
2. Stream `SETTFTLCDDATA` (0x25) reports: `[layer, 1, 0, chunkLo,
   chunkHi, realLen, 0, BIT7-ck, 56 data bytes]`, one report per 56-byte
   chunk.
3. Activate with `SET_LEDPARAM` mode 13 (user picture), `param =
   layer * 16` — this switches the screen to custom-image view.
   `Fn+Delete` on the keyboard cycles through the stored layers.

Pixel data is column-major RGB565 BIG-endian (hi byte first, verified on
hardware with a gray ramp; little-endian produces rainbow smears on gray)
over the non-black bounding box (exclusive: `[left, right) x [top,
bottom)`), matching the vendor's `yfn` conversion loop (x outer, y inner)
and wire order (`push(r[1]), push(r[0])`). A classic
monochrome OLED (0.91" 128x32 / 1.3" 128x64) instead uses
`SET_OLEDGIFDATA` (0x24): `[frameNum-1, chunk, currentFrame, frameDelay,
layer, 0, BIT7-ck, 56 bytes]` with 1-bit column-major LSB-first packing.

Screen presence: `GETOLED_VERSION` (0xAD) echoes 0xAD only on OLED
controllers; the RGB565 screen answers the 0xA5 arm with `byte[1]==1`.
The Linux driver implements the RGB565 path (`keydous/protocol.py`,
`Screen`). Do not probe during background status refreshes; the screen must
be open with the keyboard shortcut before an upload.

Observed screen-state behavior (0x0513):

* after a completed upload the arm probe can keep answering
  `byte[1]==0` (busy) for a long time; a power cycle clears it. The
  upload data is still accepted if streamed directly after a fresh arm.
* the image is stored per layer; the custom-image view only shows after
  LED mode 13 is activated for that layer.

## 5. Key matrix

128 positions × 4 bytes = 512 bytes total, read in **8 chunks** (64 B
each): `GET_KEYMATRIX`, `byte[1]`=profile, `byte[2]`=chunk. The response
does **not** echo the command byte (raw matrix data).

Each position is `[type, b1, b2, b3]`:

| type | meaning | layout |
|---|---|---|
| 0 | normal key / combo | `[0, mod, key, key2]` — mod: 224 Ctrl, 225 Shift, 226 Alt, 227 Win; key/key2 = HID usage codes |
| 0 | disabled | `[0,0,0,0]` or `[0,0,1,0]` |
| 1 | mouse button | see §5.3 |
| 3 | system/media function | see §5.2 |
| 9 | macro | `[9, macroType, macroIndex, 0]` (0 repeat-times, 1 on/off, 2 touch-repeat) |
| 10 | special | `[10,1,0,0]` Fn, `[10,1,1,0]` right-Fn, `[10,13,0,0]` Fn+lock |
| 11 | turbo ("fire") | `[11,0,0,0]` |
| 18 | Siri | `[18,0,227,44]` |
| 19 | DPI (mouse) | `[19,0,n,0]` |

### 5.1 Normal keys
`[0, 0, hidCode, 0]` — `hidCode` = USB HID keyboard usage (Esc=41, A=4,
1=30, F1=58, LShift=225, LWin=227, ...). Full table: `hid_key_names.json`.

### 5.2 System / media functions
`[3, 0, x, y]`:

| function | config |
|---|---|
| Prev / Next / Stop / Play-Pause | `[3,0,182/181/183/205,0]` |
| Mute / Vol- / Vol+ | `[3,0,226/234/233,0]` |
| Calculator / Email / My PC | `[3,0,146/138/148,1]` |
| Search / Home / Back / Refresh | `[3,0,33/35/36/39,2]` |
| Brightness - / + | `[3,0,112/111,0]` |

### 5.3 Mouse buttons
`[1, 0, x, y]`:

| button | config |
|---|---|
| Left / Right / Middle | `[1,0,240/241/242,0]` |
| Forward / Back | `[1,0,243/244,0]` |
| Wheel L / R / Fwd / Back | `[1,0,245/246/247/248,0]` |
| Scroll up / down | `[1,0,245,1]` / `[1,0,245,255]` |
| X up / down, Y up / down | `[1,0,246,251/5]` / `[1,0,247,251/5]` |

### 5.4 Combos
`[0, mod, key, key2]` e.g. `[0,225,47,0]` = Shift+`[`, `[0,0,227,15]` = Win+L,
`[0,224,44,0]` = Ctrl+Space (IME switch).

### 5.5 Fn layer (verified on 0x0513)

The Fn layer is a second 128×4 matrix, read with `GET_FN (0x90)` and
written per key with `SET_FN_SIMPLE (0x15)` - **writes take effect**
(verified live; slot 42 accepted a marker and read it back).

The Fn factory defaults are stored in the firmware and are **not
exported** by any command, so a per-key Fn reset is impossible from the
host; only the 4-corner hardware reset restores them. Known factory Fn
assignments (type-19 specials) read from a factory-reset board:

| physical key | Fn slot | config | function |
|---|---|---|---|
| Delete | 85 | `[19,0,0,0]` | screen cycle (enter/exit custom-screen view) |
| PgUp | 86 | `[19,1,1,0]` | screen font color |
| PgDn | 87 | `[19,1,0,0]` | screen background color |
| (nav) | 71 | `[19,2,0,0]` | unknown special |

Keys with any non-empty Fn assignment are treated as **reserved** by the
Linux GUI: base-layer remapping/reset is blocked so hardware shortcuts
(Fn+Delete, Fn+PgUp/PgDn, brightness/media rows, connectivity keys)
cannot be lost accidentally.

### 5.6 Hardware shortcuts & factory reset (from the NJ81 manual)

| combo | function |
|---|---|
| `Fn + Right Ctrl` | open/close the screen |
| `Fn + Delete` | enter/exit the custom-screen interface |
| `Fn + PgUp` | change screen font color |
| `Fn + PgDn` | change screen background color |
| `Esc + Left Ctrl + F12 + Right Arrow` (3 s) | factory reset (wipes mappings, macros, profiles, images, lighting) |

`Fn + Delete` cycles the displayed picture layer while LED mode 13 is
active; the screen image upload uses this to switch stored pictures.

## 6. LED (LEDPARAM 0x07/0x87)

```
byte 1  mode (YC500 numbering, see below)
byte 2  4 - speed          (MAXSPEED=4; byte 4+ = slowest)
byte 3  value (effect level, 0..4 on the NJ81 vendor profile)
byte 4  param (see below)
byte 5-7 RGB - sent literally (white 0xFFFFFF is rendered white and
        echoes back as 0x969696, the firmware's white drive level; the
        old yc200 marker 0xFB0EFA is NOT white on this board and renders
        pink/magenta - never send it)
byte 8  BIT8 checksum - REQUIRED: without it the device shows the
        effect transiently but does not commit (GET keeps old value)
```

Param byte semantics (verified on NJ81 fw 0x0513):
- low nibble 0-5: device substitutes preset color COMMONCOLOR[n]
  (0=red, 1=green, 2=blue, 3=orange, 4=magenta, 5=yellow, 6=white)
  and IGNORES the sent RGB - this caused the "tinted keys" behavior.
- low nibble 6 (DAZZLE, vendor "炫彩"): exact RGB ignored, the effect
  cycles colors automatically; shown on readback as `dazzle`.
- low nibble 7 (NORMAL): exact RGB from bytes 5-7 is displayed. Use 7.
- high nibble: direction/option bits for wave (0/16/32/48),
  snake/kaleidoscope/line-wave/circle-wave/fireworks (0 vs 16),
  user picture (0/16/32/48/64), music modes (base 4).
- trigger modes 8 (`press_action`), 9 (`coverage`), and 19
  (`press_action_off`) use param 0 as their vendor-defined trigger setting;
  do not replace it with the color sentinel.

| mode | name |
|---|---|
| 0 | off (send `value=0`, `param=7`) |
| 1 | always on |
| 2 | breath |
| 3 | neon |
| 4 | wave (param high nibble: right=0,left=1,down=2,up=3) |
| 5 | ripple |
| 6 | raindrop |
| 7 | snake (0 z / 16 return) |
| 8 | press action |
| 9 | coverage |
| 10 | sine wave |
| 11 | kaleidoscope (0 out / 16 in) |
| 12 | line wave (0 right / 16 left) |
| 13 | user picture (screen image view: `param = layer * 16`) |
| 14 | laser |
| 15 | circle wave (0 anti-clockwise / 16 clockwise) |
| 16 | dazzling |
| 17 | rain down |
| 18 | meteor |
| 19 | press action off |
| 20 | music follow 3 (param base 4) |
| 21 | screen color |
| 22 | music follow 2 (param base 4) |
| 23 | train |
| 24 | fireworks (0 right / 16 left) |

Verified on firmware 0x0513: the vendor profile constrains byte 3 to 0..4.
Sending the old Linux value 128 produces rough animation; value 4 matches
the vendor-range packet and renders smoothly. Speed byte 4 is the slowest
setting tested; lower values are faster. Mode 0 (off) is applied with
`value=0` and `param=7` (sending a missing param table entry used to
abort the request entirely).

## 7. KBOPTION bitfield (byte 2)

| bit | option |
|---|---|
| 0x01 | win-key lock |
| 0x04 | system (left win ↔ alt swap region) |
| 0x08 | WASD ↔ arrows |
| 0x10 | LED off |
| 0x20 | side-LED off |
| 0x40 | keyboard mode |
| 0x80 | keyboard lock |

`byte[3]` = fn-key matrix flag, `byte[4]` = power-save.

## 8. Macros

**Not available on `0x0513`.** The protocol is documented from the vendor
app (class `yc500_nj81`, same command numbering as this board): read
`GET_MACRO (0x8B)`, `byte[1]`=index, `byte[2]`=chunk 0..3 → 256 B of
events; write `SET_MACRO (0x0B)` with an 8-byte header
`[0x0B, index, 0, 1, chunk, 0, 0, ...]` + 56 B of event data in 5 chunks.
Event format is the vendor `buffToMacroEvents` stream: u16LE repeat
count, then 2-byte events `[hid, flags]` (flags bit7 = up, low7 =
delay ms, or a 2-byte u16LE delay when low7 is 0). A key bind is
`[9, macroType, macroIndex, 0]` (§5).

Verified on the live board: both `GET_MACRO (0x8B)` and
`GET_MACRO_SIMPLE (0x96)` are ignored - the feature-report read returns
stale state instead of macro data, and `SET_MACRO (0x0B)` writes are
not committed. The GUI therefore does not expose a macro editor.

## 9. User picture layers (per-key RGB)

Separate from the TFT screen: LED mode 13 can also render a per-key RGB
image on the keyboard LEDs, stored in five layers.

* Write one key: `USERPIC_SIMPLE (0x14)` -
  `[0x14, layer 0..4, position 0..127, 0x00 x4, BIT7, r, g, b]`.
* Bulk read: `GET_USERPIC (0x8C)` with `[1]`=0, `[2]`=chunk 0..6 -
  concatenated replies carry 384 RGB bytes (128 keys x 3) in slot order.
  Verified live on `0x0513`.
* Activate a layer: `SET_LEDPARAM` mode 13, `param = layer * 16`
  (USEROP: layer 1→0, 2→16, 3→32, 4→48, 5→64).

The vendor UI samples an image into visible-key colors, writes the
pixels, then selects mode 13. `GET_USERPIC_SIMPLE (0x94)` is declared by
the vendor but never used; the Linux GUI keeps the preview as truth.

## 10. BLE

Feasycom / Nordic UART Service (vendor BLE module):

| GATT | UUID |
|---|---|
| service | `49535343-FE7D-4AE5-8FA9-9FAFD205E455` |
| RX (host→kb, write) | `49535343-8841-43f4-A8D4-ECBE34729BB3` |
| TX (kb→host, notify) | `49535343-1E4D-4BD9-BA61-23C647249616` |

Same FEA_CMD reports are streamed over the UART pipe (chunked to the GATT
MTU). OTA runs over the same link with chunk + checksum framing
("checksum err, please upgrade again" on mismatch).

## 11. Dongle (2.4G, `dongle_common`)

Dongle devices (PID `0x4011` etc.) first run a dangle handshake
(`0xF6` set-device, `0xF7` check 2.4G status, get-device-id) before
relaying FEA reports; the routing device type is `dangle_dev_type`
(0 dev, 1 dangle-keyboard, 2 dangle-mouse).

## 12. gRPC daemon API (reference)

The vendor daemon exposes `proto.driver.DriverGrpc` on `127.0.0.1:3814`
(insecure): `watchDevList`, `watchVender`, `watchSystemInfo`, `sendMsg`,
`readMsg`, `sendRawFeature`, `readRawFeature`, `setLightType`,
`upgradeOTAGATT`, `muteMicrophone`, `toggleMicrophoneMute`,
`getMicrophoneMute`. `sendMsg(device_path, msg, check_sum_type,
dangle_dev_type)`. This driver collapses the daemon into the client.

## 13. Quirks & timing

* after `SET_REPORT` (rate change) the device briefly returns
  shifted/stale responses, then self-recovers; a USB reset also clears it.
* rapid back-to-back Fn writes can wedge the interface (`EBUSY`); space
  the writes out (>= 0.5 s) and the transport's USB-reset recovery
  clears the wedge.
* Fn-layer reads can occasionally return inconsistent values for one
  read (observed type byte flipping on a factory board); re-read to
  confirm before writing.
* `GET_FN_SIMPLE (0x95)` is not a valid Fn read - it returns garbage.
* `SET_PROFILE` requires the **BIT7** checksum; with NONE the write is
  silently ignored and the device stays on its current profile. With BIT7
  all six profiles (0..5) switch correctly (verified).
* `SET_BATTERY_LP (0x03)` is accepted but the threshold never changes on
  `0x0513` (GET_BATTERY `[3]` stays 0).
* matrix reads must not be echo-validated (raw data responses).
* a missing `YC500_PARAM` entry for mode 0 used to abort the "off"
  request - the GUI now sends `param=7, value=0` for off.
* `SET_LEDPARAM` requires the BIT8 checksum to commit; without it the
  effect shows transiently but `GET_LEDPARAM` keeps the old value.

## 14. Music / screen follow streams

* Music (LED modes 20/22): `SET_AUDIO (0x0D)` reports at ~30 fps:
  `[0x0D, 0x00 x6, BIT7, 32 band bytes]`. The vendor derives the bands
  from a 100-bin FFT over system audio: normalize bins 0..100 against the
  quiet range (bins 20..40), clamp to the keyboard count (6), emit bins
  27..59. The Linux driver captures the PipeWire monitor (`pw-record`)
  and replicates the pipeline in pure Python.
* Screen (LED mode 21): `SET_WINDOS (0x0E)` reports at ~16 fps:
  `[0x0E, R, G, B, A, 0x00 x2, BIT7]` where RGBA is the average screen
  color (the vendor downscales the whole desktop to 1x1). The Linux
  driver samples the X11 root window via libX11 (ctypes, no installs).

Streams run only while their LED mode is active; switching modes stops
them automatically. On Linux, PipeWire auto-creates a sink monitor when
recorded from by name (`<default-sink>.monitor`), so no audio setup is
needed.

## 15. Linux driver architecture (keydous/)

| module | role |
|---|---|
| `rawusb.py` | raw USB control transfers on iface 2 (detach usbhid, wedge recovery via USB reset) |
| `transport.py` | hidraw transport (older path; SET works, GET reads are unreliable) |
| `checksum.py` | BIT7 / BIT8 / NONE |
| `protocol.py` | commands, `Keyboard`, `Matrix` (base + Fn), `UserPicture`, `Screen` |
| `follow.py` | music (PipeWire + pure-Python FFT) and screen (libX11 ctypes) streams |
| `cli.py` / `gui.py` / `gui.html` | terminal and local web UI |

The GUI holds one shared device handle under a lock; the follow streams
send through the same lock so background capture cannot race other
commands.
