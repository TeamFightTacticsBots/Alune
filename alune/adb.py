import os.path
import random

import cv2
import numpy
from adb_shell.adb_device_async import AdbDeviceTcpAsync
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from numpy import ndarray

from alune.screen import ImageSearchResult


class ADB:
    def __init__(self):
        self._tft_package_name = "com.riotgames.league.teamfighttactics"
        self._tft_activity_name = "com.riotgames.leagueoflegends.RiotNativeActivity"
        self._random = random.Random()
        self._loaded = False

    async def load(self):
        if self._loaded:
            raise RuntimeError("This ADB instance has already been loaded.")

        self._loaded = True
        await self._load_rsa_signer()
        await self._connect_to_device()

    async def _load_rsa_signer(self) -> None:
        if not os.path.isfile("adb_key"):
            keygen("adb_key")

        with open("adb_key") as adb_key_file:
            private_key = adb_key_file.read()

        with open("adb_key.pub") as adb_key_file:
            public_key = adb_key_file.read()

        self._rsa_signer = PythonRSASigner(pub=public_key, priv=private_key)

    async def _connect_to_device(self):
        # TODO Make port configurable (GUI or config.yml) or add port discovery
        device = AdbDeviceTcpAsync(host='localhost', port=5555, default_transport_timeout_s=9)
        try:
            connection = await device.connect(rsa_keys=[self._rsa_signer], auth_timeout_s=1)
            if connection:
                self._device = device
                return
        except OSError as e:
            self._device = None

    def is_connected(self) -> bool:
        """
        Get if this adb instance is connected.

        Returns:
             True if a device exists and is available. Otherwise, False.
        """
        return self._device is not None and self._device.available

    async def get_screen_size(self) -> tuple[int, int] | None:
        """
        Get the screen size.

        Returns:
             A tuple containing the width and height.
        """
        shell_output = await self._device.shell("wm size | awk '{print $3}'")
        sizes = shell_output.replace("\n", "").split("x")
        return int(sizes[0]), int(sizes[1])

    async def get_memory(self) -> int | None:
        """
        Gets the memory of the device.

        Returns:
            The memory of the device in kB.
        """
        shell_output = await self._device.shell("grep MemTotal /proc/meminfo | awk '{print $2}'")
        return int(shell_output)

    async def get_screen(self) -> ndarray | None:
        """
        Gets a ndarray which contains the values of the gray-scaled pixels
        currently on the screen.

        Returns:
            The ndarray containing the gray-scaled pixels.
        """
        image_bytes_str = await self._device.shell("screencap -p", decode=False)
        raw_image = numpy.frombuffer(image_bytes_str, dtype=numpy.uint8)
        return cv2.imdecode(raw_image, cv2.IMREAD_GRAYSCALE)

    async def click_image(self, search_result: ImageSearchResult, offset_y: int = 0, randomize: bool = True):
        """
        Tap a specific coordinate.

        Args:
            search_result: The image search result to click.
            offset_y: Amount of pixels to offset Y by, useful if we search for part of buttons
                to avoid having text on screenshots.
            randomize: Whether to randomize the click position in the image. Defaults to True.
        """
        if randomize:
            x = self._random.randint(search_result.x, search_result.x + search_result.width)
            y = self._random.randint(search_result.y, search_result.y + search_result.height)
        else:
            x = search_result.get_middle().x
            y = search_result.get_middle().y

        await self.click(x, y + offset_y)

    async def click(self, x: int, y: int):
        """
        Tap a specific coordinate.

        Args:
            x: The x coordinate where to tap.
            y: The y coordinate where to tap.
        """
        await self._device.shell(f"input tap {x} {y}")

    async def go_back(self):
        """
        Utility method to fulfill the action which goes back one screen,
        however the current app might interpret that.
        """
        await self._device.shell("input tap keyevent KEYCODE_BACK")

    async def is_tft_installed(self) -> bool:
        """
        Check if TFT is installed on the device.

        Returns:
            Whether the TFT package is in the list of the installed packages.
        """
        shell_output = await self._device.shell(f"pm list packages {self._tft_package_name}")
        return shell_output != ''

    async def is_tft_active(self) -> bool:
        """
        Check if TFT is the currently active window.

        Returns:
             Whether TFT is the currently active window.
        """
        shell_output = await self._device.shell(
            "dumpsys window | grep -E 'mCurrentFocus' | awk '{print $3}'"
        )
        return shell_output.split("/")[0].replace("\n", "") == self._tft_package_name

    async def start_tft_app(self):
        await self._device.shell(f"am start -n {self._tft_package_name}/{self._tft_activity_name}")
