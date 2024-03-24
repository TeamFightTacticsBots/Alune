from alune.adb import ADB


def main():
    adb_instance = ADB()
    print(adb_instance.get_screen_size())


if __name__ == '__main__':
    main()
