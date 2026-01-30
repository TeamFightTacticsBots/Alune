"""
Module to handle all TFT economy related interactions.
"""

import asyncio
from dataclasses import dataclass
from random import randint
from random import shuffle
from typing import TYPE_CHECKING

from loguru import logger

from alune import screen
from alune.adb import ADB
from alune.config import AluneConfig
from alune.images import BoundingBox
from alune.images import Button
from alune.images import Trait
from alune.vision.digit_ocr import DigitOCR

if TYPE_CHECKING:
    from alune.tft.planning.planning import TFTPlanning

DIGIT_OCR = DigitOCR()


class TFTEconomy:
    """
    Class to hold variables and methods relating to handling the TFT economy.
    """

    def __init__(self, adb_instance: ADB, alune_config: AluneConfig, planning_instance: "TFTPlanning"):
        self.adb = adb_instance
        self.config = alune_config
        self.planning = planning_instance

        self.last_level = 1
        self.last_gold = 0

    async def handle_economy(self):
        """
        Handles the economy decisions for the current round.
        """
        await self._click_store()

        gold = await self._get_gold()
        level = await self._get_level()
        is_low_level = level <= self.planning.low_level
        min_gold, buy_xp, xp_spend_ratio, _ = self.planning.configured_economy.get(level, (0, False, 1, 0))
        logger.debug(f"Economy strategy for level {level}: min_gold={min_gold}, buy_xp={buy_xp}")

        await self.buy_from_shop(is_low_level)

        spendable = max(0, gold - min_gold)

        xp_budget = 0
        if buy_xp:
            xp_budget = int(spendable * xp_spend_ratio)
            xp_budget -= xp_budget % self.planning.xp_cost
        else:
            if spendable >= self.planning.xp_cost and randint(1, 7) == 1:
                xp_budget = self.planning.xp_cost

        await self._click_store()
        for _ in range(xp_budget // self.planning.xp_cost):
            await self.buy_xp()

    async def rerolling(self):
        """
        Rerolls the shop with the remaining spendable monney
        """
        await self._click_store()
        await asyncio.sleep(0.1)
        level = await self._get_level()
        is_low_level = level <= self.planning.low_level
        min_gold, _, _, reroll_buffer = self.planning.configured_economy.get(level, (0, False, 1, 0))

        # Try re-buy desired units after bench was cleaned up
        await self.buy_from_shop(is_low_level)
        
        while await self._get_gold() - self.planning.reroll_cost - reroll_buffer >= min_gold:
            logger.debug("Rerolling shop within budget")
            await self._reroll_shop()
            await self.buy_from_shop(is_low_level)

        await self._click_store()

    @dataclass
    class NumberReadParams:
        """
        Parameters to read a bounded integer quickly from an ROI.
        """

        max_digits: int
        min_value: int
        max_value: int
        tries: int = 2
        delay_s: float = 0.1

    async def _read_number_fast(self, bbox: BoundingBox, params: NumberReadParams) -> int | None:
        last = None
        for i in range(params.tries):
            screenshot = await self.adb.get_screen()
            roi = screenshot[bbox.min_y : bbox.max_y, bbox.min_x : bbox.max_x]
            v = DIGIT_OCR.get_number_from_image(roi, max_digits=params.max_digits)
            last = v
            if v is not None and params.min_value <= v <= params.max_value:
                return v
            if params.delay_s and i < params.tries - 1:
                await asyncio.sleep(params.delay_s)
        return last

    async def _get_gold(self):
        gold_box = BoundingBox(1185, 622, 1234, 656)
        params = self.NumberReadParams(max_digits=2, min_value=0, max_value=100)
        gold = await self._read_number_fast(gold_box, params)
        logger.debug(f"Current gold: {gold}")

        if gold is None or gold > 100:
            return self.last_gold

        self.last_gold = gold
        return self.last_gold

    async def _get_level(self):
        level_box = BoundingBox(131, 664, 150, 688)
        params = self.NumberReadParams(max_digits=1, min_value=1, max_value=10)
        level = await self._read_number_fast(level_box, params)
        logger.debug(f"Current level: {level}")

        if level is None or not 1 <= level <= 10:
            return self.last_level

        self.last_level = level
        return self.last_level

    async def _click_store(self):
        await self.adb.click_button(Button.store_card)
        await asyncio.sleep(0.1)

    async def buy_xp(self):
        """
        Buys XP once.
        """
        screenshot = await self.adb.get_screen()
        can_buy_xp = screen.get_button_on_screen(screenshot, Button.buy_xp)
        if can_buy_xp:
            logger.debug("Buying XP")
            await self.adb.click_button(Button.buy_xp)
            await asyncio.sleep(0.1)

    async def _reroll_shop(self):
        logger.debug("Rerolling shop")
        await self.adb.click_button(Button.reroll)
        await asyncio.sleep(0.2)

    async def buy_from_shop(self, low_level: bool):
        """
        Checks the shop for traits and purchases it if found.
        """
        screenshot = await self.adb.get_screen()
        logger.debug("Buying from shop")

        # TODO: I don't know why, but self.config.get_traits() returns Trait.YORDLE as well as Trait.ARCANIST
        # altough the config is set to only Yordle ...
        trait_search = [Trait.YORDLE]  # self.config.get_traits()
        if low_level:
            trait_search.append(Trait.ARCANIST)

        # TODO: use favorite champions and 2-3 star indicators instead of traits
        for trait in trait_search:
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
            shuffle(store_cards)
            for search_result in search_results:
                for store_card in store_cards:
                    if not store_card.click_box.is_inside(search_result.get_middle()):
                        continue
                    logger.debug(f"Buying store card {Button.get_store_cards().index(store_card) + 1}")
                    await self.adb.click_button(store_card)
                    break

                await asyncio.sleep(0.1)
