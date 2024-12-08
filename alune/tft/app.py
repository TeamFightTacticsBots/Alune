"""
Module to handle all TFT app related interactions.
"""

import asyncio
from dataclasses import dataclass
from enum import auto
from enum import StrEnum

import keyboard
from loguru import logger
from numpy import ndarray

from alune import screen
from alune.adb import ADB
from alune.config import AluneConfig
from alune.images import Button
from alune.images import Image
from alune.screen import ImageSearchResult
from alune.tft.game import TFTGame

PAUSE_LOGIC = False
PLAY_NEXT_GAME = True


class GameState(StrEnum):
    """
    State the game or app is in.
    """

    LOADING = auto()
    MAIN_MENU = auto()
    CHOOSE_MODE = auto()
    LOBBY = auto()
    QUEUE_MISSED = auto()
    IN_GAME = auto()
    POST_GAME_DAWN_OF_HEROES = auto()
    POST_GAME = auto()
    CHOICE_CONFIRM = auto()


@dataclass
class GameStateImageResult:
    """
    Combines a game state with an image search result (both optional)
    """

    game_state: GameState
    image_result: ImageSearchResult | None = None


class TFTApp:
    """
    Class to hold variables and methods relating to handling the overarching TFT app.
    """

    def __init__(self, adb_instance: ADB, alune_config: AluneConfig):
        self.adb = adb_instance
        self.config = alune_config
        self.game = TFTGame(adb_instance, alune_config)
        self._pause = False
        self._play_next_game = True
        self.setup_hotkeys()

    async def wait_for_accept_button(self):
        """
        Utility method to wait for the queue accept button.
        """
        screenshot = await self.adb.get_screen()
        search_result = screen.get_button_on_screen(screenshot, Button.accept)
        while not search_result:
            await asyncio.sleep(2)
            screenshot = await self.adb.get_screen()
            search_result = screen.get_button_on_screen(screenshot, Button.accept)

    async def queue(self):
        """
        Utility method to queue a match.
        """
        try:
            await asyncio.wait_for(self.wait_for_accept_button(), timeout=self.config.get_queue_timeout())
        except asyncio.TimeoutError:
            await self.adb.click_button(Button.exit_lobby)
            logger.info("Queue exited due to timeout.")
            return
        await self.adb.click_button(Button.accept)
        await asyncio.sleep(2)

        logger.debug("Queue accepted")
        screenshot = await self.adb.get_screen()
        while screen.get_on_screen(screenshot, Image.ACCEPTED):
            await asyncio.sleep(1)
            screenshot = await self.adb.get_screen()

        await asyncio.sleep(3)

        screenshot = await self.adb.get_screen()
        if screen.get_button_on_screen(screenshot, Button.accept) or screen.get_button_on_screen(
            screenshot, Button.play
        ):
            logger.debug("Queue was declined by someone else, staying in queue lock state")
            await self.queue()

    async def take_app_decision(self, game_state_image_result: GameStateImageResult):
        """
        Match the game state and take a decision based on it.

        Args:
             game_state_image_result: The result of the game state image search.
        """
        match game_state_image_result.game_state:
            case GameState.LOADING:
                logger.info("App state is loading...")
                # TODO Check if the log-in prompt is on screen
                await asyncio.sleep(10)
            case GameState.MAIN_MENU:
                logger.info("App state is main menu, clicking 'Play'.")
                await self.adb.click_button(Button.play)
            case GameState.CHOICE_CONFIRM:
                logger.info("App state is choice confirm, accepting the choice.")
                await self.adb.click_button(Button.check_choice)
            case GameState.CHOOSE_MODE:
                logger.info(f"App state is choose mode, selecting {self.config.get_game_mode()}.")
                await self.adb.click_image(game_state_image_result.image_result)
            case GameState.QUEUE_MISSED:
                logger.info("App state is queue missed, clicking it.")
                await self.adb.click_button(Button.check)
            case GameState.LOBBY:
                logger.info("App state is in lobby, locking bot into queue tft.")
                await self.adb.click_button(Button.play)
                await self.queue()
                logger.info("Queue lock released, likely loading into game now.")
            case GameState.IN_GAME:
                logger.info("App state is in game, looping decision making and waiting for the exit button.")
                screenshot = await self.adb.get_screen()
                search_result = screen.get_button_on_screen(screenshot, Button.exit_now)
                while not search_result:
                    if PAUSE_LOGIC:
                        await asyncio.sleep(5)
                        continue

                    if not await self.adb.is_tft_active():
                        logger.info("TFT got closed, starting it again.")
                        await self.adb.start_tft_app()
                        await asyncio.sleep(10)
                        break

                    await self.game.take_game_decision()
                    await asyncio.sleep(5)
                    screenshot = await self.adb.get_screen()

                    game_state = await self.get_app_state(screenshot)
                    if game_state and game_state.game_state in {
                        GameState.POST_GAME,
                        GameState.POST_GAME_DAWN_OF_HEROES,
                    }:
                        break

                    search_result = screen.get_button_on_screen(screenshot, Button.exit_now)
                await self.adb.click_button(Button.exit_now)
                await asyncio.sleep(10)
            case GameState.POST_GAME_DAWN_OF_HEROES:
                logger.info("App state is after a game for dawn of heroes, clicking 'Continue'.")
                await self.adb.click_button(Button.dawn_of_heroes_continue)
            case GameState.POST_GAME:
                logger.info("App state is post game, clicking 'Play again'.")
                await self.adb.click_button(Button.play)

    # pylint: disable-next=too-many-return-statements
    async def get_app_state(self, screenshot: ndarray) -> GameStateImageResult | None:
        """
        Get the current app/game state based off a screenshot.

        Args:
            screenshot: A screenshot that was taken by :class:`alune.adb.ADB`
        """
        if screen.get_button_on_screen(screenshot, Button.check_choice):
            return GameStateImageResult(GameState.CHOICE_CONFIRM)

        if screen.get_on_screen(screenshot, Image.RITO_LOGO):
            return GameStateImageResult(GameState.LOADING)

        if screen.get_on_screen(screenshot, Button.play.image_path) and not screen.get_on_screen(
            screenshot, Image.BACK
        ):
            return GameStateImageResult(GameState.MAIN_MENU)

        game_mode_image = Image.DAWN_OF_HEROES if self.config.get_game_mode() == "dawn of heroes" else Image.NORMAL_GAME
        if image_result := screen.get_on_screen(screenshot, game_mode_image):
            return GameStateImageResult(game_state=GameState.CHOOSE_MODE, image_result=image_result)

        if screen.get_button_on_screen(screenshot, Button.check):
            return GameStateImageResult(GameState.QUEUE_MISSED)

        if screen.get_on_screen(screenshot, Image.CLOSE_LOBBY) and screen.get_button_on_screen(screenshot, Button.play):
            return GameStateImageResult(GameState.LOBBY)

        if screen.get_on_screen(screenshot, Image.COMPOSITION) or screen.get_on_screen(screenshot, Image.ITEMS):
            return GameStateImageResult(GameState.IN_GAME)

        if screen.get_on_screen(screenshot, Image.BACK) and screen.get_button_on_screen(
            screenshot, Button.dawn_of_heroes_continue
        ):
            return GameStateImageResult(GameState.POST_GAME_DAWN_OF_HEROES)

        if screen.get_on_screen(screenshot, Image.FIRST_PLACE) and screen.get_on_screen(screenshot, Image.BACK):
            return GameStateImageResult(GameState.POST_GAME)

        return None

    async def loop(self):
        """
        The main tft app loop.
        """
        while True:
            await self.delay_next_game()

            if PAUSE_LOGIC:
                await asyncio.sleep(5)
                continue

            if not await self.adb.is_tft_active():
                logger.info("TFT was not in the foreground, setting it as active.")
                await self.adb.start_tft_app()
                await asyncio.sleep(5)

            screenshot = await self.adb.get_screen()
            game_state_image_result = await self.get_app_state(screenshot)

            if not game_state_image_result:
                await asyncio.sleep(2)
                continue

            await self.take_app_decision(game_state_image_result)

            await asyncio.sleep(2)

    async def delay_next_game(self):
        """
        Checks whether to delay the next game based on the _play_next_game variable.
        """
        wait_counter = 0
        while not self._play_next_game:
            sleep_time = 15
            # Don't print it every iteration
            if wait_counter > 0 and (sleep_time * wait_counter) % 30 == 0:
                logger.debug(f"Play next game still disabled after {sleep_time * wait_counter} seconds")
            await asyncio.sleep(sleep_time)
            wait_counter = wait_counter + 1

    def toggle_pause(self) -> None:
        """
        Toggles whether the bots tft evaluation should pause.
        *Note:* This does not entirely stop the bot, but does stop various state changes that can be annoying if you're
        trying to manually interact with it.
        """
        logger.debug(f"alt+p pressed, toggling pause from {self._pause} to {not self._pause}")
        self._pause = not self._pause
        if self._pause:
            logger.warning("Bot now paused, remember to unpause to continue botting!")
        else:
            logger.warning("Bot playing again!")

    def toggle_play_next_game(self) -> None:
        """
        Toggles whether the bots tft evaluation should start a new game after this finishes.
        *Note:* This does not entirely stop the bot, but will stop it from starting a new game.
        """
        logger.debug(f"alt+n pressed, toggling pause from {self._play_next_game} to {not self._play_next_game}")
        self._play_next_game = not self._play_next_game
        if not self._play_next_game:
            logger.warning("Bot will not queue a new game when a lobby is detected!")
        else:
            logger.warning("Bot will queue a new game when in lobby!")

    def setup_hotkeys(self) -> None:
        """
        Setup hotkey listeners
        """
        keyboard.add_hotkey("alt+p", self.toggle_pause)
        keyboard.add_hotkey("alt+n", self.toggle_play_next_game)
