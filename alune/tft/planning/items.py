"""
Module to handle all TFT item related interactions.
"""

import asyncio
from collections import Counter
import math
from random import choice
from random import uniform
from typing import TYPE_CHECKING

from loguru import logger

from alune import helpers
from alune import screen
from alune.adb import ADB
from alune.config import AluneConfig
from alune.images import BoundingBox
from alune.images import Button
from alune.images import Champion
from alune.images import Image
from alune.images import Item

if TYPE_CHECKING:
    from alune.tft.planning.planning import TFTPlanning


class TFTItems:
    """
    Class to hold variables and methods relating to handling the TFT items.
    """

    def __init__(self, adb_instance: ADB, alune_config: AluneConfig, planning_instance: "TFTPlanning"):
        self.adb = adb_instance
        self.config = alune_config
        self.planning = planning_instance

        self._drag_duration_ms = 400
        self._wait_after_drag_ms = 300
        self._keep_unknown_items_count = 0

    async def handle_items(self, field: list[list[Champion | None]]):
        """
        Handles the item placement for the current round.
        """
        await self.place_configured_items(field)
        await self.collect_dropped_items()

    async def _get_all_items(self):  # pylint: disable=too-many-locals
        await asyncio.sleep(0.2)
        screenshot = await self.adb.get_screen()
        is_items = screen.get_button_on_screen(screenshot, Button.items, 0.9)
        if not is_items:
            await self.adb.click_button(Button.items)
            await asyncio.sleep(0.3)
            screenshot = await self.adb.get_screen()

        items: list[Item] = []
        for rows in self.planning.item_coordinates:
            for coordinate in rows:
                cx, cy = coordinate
                item_box = BoundingBox(cx - 37, cy - 37, cx + 37, cy + 37)
                found_item = Item.UNKNOWN
                for item in Item:
                    if item is Item.UNKNOWN:
                        continue

                    result = screen.get_on_screen(screenshot, item, item_box, precision=0.9)
                    if result is not None:
                        found_item = item
                        break
                items.append(found_item)

        # TODO: detection of item/no-item is imperfect.
        # Cleanup trailing UNKNOWNs and only keep a limited amount.
        last_real_idx = None
        for i, it in enumerate(items):
            if it is not Item.UNKNOWN:
                last_real_idx = i

        start_none = (
            last_real_idx + 1 + self._keep_unknown_items_count
            if last_real_idx is not None
            else self._keep_unknown_items_count
        )

        del items[start_none:]

        return items

    def _check_champion_configured_position(self, champion: Champion, field: list[list[Champion | None]]):
        for r, row in enumerate(self.planning.configured_field):
            for c, configured_champ in enumerate(row):
                if configured_champ == champion and field[r][c] == champion:
                    return r, c
        return None

    def _get_first_item_match(self, wanted_item: Item, items: list[Item], skip_index: int = -1):
        for r, item in enumerate(items):
            if item == wanted_item and r != skip_index:
                return r
        return None

    async def _ensure_champion_is_on_field(self, expected_champion: Champion | None, x: int, y: int):
        await self.adb.click(x, y)
        await asyncio.sleep(0.1)
        screenshot = await self.adb.get_screen()
        is_champion = screen.get_on_screen(screenshot, Image.CHAMPION, self.planning.is_champion_box, precision=0.9)

        if expected_champion is None and is_champion:
            await self.adb.click(x, y)
            await asyncio.sleep(0.05)
            return True

        if is_champion:
            champion_found = screen.get_on_screen(
                screenshot, expected_champion, self.planning.champion_identifying_box, precision=0.9
            )
            if champion_found:
                await self.adb.click(x, y)
                await asyncio.sleep(0.05)
                return True

        await self.adb.click(x, y)
        await asyncio.sleep(0.05)
        return False

    async def _place_configured_items_on_champions_and_reserve(  # pylint: disable=too-many-locals
        self, items: list[Item], field: list[list[Champion | None]]
    ):
        item_counter = Counter(item for item in items)

        left_configurations = [
            config for config in self.planning.configured_items if config not in self.planning.crafted_items
        ]

        for config in left_configurations:
            champion, (first_item, second_item) = config

            found_champion = self._check_champion_configured_position(champion, field)
            if not found_champion:
                logger.debug("champion not found on field")
                item_counter[first_item] -= 1
                item_counter[second_item] -= 1
                continue

            if (first_item == second_item and item_counter[first_item] < 2) or (
                (item_counter[first_item] < 1) or (item_counter[second_item] < 1)
            ):
                logger.debug("not all items found")
                item_counter[first_item] -= 1
                item_counter[second_item] -= 1
                continue

            item_counter[first_item] -= 1
            item_counter[second_item] -= 1

            logger.debug(f"Placing items {first_item}, {second_item} on champion {champion}")
            first_item_index = self._get_first_item_match(first_item, items)
            second_item_index = self._get_first_item_match(second_item, items, first_item_index)

            if first_item_index is None or second_item_index is None:
                continue

            i1x, i1y = self.planning.item_coordinates[first_item_index // 5][first_item_index % 5]
            i2x, i2y = self.planning.item_coordinates[second_item_index // 5][second_item_index % 5]

            item_1 = BoundingBox(i1x - 2, i1y - 2, i1x + 2, i1y + 2)
            item_2 = BoundingBox(i2x - 2, i2y - 2, i2x + 2, i2y + 2)

            cx, cy = self.planning.field_coordinates[found_champion[0]][found_champion[1]]

            is_present = await self._ensure_champion_is_on_field(champion, cx, cy)
            if not is_present:
                logger.debug("champion not present on field after click, skipping item placement")
                continue

            for idx in sorted((first_item_index, second_item_index), reverse=True):
                items.pop(idx)

            self.planning.crafted_items.append(config)

            drag1 = item_2 if first_item_index < second_item_index else item_1
            drag2 = item_1 if drag1 is item_2 else item_2

            await self.adb.drag_and_drop(drag1, BoundingBox(cx - 2, cy - 2, cx + 2, cy + 2), self._drag_duration_ms)
            await asyncio.sleep(self._drag_duration_ms / 1000)
            await asyncio.sleep(self._wait_after_drag_ms / 1000)
            await self.adb.drag_and_drop(drag2, BoundingBox(cx - 2, cy - 2, cx + 2, cy + 2), self._drag_duration_ms)
            await asyncio.sleep(self._drag_duration_ms / 1000)
            await asyncio.sleep(self._wait_after_drag_ms / 1000)

        return item_counter, items

    async def _place_leftover_items_on_random_champions(  # pylint: disable=too-many-locals, too-many-branches
        self, item_counter: Counter[Item], items: list[Item], field: list[list[Champion | None]]
    ) -> None:
        possible_champions = []
        configured_item_champions = {champ for champ, _ in self.planning.configured_items}
        for r, row in enumerate(self.planning.configured_field):
            for c, configured_champ in enumerate(row):
                if (
                    configured_champ is not None
                    and configured_champ == field[r][c]
                    and configured_champ not in configured_item_champions
                ):
                    possible_champions.append((r, c))

        logger.debug(f"Possible champions: {possible_champions}")

        if not possible_champions:
            return

        row_count = len(self.planning.configured_field)
        split_row = row_count // 2

        front_candidates = [(r, c) for (r, c) in possible_champions if r < split_row]
        back_candidates = [(r, c) for (r, c) in possible_champions if r >= split_row]

        for item, count in item_counter.items():
            if count <= 0:
                continue

            if item in (Item.REFORGER, Item.MAGNETIC_REMOVER):
                continue

            is_frontline_item = self.planning.item_usage.get(item)

            logger.debug(f"Placing leftover item {item} x{count}")

            for _ in range(count):
                item_index = self._get_first_item_match(item, items)
                if item_index is None:
                    continue

                if is_frontline_item is True:
                    candidates = front_candidates
                elif is_frontline_item is False:
                    candidates = back_candidates
                else:
                    # on Item.UNKNOWN place randomly
                    candidates = possible_champions

                if not candidates:
                    break

                chosen_r, chosen_c = choice(candidates)
                cx, cy = self.planning.field_coordinates[chosen_r][chosen_c]

                is_present = await self._ensure_champion_is_on_field(None, cx, cy)
                if not is_present:
                    logger.debug("champion not present on field after click, skipping item placement")
                    continue

                items.pop(item_index)
                ix, iy = self.planning.item_coordinates[item_index // 5][item_index % 5]
                item_box = BoundingBox(
                    ix - 37,
                    iy - 37,
                    ix + 37,
                    iy + 37,
                )

                logger.debug(f"Placing leftover item {item} on champion at ({chosen_r}, {chosen_c})")
                await self.adb.drag_and_drop(
                    item_box, BoundingBox(cx - 2, cy - 2, cx + 2, cy + 2), self._drag_duration_ms
                )
                await asyncio.sleep(self._drag_duration_ms / 1000)
                await asyncio.sleep(self._wait_after_drag_ms / 1000)

    async def place_configured_items(self, field: list[list[Champion | None]]):
        """
        Places all configured items on the champions as per the configuration.
        """
        items = await self._get_all_items()
        logger.debug(f"All Items: {helpers.get_printable_item_version(items)}")

        item_counter, items = await self._place_configured_items_on_champions_and_reserve(items, field)
        await self._place_leftover_items_on_random_champions(item_counter, items, field)

    def _random_point_on_field_edge(
        self,
        top_left: tuple[int, int],
        top_right: tuple[int, int],
        bottom_right: tuple[int, int],
    ) -> tuple[int, int]:
        def dist(a, b):
            return math.hypot(b[0] - a[0], b[1] - a[1])

        def lerp(a, b, t):
            return (
                int(round(a[0] + t * (b[0] - a[0]))),
                int(round(a[1] + t * (b[1] - a[1]))),
            )

        # Segment lengths
        top_len = dist(top_left, top_right)
        right_len = dist(top_right, bottom_right)
        total_len = top_len + right_len

        # Choose segment proportional to length
        r = uniform(0, total_len)

        t = uniform(0, 1)
        if r < top_len:
            return lerp(top_left, top_right, t)
        return lerp(top_right, bottom_right, t)

    async def collect_dropped_items(self):
        """
        Collects all dropped items from the corners of the screen.
        """
        # TODO: i don't know how to implement this properly ... yet, so for now we just click on a random edge point (0)
        # 000
        # XX0
        # XX0

        ex, ey = self._random_point_on_field_edge(
            (350, 130),
            (990, 120),
            (1090, 530),
        )

        edge_box = BoundingBox(ex - 2, ey - 2, ex + 2, ey + 2)

        await self.adb.click_bounding_box(self.planning.default_position)
        await asyncio.sleep(0.02)
        await self.adb.click_bounding_box(edge_box)
