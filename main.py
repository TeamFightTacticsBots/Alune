"""
The main class for Alune, responsible for the main loop.
"""

import asyncio
from dataclasses import dataclass
from enum import auto
from enum import StrEnum
import importlib.metadata
import json
import os
from random import Random
import sys
from urllib.error import HTTPError
from urllib.error import URLError
import urllib.request

from adb_shell.exceptions import TcpTimeoutException
import google_play_scraper
from loguru import logger
from numpy import ndarray

from alune import helpers
from alune import screen
from alune.adb import ADB
from alune.config import AluneConfig
from alune.helpers import raise_and_exit
from alune.images import Button
from alune.images import Image
from alune.screen import BoundingBox
from alune.screen import ImageSearchResult


class GameState(StrEnum):
    """
    State the game or app is in.
    """

    LOADING = auto()
    MAIN_MENU = auto()
    CHOOSE_MODE = auto()
    LOBBY = auto()
    QUEUE_MISSED = auto()
    IN_GAME = auto()
    POST_GAME = auto()
    CHOICE_CONFIRM = auto()


@dataclass
class GameStateImageResult:
    """
    Combines a game state with an image search result (both optional)
    """

    game_state: GameState
    image_result: ImageSearchResult | None = None


async def wait_for_accept_button(adb_instance: ADB):
    """
    Utility method to wait for the queue accept button.

    Args:
        adb_instance: An instance of the ADB connection to click in.
    """
    screenshot = await adb_instance.get_screen()
    search_result = screen.get_button_on_screen(screenshot, Button.accept)
    while not search_result:
        await asyncio.sleep(2)
        screenshot = await adb_instance.get_screen()
        search_result = screen.get_button_on_screen(screenshot, Button.accept)


async def queue(adb_instance: ADB):
    """
    Utility method to queue a match.

    Args:
        adb_instance: An instance of the ADB connection to click in.
    """
    try:
        await asyncio.wait_for(wait_for_accept_button(adb_instance), timeout=120)
    except asyncio.TimeoutError:
        logger.warning("Waiting for accept button timed out, re-checking app state")
        return
    await adb_instance.click_button(Button.accept)
    await asyncio.sleep(2)

    logger.debug("Queue accepted")
    screenshot = await adb_instance.get_screen()
    while screen.get_on_screen(screenshot, Image.ACCEPTED):
        await asyncio.sleep(1)
        screenshot = await adb_instance.get_screen()

    await asyncio.sleep(3)

    screenshot = await adb_instance.get_screen()
    if screen.get_button_on_screen(screenshot, Button.accept) or screen.get_button_on_screen(screenshot, Button.play):
        logger.debug("Queue was declined by someone else, staying in queue lock state")
        await queue(adb_instance)


_random = Random()


async def handle_augments(screenshot: ndarray, adb_instance: ADB):
    """
    Checks for augments on the current screen and picks some if possible.

    Args:
        screenshot: The current screen.
        adb_instance: The adb instance to check on.
    """
    is_augment_offered = screen.get_on_screen(screenshot, Image.PICK_AUGMENT)
    if not is_augment_offered:
        return

    logger.debug("Augments offered")
    # Roll each augment with a 50% chance
    augment_rolls = Button.get_augment_rolls()
    # Randomize order in which we roll
    _random.shuffle(augment_rolls)
    for augment in augment_rolls:
        if bool(_random.getrandbits(1)):
            logger.debug(f"Rolling augment offer {Button.get_augment_rolls().index(augment) + 1}")
            await adb_instance.click_button(augment)
        await asyncio.sleep(1)
    await asyncio.sleep(2)

    # Pick a random augment
    augment_idx = _random.randint(0, len(Button.get_augments()) - 1)
    augment = Button.get_augments()[augment_idx]
    logger.debug(f"Selecting augment {augment_idx + 1}")
    await adb_instance.click_button(augment)
    await asyncio.sleep(1)


async def buy_from_shop(adb_instance: ADB, config: AluneConfig):
    """
    Checks the shop for traits and purchases it if found.

    Args:
        adb_instance: The adb instance to check and buy in.
        config: An instance of the alune config to use.
    """
    screenshot = await adb_instance.get_screen()
    for trait in config.get_traits():
        search_result = screen.get_on_screen(
            image=screenshot,
            path=trait,
            bounding_box=BoundingBox(170, 110, 1250, 230),
            precision=0.9,
        )
        if not search_result:
            return

        store_cards = Button.get_store_cards()
        _random.shuffle(store_cards)
        for store_card in store_cards:
            if not store_card.click_box.is_inside(search_result.get_middle()):
                continue
            logger.debug(f"Buying store card {Button.get_store_cards().index(store_card) + 1}")
            await adb_instance.click_button(store_card)
            break

        await asyncio.sleep(0.25)


async def take_game_decision(adb_instance: ADB, config: AluneConfig):
    """
    Called by the game loop to take a decision in the current game.

    Args:
        adb_instance: The adb instance to take the decision in.
        config: An instance of the alune config to use.
    """
    screenshot = await adb_instance.get_screen()
    is_in_carousel = screen.get_on_screen(screenshot, Image.CAROUSEL)
    if is_in_carousel:
        logger.debug("Is on carousel, clicking a random point within bounds")
        # Move to a random point in the carousel area
        await adb_instance.click_bounding_box(BoundingBox(200, 100, 1100, 660))
        await asyncio.sleep(_random.randint(3, 9))
        return

    is_on_other_board = screen.get_button_on_screen(screenshot, Button.return_to_board)
    if is_on_other_board:
        logger.debug("Is on other board, returning to own board")
        await adb_instance.click_button(Button.return_to_board)
        await asyncio.sleep(1)
        return

    await handle_augments(screenshot, adb_instance)

    is_choose_one_hidden = screen.get_button_on_screen(screenshot, Button.choose_one_hidden, precision=0.9)
    if is_choose_one_hidden:
        logger.debug("Choose one is hidden, clicking it to show offers")
        await adb_instance.click_button(Button.choose_one_hidden)
        await asyncio.sleep(2)
        screenshot = await adb_instance.get_screen()

    is_choose_one_active = screen.get_button_on_screen(screenshot, Button.choose_one, precision=0.9)
    if is_choose_one_active:
        logger.debug("Choosing from an item or a choice offer")
        await adb_instance.click_button(Button.choose_one)
        await asyncio.sleep(1)
        return

    can_buy_xp = screen.get_button_on_screen(screenshot, Button.buy_xp)
    if can_buy_xp and _random.randint(1, 4) == 4:
        logger.debug("Buying XP")
        await adb_instance.click_button(Button.buy_xp)
        await asyncio.sleep(1)

    await buy_from_shop(adb_instance, config)


async def loop_disconnect_wrapper(adb_instance: ADB, config: AluneConfig):
    """
    Wraps the main loop in a TcpTimeoutException catcher, to catch device disconnects.
    Attempts to re-connect once, then gives up and exits.

    Args:
        adb_instance: The adb instance to run the main loop on.
        config: An instance of the alune config to use.
    """
    try:
        await loop(adb_instance, config)
    except TcpTimeoutException:
        logger.warning("ADB device was disconnected, attempting one reconnect...")
        await adb_instance.load(config.get_adb_port())
        if not adb_instance.is_connected():
            raise_and_exit("Could not reconnect. Please check your emulator for any errors. Exiting.")
        logger.info("Reconnected to device, continuing main loop.")
        await loop_disconnect_wrapper(adb_instance, config)


async def loop(adb_instance: ADB, config: AluneConfig):
    """
    The main app loop logic.

    Args:
        adb_instance: An instance of the ADB connection to click in.
        config: An instance of the alune config to use.
    """
    while True:
        if not await adb_instance.is_tft_active():
            logger.info("TFT was not in the foreground, setting it as active.")
            await adb_instance.start_tft_app()
            await asyncio.sleep(5)

        screenshot = await adb_instance.get_screen()
        game_state_image_result = await get_game_state(screenshot)

        if not game_state_image_result:
            await asyncio.sleep(2)
            continue

        match game_state_image_result.game_state:
            case GameState.LOADING:
                logger.info("App state is loading...")
                # TODO Check if the log-in prompt is on screen
                await asyncio.sleep(10)
            case GameState.MAIN_MENU:
                logger.info("App state is main menu, clicking 'Play'.")
                await adb_instance.click_button(Button.play)
            case GameState.CHOICE_CONFIRM:
                logger.info("App state is choice confirm, accepting the choice.")
                await adb_instance.click_button(Button.check_choice)
            case GameState.CHOOSE_MODE:
                logger.info("App state is choose mode, selecting normal game.")
                await adb_instance.click_image(game_state_image_result.image_result)
            case GameState.QUEUE_MISSED:
                logger.info("App state is queue missed, clicking it.")
                await adb_instance.click_button(Button.check)
            case GameState.LOBBY:
                logger.info("App state is in lobby, locking bot into queue logic.")
                await adb_instance.click_button(Button.play)
                await queue(adb_instance)
                logger.info("Queue lock released, likely loading into game now.")
            case GameState.IN_GAME:
                logger.info("App state is in game, looping decision making and waiting for the exit button.")
                screenshot = await adb_instance.get_screen()
                search_result = screen.get_button_on_screen(screenshot, Button.exit_now)
                while not search_result:
                    await take_game_decision(adb_instance, config)
                    await asyncio.sleep(10)
                    screenshot = await adb_instance.get_screen()
                    search_result = screen.get_button_on_screen(screenshot, Button.exit_now)
                    game_state = await get_game_state(screenshot)
                    if game_state and game_state.game_state == GameState.POST_GAME:
                        break
                await adb_instance.click_button(Button.exit_now)
                await asyncio.sleep(10)
            case GameState.POST_GAME:
                logger.info("App state is post game, clicking 'Play again'.")
                await adb_instance.click_bounding_box(Button.play.click_box)

        await asyncio.sleep(2)


# pylint: disable-next=too-many-return-statements
async def get_game_state(screenshot: ndarray) -> GameStateImageResult | None:
    """
    Get the current app/game state based off a screenshot.

    Args:
        screenshot: A screenshot that was taken by :class:`alune.adb.ADB`
    """
    if screen.get_button_on_screen(screenshot, Button.check_choice):
        return GameStateImageResult(GameState.CHOICE_CONFIRM)

    if screen.get_on_screen(screenshot, Image.RITO_LOGO):
        return GameStateImageResult(GameState.LOADING)

    if screen.get_on_screen(screenshot, Button.play.image_path) and not screen.get_on_screen(screenshot, Image.BACK):
        return GameStateImageResult(GameState.MAIN_MENU)

    if image_result := screen.get_button_on_screen(screenshot, Button.normal_game):
        return GameStateImageResult(game_state=GameState.CHOOSE_MODE, image_result=image_result)

    if screen.get_button_on_screen(screenshot, Button.check):
        return GameStateImageResult(GameState.QUEUE_MISSED)

    if screen.get_on_screen(screenshot, Image.CLOSE_LOBBY) and screen.get_button_on_screen(screenshot, Button.play):
        return GameStateImageResult(GameState.LOBBY)

    if screen.get_on_screen(screenshot, Image.COMPOSITION) or screen.get_on_screen(screenshot, Image.ITEMS):
        return GameStateImageResult(GameState.IN_GAME)

    if screen.get_on_screen(screenshot, Image.FIRST_PLACE) and screen.get_on_screen(screenshot, Image.BACK):
        return GameStateImageResult(GameState.POST_GAME)

    return None


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

    if helpers.is_version_string_newer(play_store_version, installed_version):
        raise_and_exit("A new version of the TFT app is available. Please update to not be locked in queue.")

    logger.debug("Checking if TFT is active")
    if not await adb_instance.is_tft_active():
        logger.debug("TFT is not active, starting it")
        await adb_instance.start_tft_app()


async def check_version():
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

    await check_version()

    adb_instance = ADB()
    await adb_instance.load(config.get_adb_port())
    if not adb_instance.is_connected():
        logger.error("There is no ADB device ready. Exiting.")
        return

    logger.debug("ADB is connected, checking phone and app details")
    await check_phone_preconditions(adb_instance)
    logger.info("Connected to ADB and device is set up correctly, starting main loop.")

    await loop_disconnect_wrapper(adb_instance, config)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Thanks for using Alune, see you next time!")
