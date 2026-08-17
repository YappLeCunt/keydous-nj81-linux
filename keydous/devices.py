"""Device database recovered from iot_driver's embedded `SupportVender` table.

Keydous keyboards expose two personalities:
  * USB wired / dongle (2.4G): a vendor HID interface.
      vid 0x3151, usage_page 0xffff, usage 2, bInterfaceNumber 2,
      feature report length 65 (report-id + 64 bytes).
  * BLE: the keyboard advertises as a vendor HID over GATT using the
      Feasycom/Nordic UART Service, reachable only over the air.
"""

from dataclasses import dataclass, field
from typing import Optional

# --- BLE GATT service/characteristic UUIDs (from macOS iot_v217 binary) ---
# Feasycom / Nordic UART Service used by the Keydous BLE module.
BLE_SERVICE_UUID = "49535343-FE7D-4AE5-8FA9-9FAFD205E455"
BLE_RX_UUID = "49535343-8841-43f4-A8D4-ECBE34729BB3"    # host -> keyboard (write)
BLE_TX_UUID = "49535343-1E4D-4BD9-BA61-23C647249616"    # keyboard -> host (notify)


@dataclass
class DevDesc:
    vid: int
    pid: int
    usage: int = 2
    usage_page: int = 0xFFFF
    interface_number: int = 2
    feature_report_len: int = 65
    dongle_common: bool = False
    ble: bool = False
    name: str = ""
    display_name: str = ""

    def usb_match(self, vid, pid, usage, usage_page) -> bool:
        return (self.vid == vid and self.pid == pid
                and self.usage == usage and self.usage_page == usage_page)


def _d(pid, name, display, dongle=False, ble=False, usage=2, up=0xFFFF, itf=2):
    return DevDesc(0x3151, pid, usage, up, itf, dongle_common=dongle, ble=ble,
                   name=name, display_name=display)


# Recovered from iot_driver.exe (2023) SupportVender table + Electron config.
DEVICES: dict[int, DevDesc] = {}


def _reg(desc: DevDesc) -> DevDesc:
    DEVICES[desc.pid] = desc
    return desc


# NJ81 family (YC500, feature report len 65, usage 2, usage_page 0xffff)
_reg(_d(0x4010, "yc500_nj81", "NJ81", dongle=True))
_reg(_d(0x4011, "yc500_nj81", "NJ81", dongle=True))
_reg(_d(0x4015, "yc500_nj81s", "NJ81S", dongle=True))
_reg(_d(0x4018, "yc500_nj81_ed", "NJ81-ED"))
_reg(_d(0x401B, "yc500_nj81s_ed", "NJ81S-ED"))

# Other Keydous keyboards seen in the same table
_reg(_d(0x4007, "yc200_nj80", "NJ80", dongle=True))
_reg(_d(0x4008, "yc200_nj80", "NJ80", dongle=True))
_reg(_d(0x400B, "yc200_nj68", "NJ68", dongle=True))
_reg(_d(0x4021, "yc500", "YC500", dongle=True))

# BLE personalities: the keyboard's BLE HID interface.
_reg(_d(0x4012, "ble", "NJ BLE", ble=True, usage=0x202, up=0xFF66, itf=-1))
_reg(_d(0x4013, "ble", "NJ BLE", ble=True, usage=0x202, up=0xFF55, itf=-1))
_reg(_d(0x401C, "ble", "NJ BLE", ble=True, usage=0x202, up=0xFF55, itf=-1))


def find_usb(vid: int, pid: int, usage: int, usage_page: int) -> Optional[DevDesc]:
    d = DEVICES.get(pid)
    if d and d.usb_match(vid, pid, usage, usage_page) and not d.ble:
        return d
    return None


def lookup(pid: int) -> Optional[DevDesc]:
    return DEVICES.get(pid)