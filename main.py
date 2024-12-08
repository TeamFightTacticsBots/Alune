"""
The main class for Alune, responsible for the main loop.
"""

import asyncio
import importlib.metadata
import json
import os
import sys
from urllib.error import HTTPError
from urllib.error import URLError
import urllib.request

from adb_shell.exceptions import TcpTimeoutException
import google_play_scraper
from loguru import logger

from alune import helpers
from alune.adb import ADB
from alune.config import AluneConfig
from alune.helpers import raise_and_exit
from alune.tft.app import TFTApp


async def loop_disconnect_wrapper(adb_instance: ADB, alune_config: AluneConfig):
    """
    Wraps the main loop in a TcpTimeoutException catcher, to catch device disconnects.
    Attempts to re-connect once, then gives up and exits.

    Args:
        adb_instance: The adb instance to run the main loop on.
        alune_config: An instance of the alune config to use.
    """
    tft_app = TFTApp(adb_instance, alune_config)
    try:
        await tft_app.loop()
    except TcpTimeoutException:
        logger.warning("ADB device was disconnected, attempting one reconnect...")
        adb_instance.mark_screen_record_for_close()
        await adb_instance.load()
        adb_instance.create_screen_record_task()
        if not adb_instance.is_connected():
            raise_and_exit("Could not reconnect. Please check your emulator for any errors. Exiting.")
        logger.info("Reconnected to device, continuing main loop.")
        await loop_disconnect_wrapper(adb_instance, alune_config)


async def check_phone_preconditions(adb_instance: ADB):
    """
    Checks the phone for the screen size, pixel density, memory and app (TFT) we need.

    Args:
        adb_instance: The adb instance to check the conditions on.
    """
    logger.debug("Checking screen size")
    size = await adb_instance.get_screen_size()
    if size != "1280x720":
        logger.info(f"Changing screen size from {size} to 1280x720.")
        await adb_instance.set_screen_size()
        size = await adb_instance.get_screen_size()
        if size != "1280x720":
            raise_and_exit("Failed to change the screen size -- this may require manual intervention!")

    logger.debug("Checking screen density")
    density = await adb_instance.get_screen_density()
    if density != "240":
        logger.info(f"Changing dpi from {density} to 240.")
        await adb_instance.set_screen_density()

    logger.debug("Checking memory")
    if await adb_instance.get_memory() < 4_000_000:
        logger.warning("Your device has less than 4GB of memory, lags may occur.")

    logger.debug("Checking if TFT is installed")
    if not await adb_instance.is_tft_installed():
        raise_and_exit("TFT is not installed, please install it to continue. Exiting.")

    logger.debug("Checking TFT app version")
    installed_version = await adb_instance.get_tft_version()
    try:
        play_store_version = google_play_scraper.app(adb_instance.tft_package_name)["version"]
    except URLError as exc:
        logger.opt(exception=exc).debug("URLError while getting Google Play TFT app version.")
        logger.warning(
            "Could not get the newest TFT app version from Google. Assuming the app is on the newest version."
        )
        play_store_version = installed_version

    if helpers.is_version_string_newer(play_store_version, installed_version, ignore_minor_mismatch=True):
        raise_and_exit("A new major version of the TFT app is available. An update is required.")

    logger.debug("Checking if TFT is active")
    if not await adb_instance.is_tft_active():
        logger.debug("TFT is not active, starting it")
        await adb_instance.start_tft_app()


async def check_alune_version():
    """
    Checks the remote version against the local version and prints out a warning if remote is newer.
    """
    local_version = importlib.metadata.version("Alune")
    try:
        with urllib.request.urlopen(
            "https://api.github.com/repos/TeamFightTacticsBots/Alune/releases/latest"
        ) as remote_release:
            remote_version = json.loads(remote_release.read().decode("utf-8"))["tag_name"].replace("v", "")
            if helpers.is_version_string_newer(remote_version, local_version):
                logger.warning(
                    "A newer version is available. "
                    "You can download it at https://github.com/TeamFightTacticsBots/Alune/releases/latest"
                )
                return
    except HTTPError:
        logger.debug("Remote is not reachable, assuming local is newer.")

    logger.info("You are running the latest version.")


async def main():
    """
    Main method, loads ADB connection, checks if the phone is ready to be used and
    finally loops the main app loop in a device disconnect catch wrapper.
    """
    logs_path = helpers.get_application_path("alune-output/logs")
    os.makedirs(logs_path, exist_ok=True)
    logger.add(logs_path + "/{time}.log", level="DEBUG", retention=10)

    config = AluneConfig()
    if config.get_log_level() != "DEBUG":
        # Loguru does not have a setLevel method since it works different from traditional loggers.
        # This removes the default logger and re-adds it at a new level.
        logger.remove(0)
        logger.add(
            sys.stderr,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> - "
                "<level>{message}</level>"
            ),
            level=config.get_log_level(),
        )

    await check_alune_version()

    adb_instance = ADB(config)

    await adb_instance.load()
    if not adb_instance.is_connected():
        logger.error("There is no ADB device ready. Exiting.")
        return

    logger.debug("ADB is connected, checking phone and app details")
    await check_phone_preconditions(adb_instance)

    if config.should_use_screen_record():
        logger.info("The bot will use live screen recording for image searches.")
        adb_instance.create_screen_record_task()
        while await adb_instance.get_screen() is None:
            logger.debug("Waiting for frame data to become available...")
            await asyncio.sleep(0.5)
        logger.debug("Frames are now available.")

    logger.info("Connected to ADB and device is set up correctly, starting main loop.")

    if config.should_surrender():
        logger.info(
            "The bot will surrender early. "
            "This is recommended for passes that get experience per game, like the basic TFT passes."
        )
    else:
        logger.info(
            "The bot will play out games. "
            "This is recommended for passes that get experience for play time, like the event passes."
        )

    try:
        await loop_disconnect_wrapper(adb_instance, config)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Thanks for using Alune, see you next time!")
        adb_instance.mark_screen_record_for_close()
        await asyncio.sleep(1)
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception(e)
        logger.warning(
            "Due to an error, we are exiting Alune in 10 seconds. You can find all logs in alune-output/logs."
        )
        adb_instance.mark_screen_record_for_close()
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
