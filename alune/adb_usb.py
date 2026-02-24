import asyncio
import threading
from typing import Any, AsyncIterator, Optional

from adb_shell.adb_device import AdbDeviceUsb

class AdbDeviceUsbAsyncShim:
    """Async wrapper around adb_shell.adb_device.AdbDeviceUsb"""

    def __init__(self, serial: Optional[str] = None, port_path: Any = None, default_transport_timeout_s: float | None = 10):
        self._dev = AdbDeviceUsb(serial=serial, port_path=port_path, default_transport_timeout_s=default_transport_timeout_s)

    @property
    def available(self) -> bool:
        return self._dev.available

    async def connect(
        self,
        rsa_keys=None,
        transport_timeout_s=None,
        auth_timeout_s: float = 10.0,
        read_timeout_s: float = 10.0,
        auth_callback=None,
    ) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._dev.connect(
                rsa_keys=rsa_keys,
                transport_timeout_s=transport_timeout_s,
                auth_timeout_s=auth_timeout_s,
                read_timeout_s=read_timeout_s,
                auth_callback=auth_callback,
            ),
        )

    async def close(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._dev.close)

    async def exec_out(self, command: str, decode: bool = True, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self._dev.exec_out(command, decode=decode, **kwargs))

    async def streaming_shell(
        self,
        command: str,
        transport_timeout_s=None,
        read_timeout_s: float = 10.0,
        decode: bool = True,
    ) -> AsyncIterator[bytes | str]:
        """
        Bridge the sync generator AdbDeviceUsb.streaming_shell() into an async generator.
        """
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        def worker():
            try:
                for item in self._dev.streaming_shell(
                    command=command,
                    transport_timeout_s=transport_timeout_s,
                    read_timeout_s=read_timeout_s,
                    decode=decode,
                ):
                    asyncio.run_coroutine_threadsafe(q.put(item), loop).result()
                asyncio.run_coroutine_threadsafe(q.put(sentinel), loop).result()
            except Exception as e:  # propagate exceptions to async side
                asyncio.run_coroutine_threadsafe(q.put(e), loop).result()
                asyncio.run_coroutine_threadsafe(q.put(sentinel), loop).result()

        threading.Thread(target=worker, daemon=True).start()

        while True:
            item = await q.get()
            if item is sentinel:
                break
            if isinstance(item, Exception):
                raise item
            yield item
