import asyncio

from alune import screen
from alune.adb import ADB
from alune.screen import BoundingBox


async def main():
    adb_instance = ADB()
    await adb_instance.load()
    if not adb_instance.is_connected():
        print("There is no ADB device ready on port 5555. Exiting.")
        return

    screen_size = await adb_instance.get_screen_size()
    if screen_size[0] != 1280 or screen_size[1] != 720:
        # TODO Force screen size with density 240
        print("The bot only supports 1280 x 720")
        return

    if await adb_instance.get_memory() < 4_000_000:
        print("Your phone has less than 4GB of memory, you may experience lags.")

    if not await adb_instance.is_tft_active():
        if not await adb_instance.is_tft_installed():
            print("TFT is not installed, please install it to continue. Exiting.")
            return
        print("Tft is not active, starting it")
        await adb_instance.start_tft_app()

    print("Tft is started, waiting for play button")
    screenshot = await adb_instance.get_screen()
    search_result = screen.get_on_screen(screenshot, "alune/images/play_button.png")
    while not search_result:
        await asyncio.sleep(5)
        screenshot = await adb_instance.get_screen()
        search_result = screen.get_on_screen(screenshot, "alune/images/play_button.png")
        print("Still waiting for the play button...")
    print("Play button found, ready to start a match")
    await adb_instance.click_image(search_result)
    await asyncio.sleep(2)

    print("Creating a normal game lobby")
    screenshot = await adb_instance.get_screen()
    search_result = screen.get_on_screen(screenshot, "alune/images/normal_game.png")
    if not search_result:
        print("Could not find normal game button")
        return
    await adb_instance.click_image(search_result)
    await asyncio.sleep(2)

    print("Clicking play in the lobby")
    screenshot = await adb_instance.get_screen()
    search_result = screen.get_on_screen(screenshot, "alune/images/play_button.png")
    if not search_result:
        print("Could not find play button")
        return
    await adb_instance.click_image(search_result)
    await asyncio.sleep(2)

    print("Queue started, waiting for accept button")
    await queue(adb_instance)

    print("Match started, waiting for exit button")
    await asyncio.sleep(300)
    screenshot = await adb_instance.get_screen()
    search_result = screen.get_on_screen(screenshot, "alune/images/exit_now.png", BoundingBox(520, 400, 775, 425))
    while not search_result:
        await asyncio.sleep(60)
        screenshot = await adb_instance.get_screen()
        search_result = screen.get_on_screen(screenshot, "alune/images/exit_now.png", BoundingBox(520, 400, 775, 425))
    await adb_instance.click_image(search_result, offset_y=10)
    await asyncio.sleep(10)

    print("Going back from end screen to main menu")
    await adb_instance.go_back()
    print("Exited, ready to loop again")


async def queue(adb_instance: ADB):
    screenshot = await adb_instance.get_screen()
    search_result = screen.get_on_screen(screenshot, "alune/images/accept.png")
    while not search_result:
        await asyncio.sleep(2)
        screenshot = await adb_instance.get_screen()
        search_result = screen.get_on_screen(screenshot, "alune/images/accept.png")
    await adb_instance.click_image(search_result, offset_y=10)
    await asyncio.sleep(2)

    print("Match accepted")
    screenshot = await adb_instance.get_screen()
    while screen.get_on_screen(screenshot, "alune/images/accepted.png"):
        await asyncio.sleep(1)
        screenshot = await adb_instance.get_screen()

    await asyncio.sleep(2)
    screenshot = await adb_instance.get_screen()
    if screen.get_on_screen(screenshot, "alune/images/play_button.png"):
        print("Queue got declined by someone, waiting for accept button again")
        await queue(adb_instance)


if __name__ == '__main__':
    asyncio.run(main())
