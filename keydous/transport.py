"""HID transports: USB via Linux hidraw ioctls, BLE via BlueZ D-Bus.

USB path uses zero external dependencies (fcntl.ioctl + sysfs).

Permissions: /dev/hidraw* is normally root-only. Install the bundled
udev rule (udev/50-keydous.rules) or run as root.
"""

import errno
import fcntl
import os
import re
import struct

from . import checksum
from .devices import BLE_RX_UUID, BLE_SERVICE_UUID, BLE_TX_UUID, DevDesc

# hidraw ioctl numbers: HIDIOCSFEATURE(len) / HIDIOCGFEATURE(len) are
# _IOC(_IOC_WRITE|_IOC_READ, 'H', nr, len) - the buffer length is encoded
# into the ioctl number itself, so it must be computed for our report size.
def _hid_ioctl(nr: int, size: int) -> int:
    return (0x03 << 30) | (size << 16) | (ord("H") << 8) | nr


# Feature report: 1 report-id byte + 64 payload bytes.
FEATURE_LEN = 65
HIDIOCSFEATURE = _hid_ioctl(0x06, FEATURE_LEN)
HIDIOCGFEATURE = _hid_ioctl(0x07, FEATURE_LEN)


class KeydousError(Exception):
    pass


# --------------------------------------------------------------------------
# USB (hidraw)
# --------------------------------------------------------------------------

class HidrawUSB:
    """Talk to a Keydous keyboard over /dev/hidraw*.

    The keyboard's feature interface reports a 65-byte feature report
    (report-id 0 + 64 payload bytes). All command buffers are 64 bytes
    and are wrapped with a leading report-id byte for the ioctl.
    """

    def __init__(self, dev: DevDesc, path: str):
        self.dev = dev
        self.path = path
        self.fd: int = -1

    # -- enumeration ------------------------------------------------------
    @staticmethod
    def enumerate(system_dir: str = "/sys/class/hidraw") -> list["HidrawUSB"]:
        found = []
        for name in sorted(os.listdir(system_dir)):
            base = os.path.join(system_dir, name)
            if not os.path.isdir(base):
                continue
            info = HidrawUSB._read_sys(base)
            if info is None:
                continue
            vid, pid, usage, usage_page, itf = info
            # The vendor table pins the feature interface: usage 2 + 0xffff.
            if not (usage == 2 and usage_page == 0xFFFF):
                continue
            dev = DevDesc(vid, pid, usage, usage_page, itf)
            found.append(HidrawUSB(dev, f"/dev/{name}"))
        return found

    @staticmethod
    def _read_sys(base: str):
        # vid/pid come from the HID uevent (HID_ID or MODALIAS).
        try:
            with open(os.path.join(base, "device/uevent"), "r") as fh:
                uevent = fh.read()
        except (OSError, FileNotFoundError):
            return None

        vid = pid = None
        m = re.search(r"HID_ID=[0-9a-fA-F]+:([0-9a-fA-F]{8}):([0-9a-fA-F]{8})",
                      uevent)
        if m:
            vid, pid = int(m.group(1), 16), int(m.group(2), 16)
        else:
            m = re.search(r"MODALIAS=hid:b[0-9a-fA-F]+g[0-9a-fA-F]+"
                          r"v([0-9a-fA-F]{8})p([0-9a-fA-F]{8})", uevent)
            if m:
                vid, pid = int(m.group(1), 16), int(m.group(2), 16)
        if vid is None or pid is None:
            return None

        # Interface number: the HID device sits under `<usb>:1.N` in sysfs.
        itf = HidrawUSB._interface_number(base)

        usage, usage_page = HidrawUSB._top_level_usage(base)
        return vid, pid, usage, usage_page, itf

    @staticmethod
    def _interface_number(base: str):
        path = os.path.realpath(os.path.join(base, "device"))
        parent = os.path.basename(os.path.dirname(path))
        m = re.search(r":1\.(\d+)$", parent)
        return int(m.group(1)) if m else -1

    @staticmethod
    def _top_level_usage(base: str):
        rdesc = os.path.join(base, "device/report_descriptor")
        try:
            with open(rdesc, "rb") as fh:
                data = fh.read()
        except (OSError, FileNotFoundError):
            return 0, 0
        usage = 0
        usage_page = 0
        # Capture the top-level (pre-collection) Usage Page and Usage,
        # which identify the interface (e.g. 0xFFFF/2 for the feature iface).
        for tag, type_, size, val in _hid_items(data):
            if type_ == 1 and tag == 0:      # Global Usage Page
                usage_page = val
            elif type_ == 2 and tag == 0:    # Local Usage
                usage = val & 0xFF
            elif type_ == 0 and tag == 10:   # Main Collection: stop
                break
        return usage, usage_page

    # -- open/close -------------------------------------------------------
    def open(self) -> None:
        try:
            self.fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError as e:
            raise KeydousError(
                f"permission denied opening {self.path}: install "
                f"udev/50-keydous.rules or run with sudo") from e
        except OSError as e:
            raise KeydousError(f"failed to open {self.path}: {e}") from e

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    # -- feature reports --------------------------------------------------
    def send_feature(self, payload: bytes) -> int:
        """Send a 64-byte feature-report payload (command buffer)."""
        assert len(payload) == 64
        buf = bytearray(65)
        buf[0] = 0                       # report id
        buf[1:] = payload
        return fcntl.ioctl(self.fd, HIDIOCSFEATURE, bytes(buf))

    def get_feature(self, length: int = 65) -> bytes:
        """Read the feature report response. Returns the payload (bytes[1:])."""
        buf = bytearray(length)
        buf[0] = 0                       # report id to read
        fcntl.ioctl(self.fd, HIDIOCGFEATURE, bytes(buf))
        return bytes(buf[1:])

    # -- command round-trip ----------------------------------------------
    def command(self, cmd: int, data: bytes = b"",
                scheme: int = checksum.BIT7, pad: int = 64) -> bytes:
        buf = bytearray(pad)
        buf[0] = cmd & 0xFF
        for i, b in enumerate(data):
            buf[1 + i] = b
        buf = checksum.apply(buf, scheme)
        self.send_feature(buf)
        resp = self.get_feature()
        if len(resp) == 0:
            raise KeydousError("empty feature-report response")
        return resp


def _hid_items(data: bytes):
    """Minimal HID report-descriptor parser.

    Yields (tag, type, size, value) for short items.
    Item byte layout: bits[7:4]=bTag, bits[3:2]=bType, bits[1:0]=bSize.
    bType: 0=Main, 1=Global, 2=Local. bSize: 0=0,1=1,2=2,3=4 bytes.
    """
    i = 0
    n = len(data)
    short_size = {0: 0, 1: 1, 2: 2, 3: 4}
    while i < n:
        b = data[i]
        i += 1
        if b == 0xFE:                      # Long item
            i += 2 + data[i + 1] if i + 1 < n else 0
            continue
        size = short_size[b & 0x03]
        tag = (b >> 4) & 0x0F
        type_ = (b >> 2) & 0x03
        if i + size > n:
            break
        val = int.from_bytes(data[i:i + size], "little")
        i += size
        yield tag, type_, size, val


# --------------------------------------------------------------------------
# BLE (BlueZ D-Bus)
# --------------------------------------------------------------------------

class BLE:
    """BLE transport over the Feasycom/Nordic UART Service.

    Requires BlueZ + an adapter. Uses the `dbus-next` python package
    (or `dbus`), or falls back to `bleak` if configured.
    """

    service_uuid = BLE_SERVICE_UUID
    rx_uuid = BLE_RX_UUID
    tx_uuid = BLE_TX_UUID

    def __init__(self, address: str, adapter: str = "hci0"):
        self.address = address.upper()
        self.adapter = adapter

    # No hard BLE dependency here: implementation lives in the CLI where
    # the user may pick `dbus-next` or `bleak`. See cli.py:find_ble().
    @staticmethod
    def scan(address: str, timeout: float = 15.0):
        from .ble import scan_for_keyboard
        return scan_for_keyboard(address, timeout)


class Dangle:
    """Dongle routing: dangle_dev_type 0=dev,1=dongle-kb,2=dongle-mouse."""

    DEV = 0
    KB = 1
    MOUSE = 2