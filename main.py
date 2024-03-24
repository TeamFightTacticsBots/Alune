from alune.adb import ADB


def main():
    adb_instance = ADB()
    print(f"Screen size: {adb_instance.get_screen_size()}")
    print(f"Memory: {adb_instance.get_memory_in_mb()}MB")


if __name__ == '__main__':
    main()
