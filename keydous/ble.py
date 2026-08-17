"""BLE transport for Keydous keyboards (Feasycom / Nordic UART Service).

Implements the same command layer as USB: a 64-byte feature-report
payload is written to the RX characteristic; the keyboard answers on the
TX characteristic (notify).

Backend selection:
  1. `dbus_next` (pure Python, BlueZ D-Bus) - recommended.
  2. `bleak` if dbus_next is unavailable.

Framing note: daemon logs show the OTA/feature stream is sent as raw
reports over the UART pipe; this implementation sends the checksum-applied
64-byte command buffer, chunked to the GATT MTU. If a device requires a
length/checksum prefix on the BLE link only, adjust `frame()`.
"""

import asyncio


class BLEError(Exception):
    pass


def ensure_backend():
    try:
        import dbus_next  # noqa
        return "dbus_next"
    except ImportError:
        pass
    try:
        import bleak  # noqa
        return "bleak"
    except ImportError:
        pass
    raise BLEError("no BLE backend available: install `dbus-next` or `bleak`")


class BLEKeyboard:
    """Synchronous facade over an asyncio backend."""

    def __init__(self, address: str, backend: str = None):
        self.address = address.upper()
        self.backend = backend or ensure_backend()
        self._loop = asyncio.new_event_loop()

    def close(self):
        if not self._loop.is_closed():
            self._loop.close()

    def command(self, cmd, data=b"", scheme=0, pad=64):
        from . import checksum
        buf = bytearray(pad)
        buf[0] = cmd
        for i, b in enumerate(data):
            buf[1 + i] = b
        payload = checksum.apply(buf, scheme)
        return self._loop.run_until_complete(self._run(payload))

    def write(self, payload: bytes) -> None:
        self._loop.run_until_complete(self._run(payload))

    def read(self) -> bytes:
        return getattr(self, "_last_response", b"")

    # -- asyncio ----------------------------------------------------------
    async def _run(self, payload):
        if self.backend == "dbus_next":
            resp = await _dbus_run(self.address, payload)
        else:
            resp = await _bleak_run(self.address, payload)
        self._last_response = resp
        return resp


async def _bleak_run(address, payload):
    from bleak import BleakClient
    from .devices import BLE_RX_UUID, BLE_TX_UUID
    responses = []

    def on_notify(_handle, data):
        responses.append(bytes(data))

    async with BleakClient(address) as client:
        await client.start_notify(BLE_TX_UUID, on_notify)
        mtu = max(client.mtu_size - 3, 20) if client.mtu_size else 20
        for i in range(0, len(payload), mtu):
            await client.write_gatt_char(BLE_RX_UUID, payload[i:i + mtu])
        await asyncio.sleep(0.5)
        await client.stop_notify(BLE_TX_UUID)
    return b"".join(responses)


async def _dbus_run(address, payload):
    """BlueZ D-Bus implementation using dbus_next (pure Python)."""
    from dbus_next import BusType, Message, MessageType
    from .devices import BLE_RX_UUID, BLE_TX_UUID, BLE_SERVICE_UUID

    bus = await _connect_dbus()
    try:
        adapter_path, device_path = await _find_device(bus, address,
                                                       BLE_SERVICE_UUID)
        await _call(bus, device_path, "org.bluez.Device1", "Connect")
        # wait for services resolved
        await asyncio.sleep(1.0)

        # characteristic handles
        rx_handle = await _find_char(bus, device_path, BLE_RX_UUID)
        tx_handle = await _find_char(bus, device_path, BLE_TX_UUID)
        if rx_handle is None or tx_handle is None:
            raise BLEError(f"NUS characteristics not found on {address}")

        responses = []
        started = asyncio.Event()

        def on_prop(iface, changed, invalidated):
            if iface == "org.bluez.GattCharacteristic1":
                val = changed.get("Value")
                if val is not None:
                    responses.append(bytes(val))
            if iface == "org.bluez.GattCharacteristic1" and not started.is_set():
                started.set()

        # subscribe to notify on TX
        await _add_match(bus, on_prop)
        await _call(bus, tx_handle, "org.bluez.GattCharacteristic1",
                    "StartNotify")
        await asyncio.sleep(0.2)

        mtu = 20
        for i in range(0, len(payload), mtu):
            await _call(bus, rx_handle, "org.bluez.GattCharacteristic1",
                        "WriteValue", payload[i:i + mtu], {"type": "command"})
        await asyncio.sleep(0.6)

        try:
            await _call(bus, tx_handle, "org.bluez.GattCharacteristic1",
                        "StopNotify")
        except Exception:
            pass
        return b"".join(responses)
    finally:
        bus.disconnect()


async def _connect_dbus():
    from dbus_next import BusType, Message, MessageType
    from dbus_next.aio import MessageBus
    return await MessageBus(bus_type=BusType.SYSTEM).connect()


async def _call(bus, path, iface, member, *body, sig=None):
    from dbus_next import Message, MessageType
    from dbus_next.signature import Variant
    sig = sig or _guess_sig(body)
    msg = Message(destination="org.bluez", path=path, interface=iface,
                  member=member, signature=sig, body=list(body))
    reply = await bus.call(msg)
    if reply.message_type == MessageType.ERROR:
        raise BLEError(f"{member}: {reply.error_name} {reply.body}")
    return reply.body


def _guess_sig(body):
    from dbus_next.signature import Variant
    if not body:
        return ""
    sigs = []
    for b in body:
        if isinstance(b, bytes):
            sigs.append("ay")
        elif isinstance(b, dict):
            sigs.append("a{sv}")
        elif isinstance(b, str):
            sigs.append("s")
        elif isinstance(b, bool):
            sigs.append("b")
        elif isinstance(b, int):
            sigs.append("i")
        else:
            sigs.append("v")
    return "".join(sigs)


async def _find_device(bus, address, service_uuid):
    from dbus_next import Message, MessageType
    reply = await bus.call(Message(
        destination="org.bluez", path="/",
        interface="org.freedesktop.DBus.ObjectManager",
        member="GetManagedObjects", signature="", body=[]))
    objects = reply.body[0]
    device_path = None
    adapter_path = None
    for path, ifaces in objects.items():
        if "org.bluez.Adapter1" in ifaces and adapter_path is None:
            adapter_path = path
        if "org.bluez.Device1" in ifaces:
            props = ifaces["org.bluez.Device1"]
            if str(props.get("Address", "")).upper() == address:
                device_path = path
                adapter_path = props.get("Adapter", adapter_path)
    if device_path is None:
        raise BLEError(f"device {address} not found (is it paired/scanned?)")
    return adapter_path, device_path


async def _find_char(bus, device_path, uuid):
    from dbus_next import Message, MessageType
    reply = await bus.call(Message(
        destination="org.bluez", path="/",
        interface="org.freedesktop.DBus.ObjectManager",
        member="GetManagedObjects", signature="", body=[]))
    objects = reply.body[0]
    wanted = uuid.lower()
    for path, ifaces in objects.items():
        if "org.bluez.GattCharacteristic1" not in ifaces:
            continue
        if str(ifaces["org.bluez.GattCharacteristic1"].get("UUID",
                                                          "")).lower() == wanted:
            return path
    return None


async def _add_match(bus, callback):
    from dbus_next import Message, MessageType
    await bus.call(Message(
        destination="org.freedesktop.DBus",
        path="/org/freedesktop/DBus",
        interface="org.freedesktop.DBus",
        member="AddMatch",
        signature="s",
        body=["interface='org.bluez.GattCharacteristic1'"]))
    bus.add_message_handler(lambda m: (
        m.message_type == MessageType.SIGNAL
        and m.interface == "org.bluez.GattCharacteristic1"
        and callback(m.interface, m.body[0], m.body[1])
        if len(m.body) >= 2 else None))