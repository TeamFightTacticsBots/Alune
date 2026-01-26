"""
Module to handle all TFT planning phase related interactions.
"""

import asyncio
from random import Random

import cv2
from loguru import logger
from numpy import ndarray

from alune import helpers
from alune import screen
from alune.adb import ADB
from alune.config import AluneConfig
from alune.images import BoundingBox
from alune.images import Button
from alune.images import Champion
from alune.images import Image
from alune.images import Item


class TFTPlanning:
    """
    Class to hold variables and methods relating to handling the TFT planning phase.
    """

    def __init__(self, adb_instance: ADB, alune_config: AluneConfig):
        self.adb = adb_instance
        self.config = alune_config

        self.random = Random()

        self._xp_cost = 4
        self._reroll_cost = 2

        self._champion_identifying_box = BoundingBox(1200, 0, 1279, 30)
        self._is_champion_box = BoundingBox(1200, 300, 1269, 334)
        self._empty_compare_field = cv2.imread(str(Image.FIELD), cv2.IMREAD_GRAYSCALE)

        self._champion_detection_roi_half_size = 8  # ROI is (2*half) x (2*half) => 16x16
        self._champion_presence_threshold = 12.0  # mean abs diff threshold
        self._champion_detection_height_offset = -30  # offset to middle of champion place area

        self._field_rows = [
            (360, 920, 350),
            (400, 980, 410),
            (335, 945, 475),
            (375, 1010, 545),
        ]
        self._field_coordinates: list[list[tuple[int, int]]] = []
        for row in self._field_rows:
            self._field_coordinates.append(
                helpers.get_line_center_points_based_on_edges(
                    row[0],
                    row[1],
                    row[2] + self._champion_detection_height_offset,
                    7,
                )
            )

        self._last_field: list[list[Champion | None]] = []
        for rows in self._field_coordinates:
            row: list[bool] = []
            for _ in rows:
                row.append(None)
            self._last_field.append(row)

        self._bench_row = (245, 1030, 645)
        self._bench_coordinates = helpers.get_line_center_points_based_on_edges(
            self._bench_row[0],
            self._bench_row[1],
            self._bench_row[2] + self._champion_detection_height_offset,
            9,
        )

        self._item_rows = [
            (50, 134, 443),
            (132, 134, 443),
        ]
        self._item_coordinates: list[list[tuple[int, int]]] = []
        for row in self._item_rows:
            self._item_coordinates.append(
                helpers.get_row_center_points_based_on_edges(
                    row[0],
                    row[1],
                    row[2],
                    5,
                )
            )

        self._configured_field: list[list[Champion | None]] = [
            [None, None, Champion.KOBUKO_YUUMI, Champion.RUMBLE, Champion.KENNEN, Champion.POPPY, None],
            [None, Champion.FIZZ, None, None, None, None, None],
            [None, None, None, None, None, None, None],
            [Champion.TEEMO, None, Champion.ZIGGS, None, Champion.LULU, None, Champion.TRISTANA],
        ]

        self._crafted_items: list[tuple[Champion, tuple[Item, Item]]] = (
            []
        )  # needed to track crafted items this game (resets each game)
        self._configured_items: list[tuple[Champion, tuple[Item, Item]]] = [
            (Champion.TEEMO, (Item.NEEDLESSLY_LARGE_ROD, Item.GIANTS_BELT)),
            (Champion.TEEMO, (Item.TEAR_OF_THE_GODDESS, Item.NEGATRON_CLOAK)),
            (Champion.TEEMO, (Item.TEAR_OF_THE_GODDESS, Item.RECURVE_BOW)),
            (Champion.KENNEN, (Item.GIANTS_BELT, Item.GIANTS_BELT)),
            (Champion.KENNEN, (Item.NEGATRON_CLOAK, Item.NEGATRON_CLOAK)),
            (Champion.KENNEN, (Item.CHAIN_VEST, Item.CHAIN_VEST)),
        ]

        self._item_usage: dict[Item, bool] = {
            # frontline first
            Item.GIANTS_BELT: True,
            Item.NEGATRON_CLOAK: True,
            Item.CHAIN_VEST: True,
            # backline after
            Item.NEEDLESSLY_LARGE_ROD: False,
            Item.TEAR_OF_THE_GODDESS: False,
            Item.RECURVE_BOW: False,
            Item.SPARRING_GLOVES: False,
            Item.BF_SWORD: False,
        }

        # level: (min_gold_to_keep, buy_xp, xp_spend_ratio, reroll_buffer)
        self._configured_economy: dict[int, tuple[int, bool, float, int]] = {
            1: (0, False, 0.0, 0),
            2: (0, False, 0.0, 1),
            3: (0, True, 1, 2),
            4: (10, True, 0.6, 2),
            5: (20, True, 0.6, 3),
            6: (50, False, 0.0, 3),
            7: (30, True, 0.70, 2),
            8: (20, True, 0.80, 0),
            9: (0, True, 0.90, 0),
            10: (0, False, 0.0, 0),
        }

        self._default_position: BoundingBox = BoundingBox(170, 490, 200, 540)

        from alune.tft.planning.economy import TFTEconomy

        self.economy = TFTEconomy(adb_instance, alune_config, self)

        from alune.tft.planning.placing import TFTPlacing

        self.placing = TFTPlacing(adb_instance, alune_config, self)

        from alune.tft.planning.items import TFTItems

        self.items = TFTItems(adb_instance, alune_config, self)

    async def planning_phase(self):
        """
        Actions to take during the planning phase.
        """
        screenshot = await self.adb.get_screen()
        is_planning_phase = screen.get_button_on_screen(screenshot, Button.buy_xp) or screen.get_button_on_screen(
            screenshot, Button.buy_xp_disabled
        )
        if is_planning_phase is None:
            return

        await self.move_to_default_positions()

        await self.economy.handle_economy()

        bench, field = await self.get_champions()
        await self.placing.handle_placing(bench, field)
        self._last_field = field

        await self.items.handle_items(field)

        await self.economy.rerolling()

    def reset_planning(self):
        """
        Resets the planning state for a new game.
        """
        self._crafted_items = []

    async def move_to_default_positions(self):
        """
        Move to the default position to have a good view of the board and bench.
        """
        await self.adb.click_bounding_box(self._default_position)
        await self.adb.click_bounding_box(self._default_position)

    def _scan_for_champions(self, screenshot: ndarray):
        empty = self._empty_compare_field
        half = self._champion_detection_roi_half_size
        threshold = self._champion_presence_threshold

        field: list[list[bool]] = []
        for rows in self._field_coordinates:
            row: list[bool] = []
            for cx, cy in rows:
                now_roi = helpers.get_roi_from_coordinate(screenshot, cx, cy, half)
                empty_roi = helpers.get_roi_from_coordinate(empty, cx, cy, half)
                score = helpers.get_presence_score(now_roi, empty_roi)
                row.append(score > threshold)

            field.append(row)

        bench: list[bool] = []
        for cx, cy in self._bench_coordinates:
            now_roi = helpers.get_roi_from_coordinate(screenshot, cx, cy, half)
            empty_roi = helpers.get_roi_from_coordinate(empty, cx, cy, half)
            score = helpers.get_presence_score(now_roi, empty_roi)
            bench.append(score > threshold)

        return bench, field

    async def _check_for_champion_at_position(self, x: int, y: int, is_bench: bool = False):
        """
        Checks if a champion is present and if so return the actual champion | unknown champion | none
        """
        logger.debug(f"Check for champion at ({x}, {y})")
        await self.adb.click(x, y)

        screenshot = await self.adb.get_screen()
        is_champion = screen.get_on_screen(screenshot, Image.CHAMPION, self._is_champion_box, precision=0.9)

        champion_result: Champion | None = None

        if is_champion:
            logger.debug("Is champion")

            for champion in Champion:
                if champion is Champion.UNKNOWN:
                    continue

                champion_found = screen.get_on_screen(
                    screenshot, champion, self._champion_identifying_box, precision=0.9
                )
                if champion_found:
                    logger.debug(f"Champion is: {champion.name}")
                    champion_result = champion
                    break

            if champion_result is None:
                logger.debug("Champion present but not recognized")
                champion_result = Champion.UNKNOWN
        else:
            logger.debug("No champion")
            if is_bench:
                await self.placing.sell_champion_at_coordinates(x, y)
                await asyncio.sleep(0.2)
                screenshot = await self.adb.get_screen()
                is_choose_one_active = screen.get_button_on_screen(screenshot, Button.choose_one, precision=0.9)
                if is_choose_one_active:
                    logger.debug("Choosing from an item or a choice offer")
                    await self.adb.click_button(Button.choose_one)
                    await asyncio.sleep(0.1)

        await self.adb.click(x, y)
        return champion_result

    async def _identify_scanned_champions(
        self,
        bench_mask: list[bool],
        field_mask: list[list[bool]],
    ):
        """
        Returns detected champions on bench and board.
        Champion.UNKNOWN means Champ detected but not recognized.
        `None` means empty.
        """
        bench_result: list[Champion | None] = [None] * len(self._bench_coordinates)
        field_result: list[list[Champion | None]] = [
            [None for _ in range(len(self._field_coordinates[0]))] for _ in range(len(self._field_coordinates))
        ]

        for i, is_possibly_a_champion in enumerate(bench_mask):
            if not is_possibly_a_champion:
                continue

            cx, cy = self._bench_coordinates[i]
            bench_result[i] = await self._check_for_champion_at_position(cx, cy, True)

        for r, row in enumerate(self._field_coordinates):
            for c, (cx, cy) in enumerate(row):
                if not field_mask[r][c]:
                    continue

                last_known_champion = self._last_field[r][c]
                if last_known_champion is not None and last_known_champion is not Champion.UNKNOWN:
                    field_result[r][c] = last_known_champion
                    continue

                field_result[r][c] = await self._check_for_champion_at_position(cx, cy)

        return bench_result, field_result

    async def get_champions(self):
        """
        Get the current champions on bench and field.
        """
        screenshot = await self.adb.get_screen()

        bench_scan, field_scan = self._scan_for_champions(screenshot)
        logger.debug("Bench:")
        logger.debug(f"  {bench_scan}")
        logger.debug("field:")
        for row_scan in field_scan:
            logger.debug(f"  {row_scan}")

        bench_identified, field_identified = await self._identify_scanned_champions(bench_scan, field_scan)
        printable_bench, printable_field = helpers.get_printable_champion_version(bench_identified, field_identified)
        logger.debug("After getting champions")
        logger.debug("Bench: ")
        logger.debug(f"  {printable_bench}")
        logger.debug("field:")
        for printable_row in printable_field:
            logger.debug(f"  {printable_row}")

        return (bench_identified, field_identified)
