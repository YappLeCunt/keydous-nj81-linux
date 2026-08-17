"""Music and screen follow streams for the Keydous NJ81 (Linux, stdlib only).

Music follow:
  - captures the PipeWire monitor (system audio) via ``pw-record``
  - runs a pure-Python radix-2 FFT over 512-sample windows
  - derives the 32 band levels the firmware expects for LED modes 20/22
  - streams ``SET_AUDIO (0x0D)`` reports at ~30 fps

Screen follow:
  - captures the X11 root window via a minimal stdlib X client
    (XGetImage of a small center region - no external tools)
  - averages the region into one RGBA color
  - streams ``SET_WINDOS (0x0E)`` reports at ~16 fps (LED mode 21)

Nothing is installed or modified on the host; audio is only read from the
monitor node and the screen is only sampled.
"""

import json
import math
import os
import re
import socket
import struct
import subprocess
import threading

from . import checksum


class FollowError(Exception):
    pass


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _monitor_node():
    """Find the PipeWire monitor for system-audio capture.

    Returns a node id when a monitor node exists, otherwise the
    ``<default-sink>.monitor`` name - PipeWire creates the monitor on
    demand when targeted by name.
    """
    try:
        out = subprocess.run(["pw-dump"], capture_output=True, text=True,
                             timeout=10).stdout
        nodes = json.loads(out)
        sink_name = None
        for node in nodes:
            props = node.get("info", {}).get("props", {})
            cls = props.get("media.class")
            name = str(props.get("node.name", ""))
            if cls == "Audio/Source" and name.endswith(".monitor"):
                return node.get("id")
            if cls == "Audio/Sink" and sink_name is None:
                sink_name = name
        if sink_name:
            return f"{sink_name}.monitor"
    except Exception:
        pass
    try:
        out = subprocess.run(["wpctl", "status"], capture_output=True,
                             text=True, timeout=10).stdout
    except Exception:
        return None
    sink_name = None
    sources = []
    section = None
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("Sinks:"):
            section = "sinks"
        elif stripped.startswith("Sources:"):
            section = "sources"
        elif stripped.startswith(("Streams:", "Sink endpoints:",
                                  "Source endpoints:", "Devices:")):
            section = None
        m = re.match(r"(\*?\s*)(\d+)\.\s+(.*)", stripped)
        if not m:
            continue
        if section == "sinks" and m.group(1).strip() == "*":
            sink_name = m.group(3)
        elif section == "sources":
            sources.append((int(m.group(2)), m.group(3)))
    if sink_name:
        for sid, name in sources:
            if name == sink_name:
                return sid
    if sources:
        return sources[0][0]
    return None


def _fft(re_, im):
    """In-place radix-2 Cooley-Tukey FFT. ``len(re_)`` must be a power of 2."""
    n = len(re_)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            re_[i], re_[j] = re_[j], re_[i]
            im[i], im[j] = im[j], im[i]
    length = 2
    while length <= n:
        angle = -2 * math.pi / length
        wlen_r, wlen_i = math.cos(angle), math.sin(angle)
        half = length >> 1
        for i in range(0, n, length):
            wr, wi = 1.0, 0.0
            for k in range(half):
                j = i + k
                u_r, u_i = re_[j], im[j]
                v_r = re_[j + half] * wr - im[j + half] * wi
                v_i = re_[j + half] * wi + im[j + half] * wr
                re_[j] = u_r + v_r
                im[j] = u_i + v_i
                re_[j + half] = u_r - v_r
                im[j + half] = u_i - v_i
                wr, wi = (wr * wlen_r - wi * wlen_i,
                          wr * wlen_i + wi * wlen_r)
        length <<= 1


_WINDOW = 512


def _music_bands(frame):
    """32 band levels (0..6) for one 512-sample float32 frame.

    Mirrors the vendor pipeline: Hann-windowed FFT, byte-scaled magnitude,
    normalize 100 bins against the 20..40 quiet range, clamp to the
    keyboard count (6), emit bins 27..59.
    """
    n = _WINDOW
    for i in range(n):
        frame[i] *= 0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1))
    re_ = list(frame)
    im = [0.0] * n
    _fft(re_, im)
    mags = [math.hypot(re_[b], im[b]) for b in range(100)]
    peak = max(mags)
    if peak <= 0:
        return bytes(32)
    levels = [int(255 * m / peak) for m in mags]
    quiet = min(levels[20:40])
    normalized = [v - quiet for v in levels]
    peak2 = max(normalized)
    if peak2 <= 0:
        return bytes(32)
    scale = 6.0 / peak2
    out = bytearray(32)
    for i, v in enumerate(normalized[27:59]):
        x = int(v * scale)
        out[i] = 0 if x < 0 else 6 if x > 6 else x
    return bytes(out)


# --------------------------------------------------------------------------
# screen sampling via libX11 (ctypes - no new dependencies)
# --------------------------------------------------------------------------

class X11Screen:
    """Average color of the X11 root window via libX11 (ctypes)."""

    _image_fields = [
        ("width", "i"), ("height", "i"), ("xoffset", "i"), ("format", "i"),
        ("data", "P"), ("byte_order", "i"), ("bitmap_unit", "i"),
        ("bitmap_bit_order", "i"), ("bitmap_pad", "i"), ("depth", "i"),
        ("bytes_per_line", "i"), ("bits_per_pixel", "i"),
        ("red_mask", "L"), ("green_mask", "L"), ("blue_mask", "L"),
    ]

    def __init__(self, display=None):
        import ctypes

        self._ctypes = ctypes
        self._x11 = ctypes.CDLL("libX11.so.6")
        x = self._x11
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x.XDefaultScreen.argtypes = [ctypes.c_void_p]
        x.XDefaultScreen.restype = ctypes.c_int
        x.XDisplayWidth.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XDisplayWidth.restype = ctypes.c_int
        x.XDisplayHeight.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XDisplayHeight.restype = ctypes.c_int
        x.XDefaultDepth.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XDefaultDepth.restype = ctypes.c_int
        x.XRootWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        x.XRootWindow.restype = ctypes.c_ulong
        x.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                                ctypes.c_ulong, ctypes.c_int]
        x.XGetImage.restype = ctypes.c_void_p
        x.XDestroyImage.argtypes = [ctypes.c_void_p]
        x.XDestroyImage.restype = ctypes.c_int

        display = display or os.environ.get("DISPLAY", ":0")
        self._display = x.XOpenDisplay(display.encode())
        if not self._display:
            raise FollowError(f"cannot open X display {display}")
        self._screen = x.XDefaultScreen(self._display)
        self.width = x.XDisplayWidth(self._display, self._screen)
        self.height = x.XDisplayHeight(self._display, self._screen)
        self.depth = x.XDefaultDepth(self._display, self._screen)
        self._root = x.XRootWindow(self._display, self._screen)

    def close(self):
        if getattr(self, "_display", None):
            self._x11.XCloseDisplay(self._display)
            self._display = None

    def average(self, cx, cy, w=16, h=16):
        """Average RGBA color of a small region around the screen center."""
        import ctypes

        x = max(0, min(cx - w // 2, self.width - w))
        y = max(0, min(cy - h // 2, self.height - h))
        img = self._x11.XGetImage(self._display, self._root, x, y, w, h,
                                  0xFFFFFFFF, 2)
        if not img:
            raise FollowError("XGetImage failed")
        try:
            kinds = {"i": ctypes.c_int, "P": ctypes.c_void_p,
                     "L": ctypes.c_ulong}
            fields = [(name, kinds[kind]) for name, kind in self._image_fields]
            image = ctypes.cast(img, ctypes.POINTER(
                type("XImage", (ctypes.Structure,), {"_fields_": fields}))).contents
            bpp = image.bits_per_pixel
            count = w * h
            if bpp >= 24:
                r = g = b = 0
                for i in range(count):
                    px = ctypes.c_uint32.from_address(
                        image.data + i * 4).value
                    r += (px >> 16) & 0xFF
                    g += (px >> 8) & 0xFF
                    b += px & 0xFF
                return (r // count, g // count, b // count, 255)
            if bpp == 16:
                r = g = b = 0
                for i in range(count):
                    px = ctypes.c_uint16.from_address(
                        image.data + i * 2).value
                    r += (px >> 11) & 0x1F
                    g += (px >> 5) & 0x3F
                    b += px & 0x1F
                return (r * 255 // (count * 31),
                        g * 255 // (count * 63),
                        b * 255 // (count * 31), 255)
            raise FollowError(f"unsupported bits per pixel {bpp}")
        finally:
            self._x11.XDestroyImage(img)


# --------------------------------------------------------------------------
# follow session
# --------------------------------------------------------------------------

class FollowSession:
    """Background streams; ``send`` is a callable that writes a 64-byte
    feature payload (the GUI supplies a lock-protected device writer)."""

    def __init__(self, send):
        self._send = send
        self._thread = None
        self._stop = threading.Event()
        self._proc = None
        self.kind = None
        self.error = None
        self.last_bands = [0] * 32
        self._lock = threading.Lock()

    @property
    def running(self):
        return self._thread is not None and self._thread.is_alive()

    def status(self):
        with self._lock:
            return {"running": self.running, "kind": self.kind,
                    "error": self.error, "bands": list(self.last_bands)}

    def start(self, kind):
        if self.running:
            self.stop()
        if kind not in ("music", "screen"):
            raise FollowError(f"unknown follow kind {kind}")
        self.kind = kind
        self.error = None
        self._stop.clear()
        target = self._music_loop if kind == "music" else self._screen_loop
        self._thread = threading.Thread(target=target, daemon=True)
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=4)
            self._thread = None
        self.kind = None

    def _send_payload(self, cmd, data, offset):
        buf = bytearray(64)
        buf[0] = cmd
        buf[offset:offset + len(data)] = data
        self._send(checksum.apply(buf, checksum.BIT7))

    def _music_loop(self):
        proc = None
        try:
            node = _monitor_node()
            if node is None:
                raise FollowError("no PipeWire monitor source found")
            proc = subprocess.Popen(
                ["pw-record", "--target", str(node), "--format", "f32",
                 "--rate", "44100", "--channels", "1", "--latency", "20ms",
                 "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self._proc = proc
            frame_size = _WINDOW * 4
            buffer = b""
            sent = 0
            while not self._stop.is_set():
                chunk = proc.stdout.read(8192)
                if not chunk:
                    raise FollowError("pw-record stopped unexpectedly")
                buffer += chunk
                while len(buffer) >= frame_size and not self._stop.is_set():
                    frame = struct.unpack(f"<{_WINDOW}f",
                                          buffer[:frame_size])
                    buffer = buffer[frame_size:]
                    bands = _music_bands(list(frame))
                    with self._lock:
                        self.last_bands = list(bands)
                    self._send_payload(0x0D, bands, 8)
                    sent += 1
                    # ~30 fps: every third 512-sample window
                    if sent % 3 == 0:
                        self._stop.wait(0.005)
        except Exception as exc:
            self.error = str(exc)
        finally:
            if proc is not None:
                try:
                    proc.terminate()
                except Exception:
                    pass
            self._proc = None

    def _screen_loop(self):
        cam = None
        try:
            cam = X11Screen()
            cx, cy = cam.width // 2, cam.height // 2
            while not self._stop.is_set():
                rgba = cam.average(cx, cy, 16, 16)
                self._send_payload(0x0E, bytes(rgba), 1)
                self._stop.wait(0.06)  # ~16 fps
        except Exception as exc:
            self.error = str(exc)
        finally:
            if cam is not None:
                cam.close()
