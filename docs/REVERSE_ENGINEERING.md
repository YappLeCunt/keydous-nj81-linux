# Reverse engineering notes

How the protocol was recovered from the vendor software.

## Artifacts used

| artifact | content | extracted |
|---|---|---|
| `Keydous Driver.exe` (2023) | Electron app | `resources/app/dist/index.js` (4.8 MB, all commands) |
| `resources/app/iot_driver.exe` (2023) | Rust daemon (Windows) | `SupportVender` device table via `strings` |
| `iot_v217.dmg` (2025) | macOS daemon v2.17 | UDZO DMG → zlib streams → raw GPT image → mach-O binaries |
| `Keydous_setup_480.1.113` (2026-06) | NSIS installer | extracted with 7-Zip (`$PLUGINSDIR/app-32.7z`) → current `iot_driver.exe` |

## The DMG

`iot_v217.dmg` is a **UDIF (UDZO) image**: the data fork is concatenated
zlib streams (mostly 1 MiB blocks) followed by the `koly` trailer with an
XML plist describing the (fake) GPT partition map. Decompressing the
streams yields a GPT disk image whose "APFS" partition is actually the
**app binaries**; the GPT is a wrapper. The code-signature blob
(`Developer ID Application: Shenzhen Rongyuan Technology Co., Ltd.
4Z4GV36XH8`) and timestamp (2025-11-03) confirm provenance.

## The daemon

Both daemons are **Rust** (`iot_driver`), built with `btleplug`, `tonic`
(gRPC), `prost` (protobuf), `sled`, `cpal`. Recovered from strings:

* FEA_CMD enum (25 values) and `SupportDev` table (vid/pid/usage/
  usage_page/interface/report_id/dongle_common/ble)
* BLE: Feasycom NUS UUIDs; `src/dj_dev_api/ble_hid.rs`,
  `src/dj_dev_api/dangle_common.rs`, `src/ble_upgrade/mod.rs`
* gRPC: `proto.driver.*` messages, port 3814
* dangle handshake (F6/F7 commands), OTA checksum framing

## The command map

`dist/index.js` (minified webpack bundle) contains per-board classes:
`USBDevice` base → YC200/YC500 → `yc500_nj81`. Recovered:

* FEA_CMD values per class (`this.FEA_CMD_SET_REV=0` ...)
* checksum schemes (`BIT7/BIT8/NONE`, `255-(sum&0xFF)`)
* matrix format: 8×64-byte chunked reads; `[type,mod,key,key2]` entries
* `setKeyConfigSimple` / `configToChangeArr` → 4-byte encodings for
  normal keys, combos, media, mouse, macros
* key tables: `HidMapping` (hidCode→name), `specialFunTablectionMap`,
  combo table, `MouseKey` enum
* `yc500_nj81` layout (80 keys, x/y/w/h) + `yc500_nj81Matrix` default
  matrix → saved as `nj81_layout.json` / `nj81_matrix.json`

## Linux transport discovery

hidapi-style SET feature reports worked, but GET returned zeros with
`usbhid` bound. Raw `USBDEVFS` control transfers (`0x21/0xA1` ×
`0x09/0x01`, `wValue 0x0300`) after `USBDEVFS_DISCONNECT_CLAIM` work
reliably — this is how `keydous/rawusb.py` talks to the board.

## Verification

Every protocol detail was verified live on an NJ81 (firmware 0x0513):
reads/writes of firmware, battery, profile, report rate, keyboard
options, LED modes/colors, full key-matrix read, and single-key remap
(read-back confirmed).
