![alune_header](https://github.com/TeamFightTacticsBots/Alune/assets/60011425/dd30ed87-c5ca-42eb-810a-da07f6502cf5)
<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-green" />
  <img src="https://img.shields.io/badge/TFT_Set-11-blue" />
</p>

Teamfight Tactics (TFT) bot for the mobile version, to farm events/tokens.

## Setup

### Android Emulator

1. Download any Android emulator you find trustworthy that also has reasonable ADB support.  
   **We do not recommend a specific one** but tested examples are the AVD that comes with Android Studio, Google Play Games PC Developer Build, LDPlayer9 and Nox.  
   Some emulators may need adjustment of the port our ADB utility connects to (The place to adjust it is [here](./alune/adb.py) in `_connect_to_device`.)
2. Install the TFT APK by downloading it from [APKMirror](https://www.apkmirror.com/apk/riot-games-inc/teamfight-tactics-league-of-legends-strategy-game/) and dragging it into your emulator.  
   If drag and drop does not work, please review your emulator's documentation on how to install APK files.  
   **We discourage using Google Play** since it adds overlays the bot does not check for. Also, not entering your Google credentials in emulators is generally good security practice.
3. After installation, start the TFT app and log-in to your Riot account.  
   If you get a warning about needing to try again later, you may use a linked social log-in (Google, Facebook, XBox) if you trust your emulator.

### Bot

1. Download and install [Python 3.12](https://www.python.org/downloads/) for your operating system
2. Open a shell of your choice (Defaults: PowerShell on Windows, Zsh on MacOS, Bash on Linux)
3. Clone this repository: `git clone https://github.com/TeamFightTacticsBots/Alune.git`
4. Go into the repository: `cd Alune`
5. Create a virtual python environment: `python -m venv alune-venv`
6. Activate the venv. PowerShell: `alune-venv\Scripts\Activate.ps1`, Zsh/Bash: `alune-venv/bin/activate`  
   This should put `(alune-venv)` in the front of your shell prompt string.
7. Install the project dependencies: `pip install .`
   1. If you want to install for a development environment, use `pip install .[lint]`

## Running

### Emulator

1. Make sure your emulator is fully started up and ready to be interacted with.

> [!NOTE]
> While the bot will eventually handle almost any scenario the app may run into, it will never log in for you.
> You do not need to start TFT for the bot to be able to run, but it is a good idea to check if you are logged in.

### Bot

1. Activate the virtual environment, see setup step 6.  
   If you use PyCharm, you can use the in-built Terminal which does this automatically for you.
2. Run `python main.py`

## Development

### Linting

The project uses automatic formatting. Please adhere to it by using the following lint commands available to you after installation:
```bash
black .
isort .
flake8
pylint main.py alune
```
