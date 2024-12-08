import asyncio

import keyboard
from loguru import logger

from alune import screen
from alune.adb import ADB
from alune.config import AluneConfig
from alune.images import Button, Image
from alune.tft.game import get_game_state, GameStateImageResult, GameState, take_game_decision

PAUSE_LOGIC = False
PLAY_NEXT_GAME = True


async def wait_for_accept_button(adb_instance: ADB):
    """
    Utility method to wait for the queue accept button.

    Args:
        adb_instance: An instance of the ADB connection to click in.
    """
    screenshot = await adb_instance.get_screen()
    search_result = screen.get_button_on_screen(screenshot, Button.accept)
    while not search_result:
        await asyncio.sleep(2)
        screenshot = await adb_instance.get_screen()
        search_result = screen.get_button_on_screen(screenshot, Button.accept)


async def queue(adb_instance: ADB, config: AluneConfig):
    """
    Utility method to queue a match.

    Args:
        adb_instance: An instance of the ADB connection to click in.
        config: An instance of the alune config to use.
    """
    try:
        await asyncio.wait_for(wait_for_accept_button(adb_instance), timeout=config.get_queue_timeout())
    except asyncio.TimeoutError:
        await adb_instance.click_button(Button.exit_lobby)
        logger.info("Queue exited due to timeout.")
        return
    await adb_instance.click_button(Button.accept)
    await asyncio.sleep(2)

    logger.debug("Queue accepted")
    screenshot = await adb_instance.get_screen()
    while screen.get_on_screen(screenshot, Image.ACCEPTED):
        await asyncio.sleep(1)
        screenshot = await adb_instance.get_screen()

    await asyncio.sleep(3)

    screenshot = await adb_instance.get_screen()
    if screen.get_button_on_screen(screenshot, Button.accept) or screen.get_button_on_screen(screenshot, Button.play):
        logger.debug("Queue was declined by someone else, staying in queue lock state")
        await queue(adb_instance, config)


async def take_app_decision(game_state_image_result: GameStateImageResult, adb_instance: ADB, config: AluneConfig):
    """
    Match the game state and take a decision based on it.

    Args:
         game_state_image_result: The result of the game state image search.
         adb_instance: The ADB instance to take action in.
         config: An instance of the alune config.
    """
    match game_state_image_result.game_state:
        case GameState.LOADING:
            logger.info("App state is loading...")
            # TODO Check if the log-in prompt is on screen
            await asyncio.sleep(10)
        case GameState.MAIN_MENU:
            logger.info("App state is main menu, clicking 'Play'.")
            await adb_instance.click_button(Button.play)
        case GameState.CHOICE_CONFIRM:
            logger.info("App state is choice confirm, accepting the choice.")
            await adb_instance.click_button(Button.check_choice)
        case GameState.CHOOSE_MODE:
            logger.info(f"App state is choose mode, selecting {config.get_game_mode()}.")
            await adb_instance.click_image(game_state_image_result.image_result)
        case GameState.QUEUE_MISSED:
            logger.info("App state is queue missed, clicking it.")
            await adb_instance.click_button(Button.check)
        case GameState.LOBBY:
            logger.info("App state is in lobby, locking bot into queue tft.")
            await adb_instance.click_button(Button.play)
            await queue(adb_instance, config)
            logger.info("Queue lock released, likely loading into game now.")
        case GameState.IN_GAME:
            logger.info("App state is in game, looping decision making and waiting for the exit button.")
            screenshot = await adb_instance.get_screen()
            search_result = screen.get_button_on_screen(screenshot, Button.exit_now)
            while not search_result:
                if PAUSE_LOGIC:
                    await asyncio.sleep(5)
                    continue

                if not await adb_instance.is_tft_active():
                    logger.info("TFT got closed, starting it again.")
                    await adb_instance.start_tft_app()
                    await asyncio.sleep(10)
                    break

                await take_game_decision(adb_instance, config)
                await asyncio.sleep(5)
                screenshot = await adb_instance.get_screen()

                game_state = await get_game_state(screenshot, config)
                if game_state and game_state.game_state in {
                    GameState.POST_GAME,
                    GameState.POST_GAME_DAWN_OF_HEROES,
                }:
                    break

                search_result = screen.get_button_on_screen(screenshot, Button.exit_now)
            await adb_instance.click_button(Button.exit_now)
            await asyncio.sleep(10)
        case GameState.POST_GAME_DAWN_OF_HEROES:
            logger.info("App state is after a game for dawn of heroes, clicking 'Continue'.")
            await adb_instance.click_button(Button.dawn_of_heroes_continue)
        case GameState.POST_GAME:
            logger.info("App state is post game, clicking 'Play again'.")
            await adb_instance.click_button(Button.play)


async def loop(adb_instance: ADB, config: AluneConfig):
    """
    The main app loop tft.

    Args:
        adb_instance: An instance of the ADB connection to click in.
        config: An instance of the alune config to use.
    """
    while True:
        await delay_next_game()

        if PAUSE_LOGIC:
            await asyncio.sleep(5)
            continue

        if not await adb_instance.is_tft_active():
            logger.info("TFT was not in the foreground, setting it as active.")
            await adb_instance.start_tft_app()
            await asyncio.sleep(5)

        screenshot = await adb_instance.get_screen()
        game_state_image_result = await get_game_state(screenshot, config)

        if not game_state_image_result:
            await asyncio.sleep(2)
            continue

        await take_app_decision(game_state_image_result, adb_instance, config)

        await asyncio.sleep(2)



async def delay_next_game():
    """
    Checks whether to delay the next game based on the PLAY_NEXT_GAME variable
    """
    wait_counter = 0
    while not PLAY_NEXT_GAME:
        sleep_time = 15
        # Don't print it every iteration
        if wait_counter > 0 and (sleep_time * wait_counter) % 30 == 0:
            logger.debug(f"Play next game still disabled after {sleep_time * wait_counter} seconds")
        await asyncio.sleep(sleep_time)
        wait_counter = wait_counter + 1


def toggle_pause() -> None:
    """
    Toggles whether the bots tft evaluation should pause.
    *Note:* This does not entirely stop the bot, but does stop various state changes that can be annoying if you're
    trying to manually interact with it.
    """
    global PAUSE_LOGIC  # pylint: disable=global-statement
    logger.debug(f"alt+p pressed, toggling pause from {PAUSE_LOGIC} to {not PAUSE_LOGIC}")
    PAUSE_LOGIC = not PAUSE_LOGIC
    if PAUSE_LOGIC:
        logger.warning("Bot now paused, remember to unpause to continue botting!")
    else:
        logger.warning("Bot playing again!")


def toggle_play_next_game() -> None:
    """
    Toggles whether the bots tft evaluation should start a new game after this finishes.
    *Note:* This does not entirely stop the bot, but will stop it from starting a new game.
    """
    global PLAY_NEXT_GAME  # pylint: disable=global-statement
    logger.debug(f"alt+n pressed, toggling pause from {PLAY_NEXT_GAME} to {not PLAY_NEXT_GAME}")
    PLAY_NEXT_GAME = not PLAY_NEXT_GAME
    if not PLAY_NEXT_GAME:
        logger.warning("Bot will not queue a new game when a lobby is detected!")
    else:
        logger.warning("Bot will queue a new game when in lobby!")


def setup_hotkeys() -> None:
    """
    Setup hotkey listeners
    """
    keyboard.add_hotkey("alt+p", toggle_pause)
    keyboard.add_hotkey("alt+n", toggle_play_next_game)
