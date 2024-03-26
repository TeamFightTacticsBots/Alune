from time import sleep

from alune import screen
from alune.adb import ADB


def main():
    adb_instance = ADB()
    if not adb_instance.is_connected():
        print("There is no ADB device ready on port 5555. Exiting.")
        return

    screen_size = adb_instance.get_screen_size()
    if screen_size[0] != 1280 or screen_size[1] != 720:
        # TODO Force screen size with density 240
        print("The bot only supports 1280 x 720")
        return

    if adb_instance.get_memory() < 4_000_000:
        print("Your phone has less than 4GB of memory, you may experience lags.")

    if not adb_instance.is_tft_active():
        if not adb_instance.is_tft_installed():
            print("TFT is not installed, please install it to continue. Exiting.")
            return
        print("Tft is not active, starting it")
        adb_instance.start_tft_app()

    print("Tft is started, waiting for play button")
    screenshot = adb_instance.get_screen()
    search_result = screen.get_on_screen(image=screenshot, path="alune/images/play_button.png")
    while not search_result:
        sleep(5)
        screenshot = adb_instance.get_screen()
        search_result = screen.get_on_screen(image=screenshot, path="alune/images/play_button.png")
        print("Still waiting for the play button...")
    print("Play button found, ready to start a match")
    adb_instance.click_image(search_result=search_result)


if __name__ == '__main__':
    main()
