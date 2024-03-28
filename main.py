import asyncio
import sys
from enum import StrEnum, auto

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


async def click_play(adb_instance: ADB):
    await adb_instance.click_bounding_box(BoundingBox(950, 600, 1200, 650))


async def queue(adb_instance: ADB):
    print("Queue started, waiting for accept button")
    screenshot = await adb_instance.get_screen()
    search_result = screen.get_on_screen(screenshot, Image.accept)
    while not search_result:
        await asyncio.sleep(2)
        screenshot = await adb_instance.get_screen()
        search_result = screen.get_on_screen(screenshot, Image.accept)
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
        print("We accidentally missed the queue")
        await adb_instance.click_image(search_result)
        await asyncio.sleep(2)
        await click_play(adb_instance)
        await queue(adb_instance)

    if screen.get_on_screen(screenshot, Image.play):
        print("Queue got declined by someone")
        await queue(adb_instance)


async def loop(adb_instance: ADB):
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
                # TODO When we want to move to actually doing something in the game,
                #  we need GameState.game_loading
                await asyncio.sleep(300)
            case GameState.in_game:
                print("Match is active, waiting for the exit button")
                screenshot = await adb_instance.get_screen()
                search_result = screen.get_on_screen(screenshot, Image.exit_now, BoundingBox(520, 400, 775, 425))
                while not search_result:
                    await asyncio.sleep(10)
                    screenshot = await adb_instance.get_screen()
                    search_result = screen.get_on_screen(screenshot, Image.exit_now, BoundingBox(520, 400, 775, 425))
                await adb_instance.click_bounding_box(BoundingBox(550, 425, 740, 440))
                await asyncio.sleep(10)
            case GameState.post_game:
                print("Match concluded, clicking Play again")
                await click_play(adb_instance)

        await asyncio.sleep(2)


async def get_game_state(screenshot: ndarray) -> GameState | None:
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
