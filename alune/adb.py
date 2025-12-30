"""
Module for all ADB (Android Debug Bridge) related methods.
"""

import asyncio
import atexit
import os.path
import random
import logging

# Third-party imports
from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.adb_device_async import AdbDeviceTcpAsync
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from adb_shell.exceptions import TcpTimeoutException
import av
from av.error import InvalidDataError  # pylint: disable=no-name-in-module
import cv2
from loguru import logger
import numpy
from numpy import ndarray
import psutil

# Local imports
from alune import helpers
from alune.config import AluneConfig
from alune.images import ClickButton, ImageButton
from alune.screen import BoundingBox, ImageSearchResult


class ADB:  # pylint: disable=too-many-instance-attributes
    """
    Class to hold the connection to an ADB connection via TCP.
    USB connection is possible, but not supported at the moment.
    """

    def __init__(self, config: AluneConfig):
        """
        Initiates base values for the ADB instance.
        """
        self.tft_package_name = "com.riotgames.league.teamfighttactics"
        self._tft_activity_name = "com.riotgames.leagueoflegends.RiotNativeActivity"
        self._random = random.Random()
        self._rsa_signer = None
        self._device = None
        self._config = config
        self._default_port = config.get_adb_port()

        if not config.should_use_screen_record():
            return

        self._video_codec = av.codec.CodecContext.create("h264", "r")
        self._is_screen_recording = False
        self._should_stop_screen_recording = False
        self._latest_frame = None
        self._latest_frame_ts = 0.0
        self._screen_record_task = None

    async def load(self):
        """
        Load the RSA signer and attempt to connect to a device via ADB TCP.
        """
        await self._load_rsa_signer()
        await self._connect_to_device(self._default_port)

    async def _load_rsa_signer(self):
        """
        Loads the RSA signer needed for TCP connections. Generates a local RSA key pair if none exists.
        """
        if self._rsa_signer is not None:
            return

        adb_key_filepath = helpers.get_application_path("alune-output/adb_key")
        if not os.path.isfile(adb_key_filepath):
            keygen(adb_key_filepath)

        with open(adb_key_filepath, encoding="utf-8") as adb_key_file:
            private_key = adb_key_file.read()

        with open(adb_key_filepath + ".pub", encoding="utf-8") as adb_key_file:
            public_key = adb_key_file.read()

        self._rsa_signer = PythonRSASigner(pub=public_key, priv=private_key)

    async def scan_localhost_devices(self) -> int | None:
        """
        Try to connect with a fast abort on every open localhost port.

        Returns:
            The first valid open ADB port or None if there wasn't one.
        """
        logger.info("Scanning local ports for an open ADB connection...")

        connections = [
            conn for conn in psutil.net_connections("tcp4")
            if conn.laddr.port >= 5555 and conn.status == "LISTEN"
        ]

        if len(connections) > 9:
            logger.warning(f"There are {len(connections)} open ports, scanning may take a while.")

        for conn in connections:
            logger.debug(f"Scanning port {conn.laddr.port} for ADB...")
            try:
                adb_device = AdbDeviceTcp("localhost", port=conn.laddr.port, default_transport_timeout_s=0.5)
                if adb_device.connect(rsa_keys=[self._rsa_signer], auth_timeout_s=0.5, read_timeout_s=0.5):
                    adb_device.close()
                    return conn.laddr.port
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.debug(f"Port {conn.laddr.port} threw '{e}'.")

        logger.warning("No local device was found. Make sure ADB is enabled in your emulator's settings.")
        return None

    def mark_screen_record_for_close(self):
        """
        Tells the screen recording to close itself when possible.
        """
        self._should_stop_screen_recording = True

    def create_screen_record_task(self):
        """
        Create the screen recording task. Will not start recording if there's already a recording.
        """
        if self._screen_record_task is not None and not self._screen_record_task.done():
            return

        self._should_stop_screen_recording = False
        # Keep reference to avoid garbage collection.
        self._screen_record_task = asyncio.create_task(self.__screen_record())
        atexit.register(self.mark_screen_record_for_close)

    async def _connect_to_device(self, port: int, retry_with_scan: bool = True):
        """
        Connect to the device via TCP.
        """
        device = AdbDeviceTcpAsync(host="localhost", port=port, default_transport_timeout_s=9)
        logger.info(f"Attempting to connect to ADB session with device localhost:{port}")
        try:
            connection = await device.connect(rsa_keys=[self._rsa_signer], auth_timeout_s=1)
            if connection:
                self._device = device
                return
        except OSError:
            self._device = None

        logger.warning(f"Failed to connect to ADB session with device localhost:{port}.")
        if not retry_with_scan:
            self._device = None
            return

        open_adb_port = await self.scan_localhost_devices()
        if open_adb_port:
            await self._connect_to_device(open_adb_port, retry_with_scan=False)

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
        shell_output = await self._wrap_shell_call("wm size | awk 'END{print $3}'")
        return shell_output.replace("\n", "")

    async def get_screen_density(self) -> str:
        """
        Get the screen density.

        Returns:
             A string containing the pixel density.
        """
        shell_output = await self._wrap_shell_call("wm density | awk 'END{print $3}'")
        return shell_output.replace("\n", "")

    async def set_screen_size(self):
        """
        Set the screen size to 1280x720.
        """
        await self._wrap_shell_call("wm size 1280x720")

    async def set_screen_density(self):
        """
        Set the screen pixel density to 240.
        """
        await self._wrap_shell_call("wm density 240")

    async def get_memory(self) -> int:
        """
        Gets the memory of the device.

        Returns:
            The memory of the device in kB.
        """
        shell_output = await self._wrap_shell_call("grep MemTotal /proc/meminfo | awk '{print $2}'")
        return int(shell_output)

    async def get_screen(self) -> ndarray | None:
        """
        Gets a ndarray which contains the values of the gray-scaled pixels
        currently on the screen. Uses buffered frames from screen recording, available instantly.

        Returns:
            The ndarray containing the gray-scaled pixels. Is None until the first screen record frame is processed.
        """
        if self._config.should_use_screen_record():
            # If we have frames but they stopped updating, restart screen recording.
            if self._latest_frame is not None:
                now = asyncio.get_running_loop().time()
                if (now - self._latest_frame_ts) > 15:
                    logger.warning("Screen record frames are stale (>15s). Restarting screen recording.")
                    self.mark_screen_record_for_close()
                    await asyncio.sleep(0.2)
                    self.create_screen_record_task()
            return self._latest_frame
        return await self._get_screen_capture()

    async def _get_screen_capture(self) -> ndarray | None:
        """
        Gets a ndarray which contains the values of the gray-scaled pixels
        currently on the screen. Uses screencap, so will take some processing time.

        Returns:
            The ndarray containing the gray-scaled pixels.
        """
        image_bytes_str = await self._device.exec_out("screencap -p", decode=False)
        raw_image = numpy.frombuffer(image_bytes_str, dtype=numpy.uint8)
        return cv2.imdecode(raw_image, cv2.IMREAD_GRAYSCALE)

    async def click_image(
        self,
        search_result: ImageSearchResult,
        offset_y: int = 0,
        randomize: bool = True,
    ):
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

    async def click_button(self, button: ClickButton | ImageButton):
        """
        Tap a specific button.

        Args:
            button: The button to click.
        """
        random_coordinate = button.click_box.get_random_point(self._random)
        await self.click(random_coordinate.x, random_coordinate.y)

    async def click_bounding_box(self, bounding_box: BoundingBox):
        """
        Tap a bounding box.

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
        await self._wrap_shell_call(f"input swipe {x} {y} {x} {y} {self._random.randint(60, 120)}")

    async def is_tft_installed(self) -> bool:
        """
        Check if TFT is installed on the device using the package manager (pm).

        Returns:
            Whether the TFT package is in the list of the installed packages.
        """
        shell_output = await self._wrap_shell_call(f"pm list packages | grep {self.tft_package_name}")
        if not shell_output:
            return False

        packages = shell_output.replace("package:", "").split("\n")
        packages.remove("")

        if len(packages) > 1:
            logger.debug(f"More than one TFT package is installed ({packages}). Picking '{packages[0]}'.")

        if not self.tft_package_name == packages[0]:
            logger.debug(
                f"The pre-defined TFT package '{self.tft_package_name}' "
                f"is not the same as the installed one '{packages[0]}'. "
                f"Switching to '{packages[0]}' for compatibility."
            )
            self.tft_package_name = packages[0]

        return True

    async def is_tft_active(self) -> bool:
        """
        Check if TFT is the currently active window.

        Returns:
             Whether TFT is the currently active window.
        """
        shell_output = await self._wrap_shell_call("dumpsys window | grep -E 'mCurrentFocus' | awk '{print $3}'")
        return shell_output.split("/")[0].replace("\n", "") == self.tft_package_name

    async def start_tft_app(self):
        """
        Start TFT using the activity manager (am).
        """
        await self._wrap_shell_call(f"am start -n {self.tft_package_name}/{self._tft_activity_name}")

    async def get_tft_version(self) -> str:
        """
        Get the version of the TFT package.

        Returns:
            The versionName of the tft package.
        """
        return await self._wrap_shell_call(
            f"dumpsys package {self.tft_package_name} | grep versionName | sed s/[[:space:]]*versionName=//g"
        )

    async def go_back(self):
        """
        Send a back key press event to the device.
        """
        await self._wrap_shell_call("input keyevent 4")

    async def _wrap_shell_call(self, shell_command: str, retries: int = 0):
        """
        Wrapper for shell commands to catch timeout exceptions.
        Retries 3 times with incremental backoff.

        Args:
            shell_command: The shell command to call.
            retries: Optional, the amount of attempted retries so far.

        Returns:
            The output of the shell command.
        """
        try:
            return await self._device.exec_out(shell_command)
        except TcpTimeoutException:
            if retries == 3:
                raise
            logger.debug(f"Timed out while calling '{shell_command}', retrying {3 - retries} times.")
            await asyncio.sleep(1 + (1 * retries))
            return await self._wrap_shell_call(shell_command, retries=retries + 1)

    async def __convert_frame_to_cv2(self, frame_bytes: bytes):
        """
        Convert frame bytes to a CV2 compatible gray image.

        Args:
            frame_bytes: Byte output of the screen record session.
        """
        packets = self._video_codec.parse(frame_bytes)
        if not packets:
            return

        try:
            frames = self._video_codec.decode(packets[0])
        except InvalidDataError:
            return
        if not frames:
            return

        self._latest_frame = frames[0].to_ndarray(format="gray8").copy()
        self._latest_frame_ts = asyncio.get_running_loop().time()

    async def __write_frame_data(self):
        """
        Start a streaming shell that outputs screenrecord frame bytes and store it as a cv2 compatible image.
        """
        # output-format h264 > H264 is the only format that outputs to console which we can work with.
        # time-limit 10 > Restarts screen recording every 10 seconds instead of every 180. Fixes compression artifacts.
        # bit-rate 16M > 16_000_000 Mbps, could probably be lowered or made configurable, but works well.
        # - at the end makes screenrecord output to console, if format is h264.
        async for data in self._device.streaming_shell(
            command="screenrecord --time-limit 8 --output-format h264 --bit-rate 16M --size 1280x720 -",
            decode=False
        ):
            if self._should_stop_screen_recording:
                break

            await self.__convert_frame_to_cv2(data)

    async def __screen_record(self):
        """
        Start the screen record session. Restarts itself until an external value stops it.
        """
        if self._is_screen_recording:
            return

        await self._device.exec_out("pkill -2 screenrecord")
        logger.debug("Screen record starting.")

        self._is_screen_recording = True
        while not self._should_stop_screen_recording:
            try:
                await self.__write_frame_data()
            except TcpTimeoutException:
                logger.warning(
                    "Timed out while re-/starting screen record, "
                    "killing screenrecord and retrying in 5 seconds."
                )
                try:
                    await self._device.exec_out("pkill -2 screenrecord")
                except Exception:
                    pass
                await asyncio.sleep(5)

        logger.debug("Screen record stopped.")
        await self._device.exec_out("pkill -2 screenrecord")
        self._is_screen_recording = False