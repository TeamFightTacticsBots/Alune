import asyncio
import sys
import time
from contextlib import contextmanager
from enum import StrEnum, auto
from random import Random

from numpy import ndarray

from alune import screen
from alune.adb import ADB
from alune.screen import BoundingBox


class GameState(StrEnum):
    loading = auto()
    main_menu = auto()
    choose_mode = auto()
    lobby = auto()
    queue_missed = auto()
    in_game = auto()
    post_game = auto()


class Image(StrEnum):
    rito_logo = auto()
    play = auto()
    normal_game = auto()
    close_lobby = auto()
    accept = auto()
    accepted = auto()
    check = auto()
    composition = auto()
    items = auto()
    exit_now = auto()
    first_place = auto()
    back = auto()
    settings = auto()


@contextmanager
def timeout(seconds: int):
    """
    Context manager that times a function or with-context out after a given time.

    Args:
        seconds: number of seconds before this raises a TimeoutError

    Raises:
        TimeoutError
    """
    start_time = time.time()
    yield
    elapsed_seconds = time.time() - start_time
    if elapsed_seconds > seconds:
        raise TimeoutError()


async def click_play(adb_instance: ADB):
    """
    Utility method to click within the play button boundary box.

    Args:
        adb_instance: An instance of the ADB connection to click in.
    """
    await adb_instance.click_bounding_box(BoundingBox(950, 600, 1200, 650))


@timeout(120)
async def wait_for_accept_button(adb_instance: ADB):
    """
    Utility method to wait for the queue accept button.

    Args:
        adb_instance: An instance of the ADB connection to click in.
    """
    screenshot = await adb_instance.get_screen()
    search_result = screen.get_on_screen(screenshot, Image.accept)
    while not search_result:
        await asyncio.sleep(2)
        screenshot = await adb_instance.get_screen()
        search_result = screen.get_on_screen(screenshot, Image.accept)


async def queue(adb_instance: ADB):
    """
    Utility method to queue a match.

    Args:
        adb_instance: An instance of the ADB connection to click in.
    """
    print("Queue started, waiting for accept button")
    try:
        await wait_for_accept_button(adb_instance)
    except TimeoutError:
        print("Waiting for accept button took longer than 120 seconds, checking state again")
        return
    await adb_instance.click_bounding_box(BoundingBox(520, 515, 760, 550))
    await asyncio.sleep(2)

    print("Match accepted")
    screenshot = await adb_instance.get_screen()
    while screen.get_on_screen(screenshot, Image.accepted):
        await asyncio.sleep(1)
        screenshot = await adb_instance.get_screen()

    await asyncio.sleep(3)

    screenshot = await adb_instance.get_screen()
    search_result = screen.get_on_screen(screenshot, Image.check)
    if search_result:
        print("We missed the queue")
        await adb_instance.click_image(search_result)
        await asyncio.sleep(2)
        await click_play(adb_instance)
        await queue(adb_instance)

    if screen.get_on_screen(screenshot, Image.play):
        print("Queue got declined by someone")
        await queue(adb_instance)


_random = Random()


async def temporary_game_loop(adb_instance: ADB):
    # 50% chance at leveling up per 'tick'
    if bool(_random.getrandbits(1)):
        await adb_instance.click_bounding_box(BoundingBox(45, 600, 110, 680))
        await asyncio.sleep(2)

    # 5% chance to buy unit one in the shop
    if _random.randint(1, 20) == 20:
        await adb_instance.click_bounding_box(BoundingBox(175, 45, 370, 225))
        await asyncio.sleep(2)

    # 5% chance to buy unit two in the shop
    if _random.randint(1, 20) == 20:
        await adb_instance.click_bounding_box(BoundingBox(400, 45, 580, 255))
        await asyncio.sleep(2)

    # You get the idea
    if _random.randint(1, 20) == 20:
        await adb_instance.click_bounding_box(BoundingBox(620, 45, 810, 255))
        await asyncio.sleep(2)

    if _random.randint(1, 20) == 20:
        await adb_instance.click_bounding_box(BoundingBox(840, 45, 1030, 255))
        await asyncio.sleep(2)

    if _random.randint(1, 20) == 20:
        await adb_instance.click_bounding_box(BoundingBox(1070, 45, 1250, 255))
        await asyncio.sleep(2)


async def loop(adb_instance: ADB):
    """
    The main app loop logic.

    Args:
        adb_instance: An instance of the ADB connection to click in.
    """
    while True:
        screenshot = await adb_instance.get_screen()
        game_state = await get_game_state(screenshot)

        match game_state:
            case GameState.loading:
                print("TFT is loading, waiting for the main menu...")
                # TODO Check if the log-in prompt is on screen
                await asyncio.sleep(10)
            case GameState.main_menu:
                print("TFT is loaded, opening mode choice")
                await click_play(adb_instance)
            case GameState.choose_mode:
                print("Selecting normal game")
                await adb_instance.click_bounding_box(BoundingBox(50, 250, 275, 580))
            case GameState.queue_missed:
                await adb_instance.click_bounding_box(BoundingBox(555, 425, 725, 470))
            case GameState.lobby:
                await click_play(adb_instance)
                await queue(adb_instance)
            case GameState.in_game:
                print("Match is active, waiting for the exit button")
                screenshot = await adb_instance.get_screen()
                search_result = screen.get_on_screen(screenshot, Image.exit_now, BoundingBox(520, 400, 775, 425))
                while not search_result:
                    await temporary_game_loop(adb_instance)
                    await asyncio.sleep(10)
                    screenshot = await adb_instance.get_screen()
                    search_result = screen.get_on_screen(screenshot, Image.exit_now, BoundingBox(520, 400, 775, 425))
                    game_state = await get_game_state(screenshot)
                    if game_state == GameState.post_game:
                        break
                await adb_instance.click_bounding_box(BoundingBox(550, 425, 740, 440))
                await asyncio.sleep(10)
            case GameState.post_game:
                print("Match concluded, clicking Play again")
                await click_play(adb_instance)

        await asyncio.sleep(2)


async def get_game_state(screenshot: ndarray) -> GameState | None:
    """
    Get the current app/game state based off a screenshot.

    Args:
        screenshot: A screenshot that was taken by :class:`alune.adb.ADB`
    """
    if screen.get_on_screen(screenshot, Image.rito_logo):
        return GameState.loading

    if screen.get_on_screen(screenshot, Image.play) and not screen.get_on_screen(screenshot, Image.back):
        return GameState.main_menu

    if screen.get_on_screen(screenshot, Image.normal_game):
        return GameState.choose_mode

    if screen.get_on_screen(screenshot, Image.check):
        return GameState.queue_missed

    if screen.get_on_screen(screenshot, Image.close_lobby) and screen.get_on_screen(screenshot, Image.play):
        return GameState.lobby

    if screen.get_on_screen(screenshot, Image.composition) or screen.get_on_screen(screenshot, Image.items):
        return GameState.in_game

    if screen.get_on_screen(screenshot, Image.first_place) and screen.get_on_screen(screenshot, Image.back):
        return GameState.post_game


async def check_phone_preconditions(adb_instance: ADB):
    print("Checking pre-conditions of the phone")

    size = await adb_instance.get_screen_size()
    if size != "1280x720":
        print(f"Your screen size is {size}, which is unsupported. Changing it to 1280x720.")
        await adb_instance.set_screen_size()

    density = await adb_instance.get_screen_density()
    if density != "240":
        print(f"Your screen pixel density is {density}, which is unsupported. Changing it to 240.")
        await adb_instance.set_screen_density()

    if await adb_instance.get_memory() < 4_000_000:
        print("Your phone has less than 4GB of memory, you may experience lags.")

    if not await adb_instance.is_tft_active():
        if not await adb_instance.is_tft_installed():
            # TODO Avoid Google Play (add README warning for Google Play interruptions) and install from
            #  https://www.apkmirror.com/apk/riot-games-inc/teamfight-tactics-league-of-legends-strategy-game/
            #  Note, this also needs a functionality to update check (Does the app tell us? Parse from site?)
            print("TFT is not installed, please install it to continue. Exiting.")
            sys.exit(1)

        print("Tft is not active, starting it")
        await adb_instance.start_tft_app()


async def main():
    adb_instance = ADB()
    await adb_instance.load()
    if not adb_instance.is_connected():
        print("There is no ADB device ready on port 5555. Exiting.")
        return

    await check_phone_preconditions(adb_instance)

    await loop(adb_instance)


if __name__ == '__main__':
    asyncio.run(main())
