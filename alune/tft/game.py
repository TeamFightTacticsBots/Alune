"""
Module to handle all TFT game related interactions.
"""

import asyncio
from random import Random

from loguru import logger
from numpy import ndarray

from alune import screen
from alune.adb import ADB
from alune.config import AluneConfig
from alune.images import BoundingBox
from alune.images import Button
from alune.images import Image
from alune.tft.planning.planning import TFTPlanning


class TFTGame:
    """
    Class to hold variables and methods relating to handling the TFT game.
    """

    def __init__(self, adb_instance: ADB, alune_config: AluneConfig):
        self.adb = adb_instance
        self.config = alune_config
        self.random = Random()

        self.planning = TFTPlanning(adb_instance, alune_config)

    async def take_game_decision(self):
        """
        Called by the game loop to take a decision in the current game.
        """
        screenshot = await self.adb.get_screen()

        if await self.check_surrender_state(screenshot):
            await self.surrender_game()
            return

        is_in_carousel = screen.get_on_screen(screenshot, Image.CAROUSEL)
        if is_in_carousel:
            logger.debug("Is on carousel, clicking a random point within bounds")
            await self.adb.click_bounding_box(BoundingBox(420, 180, 825, 425))
            await asyncio.sleep(2)
            return

        is_on_other_board = screen.get_button_on_screen(screenshot, Button.return_to_board)
        if is_on_other_board:
            logger.debug("Is on other board, returning to own board")
            await self.adb.click_button(Button.return_to_board)
            await asyncio.sleep(0.5)
            return

        is_augment_offered = screen.get_on_screen(screenshot, Image.PICK_AUGMENT)
        if is_augment_offered:
            await self.select_augment()
            return

        is_choose_one_hidden = screen.get_button_on_screen(screenshot, Button.choose_one_hidden, precision=0.9)
        if is_choose_one_hidden:
            logger.debug("Choose one is hidden, clicking it to show offers")
            await self.adb.click_button(Button.choose_one_hidden)
            await asyncio.sleep(2)
            screenshot = await self.adb.get_screen()

        is_choose_one_active = screen.get_button_on_screen(screenshot, Button.choose_one, precision=0.9)
        if is_choose_one_active:
            logger.debug("Choosing from an item or a choice offer")
            await self.adb.click_button(Button.choose_one)
            await asyncio.sleep(1)
            return

        is_shop_opened = screen.get_button_on_screen(screenshot, Button.store_lock, precision=0.9)
        # When the shop is opened, we're in planning phase
        if is_shop_opened:
            logger.debug("Planning phase")
            await self.planning.planning_phase()
            logger.debug("Planning phase ended")
            return

    def reset_planning(self):
        """
        Resets the planning state for a new game.
        """
        self.planning.reset_planning()

    async def select_augment(self):
        """
        Checks for augments on the current screen and picks some if possible.

        Args:
            screenshot: The current screen.
        """
        logger.debug("Augments offered")
        # Roll each augment with a 50% chance
        augment_rolls = Button.get_augment_rolls()
        # Randomize order in which we roll
        self.random.shuffle(augment_rolls)
        for augment in augment_rolls:
            if bool(self.random.getrandbits(1)):
                logger.debug(f"Rolling augment offer {Button.get_augment_rolls().index(augment) + 1}")
                await self.adb.click_button(augment)
            await asyncio.sleep(1)
        await asyncio.sleep(2)

        # Pick a random augment
        augment_idx = self.random.randint(0, len(Button.get_augments()) - 1)
        augment = Button.get_augments()[augment_idx]
        logger.debug(f"Selecting augment {augment_idx + 1}")
        await self.adb.click_button(augment)
        await asyncio.sleep(1)

    async def check_surrender_state(self, screenshot: ndarray) -> bool:
        """
        Check if we're able to surrender from the current game state.

        Args:
            screenshot: The current screen.

        Returns:
            Whether we're able to surrender.
        """
        if not self.config.should_surrender():
            return False

        logger.debug("Checking whether we can surrender")
        if not screen.get_on_screen(screenshot, Image.COLLAPSE_TOP_BAR):
            await self.adb.click_button(Button.expand_top_bar)
            await asyncio.sleep(1)
            screenshot = await self.adb.get_screen()

        is_phase_3_2 = screen.get_on_screen(screenshot, Image.PHASE_3_2_FULL)
        if not is_phase_3_2:
            return False

        surrender_delay = self.config.get_surrender_delay()
        logger.info(f"Surrendering the game in {surrender_delay} seconds.")
        await asyncio.sleep(surrender_delay)
        return True

    async def surrender_game(self):
        """
        Surrenders the current game.
        """
        await self.adb.go_back()
        await asyncio.sleep(2)
        await self.adb.click_button(Button.surrender)
        await asyncio.sleep(2)
        await self.adb.click_button(Button.check_surrender)
        await asyncio.sleep(5)
