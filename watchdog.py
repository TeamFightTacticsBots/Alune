import subprocess
import time
import sys


def main():
    print("--- Alune Watchdog Started ---")
    print("Press Ctrl+C to stop the watchdog completely.\n")

    while True:
        try:
            # sys.executable ensures we use the same 'python' (venv) that ran this script
            print(f"[Watchdog] Starting main.py...")
            subprocess.run([sys.executable, "main.py"])

            print("\n[Watchdog] Bot process ended. Restarting in 5 seconds...")
            time.sleep(5)

        except KeyboardInterrupt:
            print("\n[Watchdog] Stopping Watchdog. Goodbye!")
            sys.exit(0)
        except Exception as e:
            print(f"[Watchdog] Unexpected error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()