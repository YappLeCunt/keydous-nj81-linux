"""Key-config encoding for the Keydous NJ81 (YC500).

Every matrix position holds a 4-byte config: [type, b1, b2, b3].

  type 0 : normal key / combo
           [0, 0, hidCode, 0]            single key
           [0, mod, hidCode, hidCode2]   combo (mod: 224 ctrl,225 shift,
                                          226 alt, 227 win)
           [0, 0, 0, 0] or [0,0,1,0]     disabled (forbidden)
  type 1 : mouse button (see MOUSE)
  type 3 : system/media function (see FUNCTIONS)
  type 9 : macro [9, macroType, macroIndex, 0]
  type 10: special [10, 1, 0, 0] = fn, [10,1,1,0] = right-fn,
           [10,13,0,0] = fn+lock-screen
  type 11: turbo ("火力")
  type 18: siri
  type 19: DPI control (mouse)

Recovered from the vendor app's `configToChangeArr` and `matrixToConfigs`
(keys with 4-byte values were read back from the firmware and cross-checked
against the default matrix).
"""

# --- special keys used inside combos (byte b1 for type 0) ---
MOD_CTRL = 224
MOD_SHIFT = 225
MOD_ALT = 226
MOD_WIN = 227

# --- disabled ---
DISABLED = [0, 0, 0, 0]

# --- system / media functions (type 3) ---
FUNCTIONS = {
    "Prev track": [3, 0, 182, 0],
    "Next track": [3, 0, 181, 0],
    "Stop": [3, 0, 183, 0],
    "Play/Pause": [3, 0, 205, 0],
    "Player": [3, 0, 131, 1],
    "Turbo (fire)": [11, 0, 0, 0],
    "Mute": [3, 0, 226, 0],
    "Volume down": [3, 0, 234, 0],
    "Volume up": [3, 0, 233, 0],
    "Calculator": [3, 0, 146, 1],
    "Email": [3, 0, 138, 1],
    "My computer": [3, 0, 148, 1],
    "Search": [3, 0, 33, 2],
    "Home": [3, 0, 35, 2],
    "Brightness down": [3, 0, 112, 0],
    "Brightness up": [3, 0, 111, 0],
    "Back": [3, 0, 36, 2],
    "Refresh": [3, 0, 39, 2],
    "Siri": [18, 0, 227, 44],
}

# --- special combos (type 0) ---
COMBOS = {
    "(": [0, 0, MOD_SHIFT, 38],
    ")": [0, 0, MOD_SHIFT, 39],
    "{": [0, MOD_SHIFT, 47, 0],
    "}": [0, MOD_SHIFT, 48, 0],
    "Switch IME": [0, MOD_CTRL, 44, 0],
    "Zoom out": [0, 0, MOD_WIN, 45],
    "Zoom in": [0, 0, MOD_WIN, 46],
    "Lock screen": [0, 0, MOD_WIN, 15],
}

# --- mouse buttons (type 1) ---
MOUSE = {
    "Mouse left": [1, 0, 240, 0],
    "Mouse right": [1, 0, 241, 0],
    "Mouse middle": [1, 0, 242, 0],
    "Mouse forward": [1, 0, 243, 0],
    "Mouse back": [1, 0, 244, 0],
    "Wheel left": [1, 0, 245, 0],
    "Wheel right": [1, 0, 246, 0],
    "Wheel forward": [1, 0, 247, 0],
    "Wheel back": [1, 0, 248, 0],
    "Scroll up": [1, 0, 245, 1],
    "Scroll down": [1, 0, 245, 255],
    "Mouse X up": [1, 0, 246, 251],
    "Mouse X down": [1, 0, 246, 5],
    "Mouse Y up": [1, 0, 247, 251],
    "Mouse Y down": [1, 0, 247, 5],
}

# --- special (type 10) ---
SPECIAL = {
    "Fn": [10, 1, 0, 0],
    "Right Fn": [10, 1, 1, 0],
    "Fn lock screen": [10, 13, 0, 0],
}

# --- native Fn-layer screen specials (type 19, verified on NJ81 0x0513) ---
# The NJ81 Fn layer reuses the vendor's type-19 sub-codes for screen
# functions: Fn+Delete = screen cycle, Fn+PgUp = font color,
# Fn+PgDn = background color. The DPI entries come from the vendor map.
FN_SPECIALS = {
    "Screen cycle": [19, 0, 0, 0],
    "Screen font color": [19, 1, 1, 0],
    "Screen background color": [19, 1, 0, 0],
    "DPI up": [19, 0, 1, 0],
    "DPI down": [19, 0, 2, 0],
    "DPI shift": [19, 0, 4, 0],
    "Volume <-> keyboard brightness": [10, 15, 0, 0],
    "Volume <-> keyboard brightness 2": [10, 13, 0, 0],
    "Volume <-> keyboard brightness 3": [10, 14, 0, 0],
}

# Config types that are firmware-native specials (never plain keys).
# Positions holding them in the Fn layer are locked against remapping.
NATIVE_SPECIAL_TYPES = (3, 8, 9, 10, 11, 13, 14, 18, 19, 20, 21)

MOD_NAMES = {MOD_CTRL: "Ctrl", MOD_SHIFT: "Shift", MOD_ALT: "Alt",
             MOD_WIN: "Win"}


def is_native_special(cfg):
    """True when a 4-byte config is a firmware-native special function."""
    return bool(any(cfg)) and cfg[0] in NATIVE_SPECIAL_TYPES


def decode(cfg, hid_names):
    """Decode a 4-byte config into a human-readable description."""
    cfg = list(cfg)
    t = cfg[0]
    if cfg == DISABLED or cfg == [0, 0, 1, 0]:
        return "Disabled"
    if t == 0:
        parts = []
        if cfg[1] in MOD_NAMES:
            parts.append(MOD_NAMES[cfg[1]])
        for b in (cfg[2], cfg[3]):
            if b:
                parts.append(hid_names.get(str(b), f"0x{b:02x}"))
        return " + ".join(parts) if parts else "Empty"
    for table in (FUNCTIONS, MOUSE, SPECIAL, FN_SPECIALS):
        for name, val in table.items():
            if val == cfg:
                return name
    if t == 13 or t == 14:
        return f"Screen fn {cfg[1]}.{cfg[2]}.{cfg[3]}"
    if t == 19:
        return f"Special 19-{cfg[1]}.{cfg[2]}.{cfg[3]}"
    return f"0x{cfg[0]:02x} {cfg[1]:02x} {cfg[2]:02x} {cfg[3]:02x}"


def key_cfg(hid_code):
    """4-byte config for a single normal key."""
    return [0, 0, hid_code & 0xFF, 0]


def combo_cfg(mod, key1, key2=0):
    return [0, mod, key1 & 0xFF, key2 & 0xFF]