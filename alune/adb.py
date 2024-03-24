import os.path

import cv2
import numpy
from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from numpy import ndarray


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

        size: str = self._device.shell("wm size | awk '{print $3}'").replace("\n", "")
        return size

    def get_memory_in_mb(self) -> int | None:
        if not self._device or not self._device.available:
            return None

        # It's an actual shell, so we can use the usual linux shell commands
        memory_kilobytes = int(self._device.shell("grep MemTotal /proc/meminfo | awk '{print $2}'"))
        return memory_kilobytes // 1000

    def get_screen(self) -> ndarray | None:
        """
        Gets a ndarray which contains the values of the gray-scaled pixels
        currently on the screen.

        Returns:
            The ndarray containing the gray-scaled pixels.
        """
        image_bytes_str = self._device.shell("screencap -p", decode=False)
        raw_image = numpy.frombuffer(image_bytes_str, dtype=numpy.uint8)
        return cv2.imdecode(raw_image, cv2.IMREAD_GRAYSCALE)

    def click(self, x: int, y: int):
        """
        Tap a specific coordinate.

        Args:
            x: The x coordinate where to tap.
            y: The y coordinate where to tap.
        """
        self._device.shell(f"input tap {x} {y}")

    def go_back(self):
        """
        Utility method to fulfill the action which goes back one screen,
        however the current app might interpret that.
        """
        self._device.shell(f"input tap keyevent KEYCODE_BACK")
