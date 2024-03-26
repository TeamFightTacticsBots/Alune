from time import sleep

from alune import screen
from alune.adb import ADB
from alune.screen import BoundingBox


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
    search_result = screen.get_on_screen(adb_instance.get_screen(), "alune/images/play_button.png")
    while not search_result:
        sleep(5)
        search_result = screen.get_on_screen(adb_instance.get_screen(), "alune/images/play_button.png")
        print("Still waiting for the play button...")
    print("Play button found, ready to start a match")
    adb_instance.click_image(search_result)
    sleep(2)

    print("Creating a normal game lobby")
    search_result = screen.get_on_screen(adb_instance.get_screen(), "alune/images/normal_game.png")
    if not search_result:
        print("Could not find normal game button")
        return
    adb_instance.click_image(search_result)
    sleep(2)

    print("Clicking play in the lobby")
    search_result = screen.get_on_screen(adb_instance.get_screen(), "alune/images/play_button.png")
    if not search_result:
        print("Could not find play button")
        return
    adb_instance.click_image(search_result)
    sleep(2)

    print("Queue started, waiting for accept button")
    queue(adb_instance)

    print("Match started, waiting for exit button")
    sleep(300)
    search_result = screen.get_on_screen(adb_instance.get_screen(), "alune/images/exit_now.png", BoundingBox(520, 400, 775, 425))
    while not search_result:
        sleep(60)
        search_result = screen.get_on_screen(adb_instance.get_screen(), "alune/images/exit_now.png", BoundingBox(520, 400, 775, 425))
    adb_instance.click_image(search_result, offset_y=10)
    sleep(10)

    print("Going back from end screen to main menu")
    adb_instance.go_back()
    print("Exited, ready to loop again")


def queue(adb_instance: ADB):
    search_result = screen.get_on_screen(adb_instance.get_screen(), "alune/images/accept.png")
    while not search_result:
        sleep(2)
        search_result = screen.get_on_screen(adb_instance.get_screen(), "alune/images/accept.png")
    adb_instance.click_image(search_result, offset_y=10)
    sleep(2)

    print("Match accepted")
    while screen.get_on_screen(adb_instance.get_screen(), "alune/images/accepted.png"):
        sleep(1)

    sleep(2)
    if screen.get_on_screen(adb_instance.get_screen(), "alune/images/play_button.png"):
        print("Queue got declined by someone, waiting for accept button again")
        queue(adb_instance)


if __name__ == '__main__':
    main()
