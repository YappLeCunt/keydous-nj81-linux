# Keydous NJ81 Linux Driver — Open-Source Keyboard Control (Key Mapping, RGB Lighting, OLED Screen, Music Sync)

A from-scratch, open-source Linux driver and web GUI for the **Keydous NJ81**
wireless mechanical keyboard (and NJ-series boards with VID `0x3151`).
No vendor software, no Windows, no daemon: it talks to the keyboard directly
over raw USB HID feature reports (and optionally Bluetooth BLE) using pure
Python. It was built entirely from reverse-engineering the official Keydous
driver, and every protocol detail below was verified against a live NJ81 on
firmware `0x0513`.

**What you can do with it:**

- Remap any key and edit the Fn layer (writes verified working)
- Drive all NJ81 **RGB lighting effects** with speed, level, direction, color,
  and the vendor's **Dazzle (炫彩) color-cycle** mode
- Upload images to the built-in **160x80 RGB565 OLED-style screen** (5 layers)
- Paint **per-key RGB picture layers** on the board
- Sync the LEDs to **music** (PipeWire FFT, 32 bands) or **screen color** (X11)
- Switch between all **6 onboard profiles**, tune power/debounce/sleep timers,
  backup & restore everything to a JSON file, and trigger a real factory reset

It also serves as the most complete public reference for the **Keydous NJ81
USB protocol** (`docs/FIRMWARE.md`).

## Quick start

```sh
# 1) allow non-root access (raw USB control transfers on interface 2)
sudo cp udev/50-keydous.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger

# 2) launch the web GUI
./keydous-driver gui            # open http://127.0.0.1:8765
```

No pip installs for the USB path — everything uses the standard library
(ctypes + raw `usbfs` ioctls). BLE support is optional (`dbus-next` or
`bleak`).

## Web GUI (http://127.0.0.1:8765)

- **Overview** — live status: firmware, battery (wired + 2.4G dongle),
  active profile, report rate, current effect; quick light apply; 6-profile
  switcher
- **Key mapping** — click any key and assign normal keys, media/system
  functions, mouse buttons, combos, or disabled; a separate **Fn-layer**
  view with working writes (native Fn shortcuts warn before overwrite)
- **Lighting laboratory** — every NJ81 effect with speed / level / direction /
  option / exact RGB / **Dazzle**, plus an animated **live preview** of the
  board and a 32-band **spectrum display** for music follow
- **Image studio** — upload images to the 160x80 RGB565 built-in screen
  (5 layers) or sample an image into **per-key RGB picture layers**, with
  zoom for fine editing
- **Settings** — report rate, keyboard options (Win lock, WASD-arrow swap,
  LED off, ...), **power panel** (debounce, BT/2.4G sleep + deep sleep,
  low-battery threshold), **backup/restore to JSON**, **Bluetooth battery
  read**, and a confirmed **factory reset**

## Command line

```sh
./keydous-driver list
./keydous-driver info
./keydous-driver battery
./keydous-driver profile            # active profile
./keydous-driver profile 2          # switch profile
./keydous-driver report-rate
./keydous-driver report-rate set 1000
./keydous-driver option
./keydous-driver option set win_key_lock=1
./keydous-driver light
./keydous-driver light set breath --speed 2 --value 4 --rgb FFA500
./keydous-driver remap --list              # current key matrix
./keydous-driver remap --get 0             # what is position 0?
./keydous-driver remap --set 0=a           # remap Esc to "A"
./keydous-driver remap --disable 0         # disable a key
./keydous-driver reset                     # factory reset
# BLE (same commands over Bluetooth):
./keydous-driver --ble AA:BB:CC:DD:EE:FF info
```

## Documentation

- [`docs/FIRMWARE.md`](docs/FIRMWARE.md) — the complete **Keydous NJ81 USB
  protocol**: command map, checksums, base/Fn key matrix, LED parameter
  layout (including the verified exact-RGB and Dazzle values), the 160x80
  RGB565 screen upload handshake, per-key picture layers, music/screen
  follow streams, hardware shortcuts, factory reset, and every quirk —
  all verified against a live board
- [`docs/REVERSE_ENGINEERING.md`](docs/REVERSE_ENGINEERING.md) — how it was
  recovered from the vendor software (DMG structure, daemon analysis, JS
  extraction)

| Artifact | What it is | Protocol source |
|---|---|---|
| `Keydous Driver.exe` (2023) | Windows Electron app | `resources/app/dist/index.js` — full FEA_CMD + gRPC client |
| `resources/app/iot_driver.exe` (2023) | Windows daemon (Rust) | embedded `SupportVender` device table (VID/PID/usage) |
| `iot_v217.dmg` (2025) | macOS daemon v2.17 (Rust, gRPC) | BLE (Feasycom NUS) UUIDs, protobuf API, FEA_CMD |
| `Keydous_setup_480.1.113` (2026) | current Windows installer | extracted `iot_driver.exe` (June 2026) |

## How it talks to the keyboard

- **USB identity**: `VID 0x3151`, `PID 0x4010/0x4011` (NJ81/NJ81S/ED),
  usage page `0xFFFF`, usage `2`, interface 2, **65-byte feature reports**
  (report-id 0 + 64 payload bytes).
- **Command layer** (`byte[0]` of the 64-byte report):
  GET_* = SET_* + 128. Full map in `keydous/protocol.py`.
  ```
  SET_REV 0   GET_REV 128   SET_RESERT 2   GET_BATTERY 131
  SET_REPORT 4/132  SET_PROFILE 5/133  SET_KBOPTION 6/134
  SET_LEDPARAM 7/135  SET_SLEDPARAM 8/136  SET_KEYMATRIX 9/137
  SET_KEYENABLE 10/138  SET_MACRO 11/139  SET_USERPIC 12/140
  SET_AUDIO 13  SET_WINDOS 14  GET_INFOR 143
  ```
- **Checksums** (`check_sum_type`): `BIT7` = `byte[7] = 0xFF - (sum(byte[0..6]) & 0xFF)`,
  `BIT8` one byte later, `NONE` = as-is. See `keydous/checksum.py`.
  Several commands silently ignore writes without the right checksum
  (e.g. `SET_PROFILE` needs BIT7; `SET_LEDPARAM` needs BIT8).
- **BLE**: Feasycom / Nordic UART Service
  `49535343-FE7D-4AE5-8FA9-9FAFD205E455`, RX (write)
  `49535343-8841-43f4-A8D4-ECBE34729BB3`, TX (notify)
  `49535343-1E4D-4BD9-BA61-23C647249616`.
- **Architecture**: GUI (Electron) → gRPC `:3814` → `iot_driver` daemon
  → keyboard (USB HID feature reports / BLE NUS). This repo collapses the
  daemon into the client.

## The Linux transport problem (solved)

The vendor HID interface (interface 2) has a feature report but **no input
report**. When `usbhid` owns the interface, *SET* feature reports work but
*GET* feature reports return all zeros. The reliable path is **raw USB
control transfers** (`bmRequestType=0x21/0xA1`, `bRequest=0x09/0x01`,
`wValue=0x0300`, `wIndex=2`) issued after detaching `usbhid` via
`USBDEVFS_DISCONNECT_CLAIM`. See `keydous/rawusb.py`.

## Requirements

* Python 3.8+
* USB: nothing (raw `usbfs` ioctls via ctypes)
* BLE (optional): `pip install dbus-next` (or `bleak`), BlueZ running

Note: the driver detaches `usbhid` from interface 2 while talking to the
keyboard; the keyboard's typing (interfaces 0/1) is unaffected. To rebind
afterwards: `sudo sh -c 'echo -n "3-2:1.2" > /sys/bus/usb/drivers/usbhid/bind'`

## Matrix protocol (YC500 NJ81)

128 positions x 4 bytes `[type, mod, key, key2]`; read = 8 chunks of
GET_KEYMATRIX (0x89), single-key write = SET_KEYMATRIX_SIMPLE (0x13) with
the 4-byte config at bytes 8-11. The Fn layer is readable (GET_FN 0x90) and
writable (SET_FN_SIMPLE 0x15); its factory defaults are firmware-stored, so
the GUI only resets base-layer keys.

User-picture uploads use `USERPIC_SIMPLE` (`0x14`): each visible matrix slot
receives one RGB888 value in a selected layer (0..4), then LED mode 13 is
selected for that layer. The browser performs image sampling, so no image
library is required on the Python side.

## Verified on hardware (NJ81, firmware 0x0513)

* firmware, battery, profile (0..5, BIT7 checksum), report rate (125-1000 Hz)
  read/write
* keyboard options (win-key lock, LED-off, WASD-arrow swap, ...) read/write
* LED effects (off/always-on/breath/wave/ripple/... + RGB + Dazzle) read/write
* key remapping (matrix read + single-key write) verified end-to-end
* Fn-layer writes, per-key picture layers, 160x80 RGB565 screen upload
* power panel: debounce, sleep timers, low-battery threshold (read)
* device wedge recovery via automatic USB reset

## Notes / caveats

* Command maps differ between keyboard generations (dk2017 vs yc200/yc500).
  This driver targets the yc500/yc200 family used by NJ81.
* **Macros are not available on firmware `0x0513`**: `GET/SET_MACRO` are
  ignored by the firmware (reads return stale state, writes don't commit),
  so the GUI does not expose a macro editor.
* The wired USB port reports battery `0%` while charging; the real level is
  only reported over the wireless link (BT / 2.4G dongle) — the GUI reads
  the dongle when present and offers a manual Bluetooth battery read.
* BLE framing: feature reports are written as-is, chunked to the GATT MTU.

## License

MIT — see [LICENSE](LICENSE). This project is not affiliated with Keydous;
it is an independent, clean-room-adjacent implementation derived from
studying the vendor software's behavior.