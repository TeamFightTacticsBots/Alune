import os.path

from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner


class ADB:
    def __init__(self):
        self._load_rsa_signer()
        self._connect_to_device()

    def _load_rsa_signer(self) -> None:
        if not os.path.isfile("adb_key"):
            keygen("adb_key")

        with open("adb_key") as adb_key_file:
            private_key = adb_key_file.read()

        with open("adb_key.pub") as adb_key_file:
            public_key = adb_key_file.read()

        self._rsa_signer = PythonRSASigner(pub=public_key, priv=private_key)

    def _connect_to_device(self):
        # TODO Make port configurable (GUI or config.yml) or add port discovery
        device = AdbDeviceTcp(host='127.0.0.1', port=5555, default_transport_timeout_s=9)
        try:
            if device.connect(rsa_keys=[self._rsa_signer], auth_timeout_s=0.1):
                self._device = device
                return
        except OSError:
            self._device = None

    def get_screen_size(self) -> str | None:
        # wm commands:
        # wm size - get size ('Physical size: WIDTHxHEIGHT\n')
        # wm size WIDTHxHEIGHT - set size
        # wm density - get pixel density ('Physical density: DENSITY\n')
        # wm density DENSITY - set pixel density, the smaller the size, the smaller the density should be
        if not self._device or not self._device.available:
            return None

        size: str = self._device.shell("wm size")
        return size.split(" ")[-1].replace("\n", "")
