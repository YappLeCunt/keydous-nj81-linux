"""Feature-report checksum schemes used by the Keydous firmware.

Recovered from the Electron app JS: the daemon (`iot_driver`) accepts a
`check_sum_type` per send:

  CheckSumType { BIT7: 0, BIT8: 1, NONE: 2 }

* BIT7: byte[7] = 0xFF - ((byte[0] + byte[1] + ... + byte[6]) & 0xFF)
        (JS computes the same value as `255 - (sum & 255)` for the
         8-byte-header commands it builds itself).
* BIT8: byte[8] = 0xFF - ((byte[0] + ... + byte[7]) & 0xFF)
        (one byte later; used for 9-byte-header commands).
* NONE: report sent as-is.

Most query commands (fw version, battery, profile, report rate,
keyboard options) are sent with BIT7.
"""

BIT7 = 0
BIT8 = 1
NONE = 2

NAMES = {BIT7: "BIT7", BIT8: "BIT8", NONE: "NONE"}


def apply(buf: bytearray, scheme: int) -> bytearray:
    """Return `buf` with the checksum byte filled in for the given scheme.

    The buffer is expected to be the 64-byte feature-report payload
    (byte 0 = command, data follows)."""
    buf = bytearray(buf)
    if scheme == NONE:
        return buf
    if scheme == BIT7:
        assert len(buf) >= 8, "BIT7 checksum needs >= 8 bytes"
        buf[7] = (0xFF - (sum(buf[0:7]) & 0xFF)) & 0xFF
    elif scheme == BIT8:
        assert len(buf) >= 9, "BIT8 checksum needs >= 9 bytes"
        buf[8] = (0xFF - (sum(buf[0:8]) & 0xFF)) & 0xFF
    else:
        raise ValueError(f"unknown checksum scheme {scheme}")
    return buf