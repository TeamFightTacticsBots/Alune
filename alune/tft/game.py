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


class TFTGame:
    """
    Class to hold variables and methods relating to handling the TFT game.
    """

    def __init__(self, adb_instance: ADB, alune_config: AluneConfig):
        self.adb = adb_instance
        self.config = alune_config
        self.random = Random()

    async def handle_augments(self, screenshot: ndarray):
        """
        Checks for augments on the current screen and picks some if possible.

        Args:
            screenshot: The current screen.
        """
        is_augment_offered = screen.get_on_screen(screenshot, Image.PICK_AUGMENT)
        if not is_augment_offered:
            return

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

    async def buy_from_shop(self):
        """
        Checks the shop for traits and purchases it if found.
        """
        screenshot = await self.adb.get_screen()
        logger.debug("Buying from shop")
        for trait in self.config.get_traits():
            search_results = screen.get_all_on_screen(
                image=screenshot,
                path=trait,
                bounding_box=BoundingBox(170, 110, 1250, 230),
                precision=0.9,
            )
            if len(search_results) == 0:
                logger.debug(f"No card in the shop has the trait {trait.name}.")
                continue

            logger.debug(f"{len(search_results)} cards in the shop have the trait {trait.name}.")
            store_cards = Button.get_store_cards()
            self.random.shuffle(store_cards)
            for search_result in search_results:
                for store_card in store_cards:
                    if not store_card.click_box.is_inside(search_result.get_middle()):
                        continue
                    logger.debug(f"Buying store card {Button.get_store_cards().index(store_card) + 1}")
                    await self.adb.click_button(store_card)
                    break

                await asyncio.sleep(self.random.uniform(0.25, 0.75))

    async def take_game_decision(self):
        """
        Called by the game loop to take a decision in the current game.
        """
        screenshot = await self.adb.get_screen()

        is_on_other_board = screen.get_button_on_screen(screenshot, Button.return_to_board)
        if is_on_other_board:
            logger.debug("Is on other board, checking if we are on a carousel")
            await self.adb.click_button(Button.return_to_board)
            await asyncio.sleep(1)

            screenshot = await self.adb.get_screen()
            is_in_carousel = screen.get_on_screen(screenshot, Image.CAROUSEL)
            if is_in_carousel:
                logger.debug("Is on carousel, clicking a random point within bounds")
                await self.adb.click_button(Button.return_to_board)
                await asyncio.sleep(2)
                # Move to a random point in the carousel area
                await self.adb.click_bounding_box(BoundingBox(420, 180, 825, 425))
            return

        await self.handle_augments(screenshot)

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

        can_buy_xp = screen.get_button_on_screen(screenshot, Button.buy_xp)
        if can_buy_xp and self.random.randint(1, 100) <= self.config.get_chance_to_buy_xp():
            logger.debug("Buying XP")
            await self.adb.click_button(Button.buy_xp)
            await asyncio.sleep(1)

        await self.buy_from_shop()

        if await self.check_surrender_state(screenshot):
            await self.surrender_game()
