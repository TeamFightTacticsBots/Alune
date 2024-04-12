import asyncio
import sys
from enum import StrEnum, auto
from random import Random

from adb_shell.exceptions import TcpTimeoutException
from loguru import logger
from numpy import ndarray

from alune import screen
from alune.adb import ADB
from alune.images import Button, Image, Trait
from alune.screen import BoundingBox


class GameState(StrEnum):
    loading = auto()
    main_menu = auto()
    choose_mode = auto()
    lobby = auto()
    queue_missed = auto()
    in_game = auto()
    post_game = auto()


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
    logger.info("Queue started, waiting for accept button.")
    try:
        await asyncio.wait_for(wait_for_accept_button(adb_instance), timeout=120)
    except asyncio.TimeoutError:
        logger.warning("Waiting for accept button timed out, re-checking app state")
        return
    await adb_instance.click_button(Button.accept)
    await asyncio.sleep(2)

    logger.debug("Queue accepted")
    screenshot = await adb_instance.get_screen()
    while screen.get_on_screen(screenshot, Image.accepted):
        await asyncio.sleep(1)
        screenshot = await adb_instance.get_screen()

    await asyncio.sleep(3)

    screenshot = await adb_instance.get_screen()
    search_result = screen.get_button_on_screen(screenshot, Button.check)
    if search_result:
        logger.debug("Queue was missed, accepting and re-queueing")
        await adb_instance.click_button(Button.check)
        await asyncio.sleep(2)
        await adb_instance.click_button(Button.play)
        await queue(adb_instance)

    if screen.get_button_on_screen(screenshot, Button.play):
        logger.debug("Queue was declined by someone else, staying in queue lock state")
        await queue(adb_instance)


_random = Random()


async def take_game_decision(adb_instance: ADB):
    screenshot = await adb_instance.get_screen()
    is_in_carousel = screen.get_on_screen(screenshot, Image.carousel)
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

    is_augment_offered = screen.get_on_screen(screenshot, Image.pick_augment)
    if is_augment_offered:
        logger.debug("Augments offered")
        # Roll each augment with a 50% chance
        augment_rolls = Button.get_augment_rolls()
        # Randomize order in which we roll
        _random.shuffle(augment_rolls)
        for i in range(len(augment_rolls)):
            if bool(_random.getrandbits(1)):
                logger.debug(f"Rolling augment offer {i}")
                await adb_instance.click_button(augment_rolls[i])
            await asyncio.sleep(1)
        await asyncio.sleep(2)

        # Pick a random augment
        augment_idx = _random.randint(0, len(Button.get_augments()) - 1)
        augment = Button.get_augments()[augment_idx]
        logger.debug(f"Selecting augment {augment_idx + 1}")
        await adb_instance.click_button(augment)
        await asyncio.sleep(1)
        return

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

    screenshot = await adb_instance.get_screen()
    search_result = screen.get_on_screen(
        image=screenshot,
        # TODO Make trait configurable
        path=Trait.heavenly,
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


async def loop_disconnect_wrapper(adb_instance: ADB):
    try:
        await loop(adb_instance)
    except TcpTimeoutException:
        logger.warning("ADB device was disconnected, attempting one reconnect...")
        await adb_instance.load()
        if not adb_instance.is_connected():
            logger.error("Could not reconnect. Please check your emulator for any errors. Exiting.")
            sys.exit(1)
        logger.info("Reconnected to device, continuing main loop.")
        await loop_disconnect_wrapper(adb_instance)


async def loop(adb_instance: ADB):
    """
    The main app loop logic.

    Args:
        adb_instance: An instance of the ADB connection to click in.
    """
    while True:
        if not await adb_instance.is_tft_active():
            logger.info("TFT was not in the foreground, setting it as active.")
            await adb_instance.start_tft_app()
            await asyncio.sleep(5)

        screenshot = await adb_instance.get_screen()
        game_state = await get_game_state(screenshot)

        match game_state:
            case GameState.loading:
                logger.info("App state is loading...")
                # TODO Check if the log-in prompt is on screen
                await asyncio.sleep(10)
            case GameState.main_menu:
                logger.info("App state is main menu, clicking 'Play'.")
                await adb_instance.click_button(Button.play)
            case GameState.choose_mode:
                logger.info("App state is choose mode, selecting normal game.")
                await adb_instance.click_button(Button.normal_game)
            case GameState.queue_missed:
                logger.info("App state is queue missed, clicking it.")
                await adb_instance.click_button(Button.check)
            case GameState.lobby:
                logger.info("App state is in lobby, locking bot into queue logic.")
                await adb_instance.click_button(Button.play)
                await queue(adb_instance)
                logger.info("Queue lock released, likely loading into game now.")
            case GameState.in_game:
                logger.info("App state is in game, looping decision making and waiting for the exit button.")
                screenshot = await adb_instance.get_screen()
                search_result = screen.get_button_on_screen(screenshot, Button.exit_now)
                while not search_result:
                    await take_game_decision(adb_instance)
                    await asyncio.sleep(10)
                    screenshot = await adb_instance.get_screen()
                    search_result = screen.get_button_on_screen(screenshot, Button.exit_now)
                    game_state = await get_game_state(screenshot)
                    if game_state == GameState.post_game:
                        break
                await adb_instance.click_button(Button.exit_now)
                await asyncio.sleep(10)
            case GameState.post_game:
                logger.info("App state is post game, clicking 'Play again'.")
                await adb_instance.click_bounding_box(Button.play.click_box)

        await asyncio.sleep(2)


async def get_game_state(screenshot: ndarray) -> GameState | None:
    """
    Get the current app/game state based off a screenshot.

    Args:
        screenshot: A screenshot that was taken by :class:`alune.adb.ADB`
    """
    if screen.get_on_screen(screenshot, Image.rito_logo):
        return GameState.loading

    if screen.get_on_screen(screenshot, Button.play.image_path) and not screen.get_on_screen(screenshot, Image.back):
        return GameState.main_menu

    if screen.get_button_on_screen(screenshot, Button.normal_game):
        return GameState.choose_mode

    if screen.get_button_on_screen(screenshot, Button.check):
        return GameState.queue_missed

    if screen.get_on_screen(screenshot, Image.close_lobby) and screen.get_button_on_screen(screenshot, Button.play):
        return GameState.lobby

    if screen.get_on_screen(screenshot, Image.composition) or screen.get_on_screen(screenshot, Image.items):
        return GameState.in_game

    if screen.get_on_screen(screenshot, Image.first_place) and screen.get_on_screen(screenshot, Image.back):
        return GameState.post_game


async def check_phone_preconditions(adb_instance: ADB):
    logger.debug("Checking phone preconditions")

    size = await adb_instance.get_screen_size()
    if size != "1280x720":
        logger.info(f"Changing screen size from {size} to 1280x720.")
        await adb_instance.set_screen_size()

    density = await adb_instance.get_screen_density()
    if density != "240":
        logger.info(f"Changing dpi from {density} to 240.")
        await adb_instance.set_screen_density()

    if await adb_instance.get_memory() < 4_000_000:
        logger.warning("Your device has less than 4GB of memory, lags may occur.")

    if not await adb_instance.is_tft_active():
        if not await adb_instance.is_tft_installed():
            # TODO Avoid Google Play (add README warning for Google Play interruptions) and install from
            #  https://www.apkmirror.com/apk/riot-games-inc/teamfight-tactics-league-of-legends-strategy-game/
            #  Note, this also needs a functionality to update check (Does the app tell us? Parse from site?)
            logger.error("TFT is not installed, please install it to continue. Exiting.")
            sys.exit(1)

        logger.debug("TFT is not active, starting it")
        await adb_instance.start_tft_app()


async def main():
    adb_instance = ADB()
    await adb_instance.load()
    if not adb_instance.is_connected():
        logger.error("There is no ADB device ready. Exiting.")
        return

    await check_phone_preconditions(adb_instance)
    logger.info("Connected to ADB and device is set up correctly, starting main loop.")

    await loop_disconnect_wrapper(adb_instance)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Thanks for using Alune, see you next time!")
