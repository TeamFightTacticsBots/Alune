![alune_header](https://github.com/TeamFightTacticsBots/Alune/assets/60011425/dd30ed87-c5ca-42eb-810a-da07f6502cf5)
<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-green" />
  <img src="https://img.shields.io/badge/TFT_Set-11-blue" />
  <img src="https://github.com/TeamFightTacticsBots/Alune/actions/workflows/build.yml/badge.svg" />
</p>

Teamfight Tactics / TFT bot for the mobile version. Farms pass experience, events, and tokens.

**Table of Contents**
1. [Features](#features)
2. [Setup](#setup)
   1. [Android Emulator](#android-emulator)
   2. [Bot (executable)](#bot-executable)
   3. [Bot (source)](#bot-source)
3. [Running](#running)
   1. [Emulator](#emulator)
   2. [Bot (executable)](#bot-executable-1)
   3. [Bot (source)](#bot-source-1)
4. [Development](#development) 

## Features

The purpose is to farm the TFT pass experience and League event tokens. The bot is "good enough".
We will never support playing ranked with it. We also do not encourage you to learn from its decisions.

1. Uses ADB to be able to support every emulator or phone and runs in the background
2. Can start up TFT and queues for normal games
3. Buys experience and shop cards (currently only Heavenly units)
4. Rolls and buys augments
5. Walks around on carousel rounds

You can find planned and potential future features on our [Features wiki page](https://github.com/TeamFightTacticsBots/Alune/wiki/Features).

The TFT bot is available as a Windows executable for convenience. Running from source is supported as well.

## Setup

### Android Emulator

1. Download any Android emulator you find trustworthy that also has reasonable ADB support.
   1. Please refer to the [wiki page about emulators](https://github.com/TeamFightTacticsBots/Alune/wiki/Emulators) for more information.
   2. Some emulators may need adjustment of the port our ADB utility connects to. The place to adjust it is - after running the bot once - in `alune-output/config.yml`.
2. Install the TFT APK by downloading it from [APKMirror](https://www.apkmirror.com/apk/riot-games-inc/teamfight-tactics-league-of-legends-strategy-game/) and dragging it into your emulator.
   1. If drag and drop does not work, review your emulator's documentation on how to install APK files.  
   2. While the bot should work with the Google Play version, **we discourage using Google Play**. It may add overlays the bot does not check for. It is also generally good security practice to **not** enter your Google credentials in emulators.
3. Start the TFT app and log in to your Riot account.
   1. If you get a warning about needing to try again later, try a linked social log-in (Google, Facebook, Xbox).

### Bot (executable)

1. Download the latest [release](https://github.com/TeamFightTacticsBots/Alune/releases).

### Bot (source)

1. Download and install [Python 3.12](https://www.python.org/downloads/) for your operating system
2. Download and install [git](https://git-scm.com/downloads) for your operating system
3. Open a shell of your choice (Defaults: PowerShell on Windows, Zsh on MacOS, Bash on Linux)
   1. You can verify your python version by running `python --version`.
4. Clone this repository: `git clone https://github.com/TeamFightTacticsBots/Alune.git`
5. Go into the repository: `cd Alune`
6. Create a virtual Python environment: `python -m venv alune-venv`
7. Activate the virtual environment.  
   1. PowerShell: `alune-venv\Scripts\Activate.ps1`, Zsh/Bash: `alune-venv/bin/activate`  
   2. This should put `(alune-venv)` in the front of your shell prompt string.
8. Install the project dependencies: `pip install .`
   1. If you want to install for a development environment, use `pip install .[dev]`

## Running

### Emulator

1. Make sure your emulator runs and is interactable.

> [!NOTE]
> While the bot will handle almost any scenario the app may run into, it will never log in for you.
> You do not need to start TFT for the bot to be able to run, but it is a good idea to check if you are logged in.

### Bot (executable)

1. Run the downloaded `Alune.exe`. 

The configuration for the bot can be found in the `alune-output` folder that's created during the first run.
Logs for bug reports can be found in the `logs` folder in that output folder.

### Bot (source)

1. If not already active, activate the virtual environment - see setup step 7.  
   1. If you use PyCharm or VS Code, you can use the in-built terminal, which does this automatically for you.
2. Run `python main.py`

Same as with the executable, configuration and logs are in the `alune-output` folder.

## Development

### Linting

The project uses automatic formatting. Use the following lint commands available to you after installation:
```bash
black .
isort .
flake8
pylint main.py alune
```

### Compiling

Bundling the project into a .exe can be done with
```bash
pyinstaller Alune.spec
```
