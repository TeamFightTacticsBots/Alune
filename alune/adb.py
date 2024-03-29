import os.path
import random

import cv2
import numpy
from adb_shell.adb_device_async import AdbDeviceTcpAsync
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from numpy import ndarray

from alune.screen import ImageSearchResult, BoundingBox


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
        except OSError:
            self._device = None

    def is_connected(self) -> bool:
        """
        Get if this adb instance is connected.

        Returns:
             True if a device exists and is available. Otherwise, False.
        """
        return self._device is not None and self._device.available

    async def get_screen_size(self) -> str:
        """
        Get the screen size.

        Returns:
             A string containing 'WIDTHxHEIGHT'.
        """
        shell_output = await self._device.shell("wm size | awk '{print $3}'")
        return shell_output.replace("\n", "")

    async def get_screen_density(self) -> str:
        """
        Get the screen density.

        Returns:
             A string containing the pixel density.
        """
        shell_output = await self._device.shell("wm density | awk '{print $3}'")
        return shell_output.replace("\n", "")

    async def set_screen_size(self):
        """
        Set the screen size to 1280x720.
        """
        await self._device.shell("wm size 1280x720")

    async def set_screen_density(self):
        """
        Set the screen pixel density to 240.
        """
        await self._device.shell("wm density 240")

    async def get_memory(self) -> int:
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

    async def click_bounding_box(self, bounding_box: BoundingBox):
        """
        Tap a specific coordinate.

        Args:
            bounding_box: The bounding box in which to click.
        """
        random_coordinate = bounding_box.get_random_point(self._random)
        await self.click(random_coordinate.x, random_coordinate.y)

    async def click(self, x: int, y: int):
        """
        Tap a specific coordinate.

        Args:
            x: The x coordinate where to tap.
            y: The y coordinate where to tap.
        """
        # input tap x y comes with the downtime of tapping too fast for the game sometimes,
        # so we swipe on the same coordinate to simulate a longer press with a random duration.
        await self._device.shell(f"input swipe {x} {y} {x} {y} {self._random.randint(40, 120)}")

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
