import cv2

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
        print("Tft is not active, starting it")
        adb_instance.start_tft_app()

    print("Tft is started, ready to proceed")


if __name__ == '__main__':
    main()
