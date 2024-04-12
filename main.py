import asyncio
import sys
from enum import StrEnum, auto
from random import Random

from adb_shell.exceptions import TcpTimeoutException
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
    print("Queue started, waiting for accept button")
    try:
        await asyncio.wait_for(wait_for_accept_button(adb_instance), timeout=120)
    except asyncio.TimeoutError:
        print("Waiting for accept button took longer than 120 seconds, checking state again")
        return
    await adb_instance.click_button(Button.accept)
    await asyncio.sleep(2)

    print("Match accepted")
    screenshot = await adb_instance.get_screen()
    while screen.get_on_screen(screenshot, Image.accepted):
        await asyncio.sleep(1)
        screenshot = await adb_instance.get_screen()

    await asyncio.sleep(3)

    screenshot = await adb_instance.get_screen()
    search_result = screen.get_button_on_screen(screenshot, Button.check)
    if search_result:
        print("We missed the queue")
        await adb_instance.click_image(search_result)
        await asyncio.sleep(2)
        await adb_instance.click_button(Button.play)
        await queue(adb_instance)

    if screen.get_button_on_screen(screenshot, Button.play):
        print("Queue got declined by someone")
        await queue(adb_instance)


_random = Random()


async def take_game_decision(adb_instance: ADB):
    screenshot = await adb_instance.get_screen()
    is_in_carousel = screen.get_on_screen(screenshot, Image.carousel)
    if is_in_carousel:
        # Move to a random point in the carousel area
        await adb_instance.click_bounding_box(BoundingBox(150, 100, 1100, 660))
        await asyncio.sleep(_random.randint(3, 9))
        return

    is_on_other_board = screen.get_button_on_screen(screenshot, Button.return_to_board)
    if is_on_other_board:
        await adb_instance.click_button(Button.return_to_board)
        await asyncio.sleep(1)
        return

    is_augment_offered = screen.get_on_screen(screenshot, Image.pick_augment)
    if is_augment_offered:
        # Roll each augment with a 50% chance
        augment_rolls = Button.get_augment_rolls()
        for i in range(len(augment_rolls)):
            if bool(_random.getrandbits(1)):
                await adb_instance.click_button(augment_rolls[i])

        # Pick a random augment
        augment = _random.choice(Button.get_augments())
        await adb_instance.click_button(augment)
        await asyncio.sleep(1)
        return

    can_buy_xp = screen.get_button_on_screen(screenshot, Button.buy_xp)
    if can_buy_xp and bool(_random.getrandbits(1)):
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

    for store_card in Button.get_store_cards():
        if not store_card.click_box.is_inside(search_result.get_middle()):
            continue
        await adb_instance.click_button(store_card)
        break


async def loop_disconnect_wrapper(adb_instance: ADB):
    try:
        await loop(adb_instance)
    except TcpTimeoutException:
        print("Device disconnected, attempting reconnect...")
        await adb_instance.load()
        if not adb_instance.is_connected():
            print("Could not reconnect. Please check your emulator for any errors. Exiting.")
            sys.exit(1)
        await loop_disconnect_wrapper(adb_instance)


async def loop(adb_instance: ADB):
    """
    The main app loop logic.

    Args:
        adb_instance: An instance of the ADB connection to click in.
    """
    while True:
        if not await adb_instance.is_tft_active():
            print("TFT is not in the foreground anymore, setting it back to active.")
            await adb_instance.start_tft_app()

        screenshot = await adb_instance.get_screen()
        game_state = await get_game_state(screenshot)

        match game_state:
            case GameState.loading:
                print("TFT is loading, waiting for the main menu...")
                # TODO Check if the log-in prompt is on screen
                await asyncio.sleep(10)
            case GameState.main_menu:
                print("TFT is loaded, opening mode choice")
                await adb_instance.click_button(Button.play)
            case GameState.choose_mode:
                print("Selecting normal game")
                await adb_instance.click_button(Button.normal_game)
            case GameState.queue_missed:
                print("Queue missed, clicking check mark")
                await adb_instance.click_button(Button.check)
            case GameState.lobby:
                await adb_instance.click_button(Button.play)
                await queue(adb_instance)
            case GameState.in_game:
                print("Match is active, waiting for the exit button")
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
                print("Match concluded, clicking Play again")
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
    print("Phone ready, starting main loop")

    await loop_disconnect_wrapper(adb_instance)


if __name__ == '__main__':
    asyncio.run(main())
