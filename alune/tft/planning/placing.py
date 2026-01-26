"""
Module to handle all TFT placing related interactions.
"""

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from alune.adb import ADB
from alune.config import AluneConfig
from alune.images import BoundingBox
from alune.images import Button
from alune.images import Champion

if TYPE_CHECKING:
    from alune.tft.planning.planning import TFTPlanning


class TFTPlacing:
    """
    Class to hold variables and methods relating to handling the TFT placing.
    """

    def __init__(self, adb_instance: ADB, alune_config: AluneConfig, planning_instance: "TFTPlanning"):
        self.adb = adb_instance
        self.config = alune_config
        self.planning = planning_instance
        self._drag_duration_ms = 400

    async def handle_placing(self, bench: list[Champion | None], field: list[list[Champion | None]]):
        """
        Handles the placing of champions on the field and bench according to configuration.
        """
        field_sold_count = await self.sell_unwanted_champions(bench, field)
        await self.place_configured_champions(field_sold_count, bench, field)

    def _is_configured_champion(self, champion: Champion | None):
        # TODO later when all Champs are defined treat UNKNOWN properly
        if champion is Champion.UNKNOWN:
            return False
        for row in self.planning.configured_field:
            if champion in row:
                return True
        return False

    async def sell_champion_at_coordinates(self, x: int, y: int):
        """
        Sells a champion at the given coordinates.
        """
        logger.debug(f"Selling champion at coordinates ({x}, {y})")
        grab = BoundingBox(x - 2, y - 2, x + 2, y + 2)
        await self.adb.drag_and_drop(grab, Button.sell.click_box, self._drag_duration_ms)
        await asyncio.sleep(self._drag_duration_ms / 1000)

    async def sell_unwanted_champions(self, bench: list[Champion | None], field: list[list[Champion | None]]):
        """
        Sells champions that are not part of the configured comp, if overcapacity.
        """
        bench_count = sum(1 for champ in bench if champ is not None)
        sell_unknowns = bench_count - 1
        logger.debug(f"Bench count: {bench_count}, will sell {sell_unknowns} unwanted champions if any.")
        field_sold_count: int = 0

        if sell_unknowns <= 0:
            return field_sold_count

        for i, champ in enumerate(bench):
            if champ is not None and self._is_configured_champion(champ) is False:
                logger.debug(f"Selling unwanted from bench[{i}].")
                x, y = self.planning.bench_coordinates[i]
                await self.sell_champion_at_coordinates(x, y)
                bench[i] = None
                sell_unknowns -= 1
                if sell_unknowns <= 0:
                    break

        if sell_unknowns <= 0:
            return field_sold_count

        for r, row in enumerate(field):
            for c, champ in enumerate(row):
                if champ is not None and self._is_configured_champion(champ) is False:
                    logger.debug(f"Selling unwanted from field[{r}][{c}].")
                    x, y = self.planning.field_coordinates[r][c]
                    await self.sell_champion_at_coordinates(x, y)
                    field[r][c] = None
                    sell_unknowns -= 1
                    field_sold_count += 1
                    if sell_unknowns <= 0:
                        return field_sold_count

        return field_sold_count

    def _get_configured_lookup(self):
        desired_pos: dict[Champion, tuple[int, int]] = {}
        for r, row in enumerate(self.planning.configured_field):
            for c, configured_champ in enumerate(row):
                if configured_champ is None:
                    continue

                desired_pos[configured_champ] = (r, c)

        return desired_pos

    async def _place_from_coordinate_to_coordinate(self, fx: int, fy: int, tx: int, ty: int):
        logger.debug(f"Moving champion from ({fx}, {fy}) to ({tx}, {ty})")
        grab = BoundingBox(fx - 2, fy - 2, fx + 2, fy + 2)
        release = BoundingBox(tx - 2, ty - 2, tx + 2, ty + 2)
        await self.adb.drag_and_drop(grab, release, self._drag_duration_ms)
        await asyncio.sleep(self._drag_duration_ms / 1000)

    async def _place_on_last_free_bench_slot(self, champion: Champion, x: int, y: int, bench: list[Champion | None]):
        for i in range(len(bench) - 1, -1, -1):
            if bench[i] is None:
                bx, by = self.planning.bench_coordinates[i]
                await self._place_from_coordinate_to_coordinate(x, y, bx, by)
                bench[i] = champion
                return True
        return False

    async def _arrange_field_to_configured(
        self,
        configured_lookup: dict[Champion, tuple[int, int]],
        bench: list[Champion | None],
        field: list[list[Champion | None]],
    ):
        benched_count = 0

        for r, row in enumerate(field):
            for c, champion in enumerate(row):
                if champion is None:
                    continue

                ox, oy = self.planning.field_coordinates[r][c]

                if champion not in configured_lookup:
                    if await self._place_on_last_free_bench_slot(champion, ox, oy, bench):
                        field[r][c] = None
                        benched_count += 1
                    continue

                # Champion is in configuration
                target_r, target_c = configured_lookup[champion]
                tx, ty = self.planning.field_coordinates[target_r][target_c]

                if field[target_r][target_c] is None:
                    await self._place_from_coordinate_to_coordinate(ox, oy, tx, ty)
                    field[target_r][target_c] = champion
                    field[r][c] = None
                    continue
                if field[target_r][target_c] is champion:
                    if target_r != r or target_c != c:
                        await self._place_on_last_free_bench_slot(champion, ox, oy, bench)
                        field[r][c] = None
                        benched_count += 1
                    continue

                # This isn't ideal, but in the next cycle it fixes itself
                await self._place_from_coordinate_to_coordinate(ox, oy, tx, ty)
                field[r][c] = field[target_r][target_c]
                field[target_r][target_c] = champion

        return benched_count

    def _find_champ_on_bench(self, champ: Champion, bench) -> int | None:
        for i, ch in enumerate(bench):
            if ch == champ:
                return i
        return None

    async def _arrange_bench_to_field_configured(
        self,
        configured_lookup: dict[Champion, tuple[int, int]],
        benched_count: int,
        bench: list[Champion | None],
        field: list[list[Champion | None]],
    ):
        for champ, (r, c) in configured_lookup.items():
            if field[r][c] == champ:
                continue

            bi = self._find_champ_on_bench(champ, bench)
            if bi is None:
                continue

            bx, by = self.planning.bench_coordinates[bi]
            tx, ty = self.planning.field_coordinates[r][c]

            if field[r][c] is None and benched_count > 0:
                await self._place_from_coordinate_to_coordinate(bx, by, tx, ty)
                bench[bi] = None
                field[r][c] = champ
                benched_count -= 1
                continue

            if field[r][c] is not None:
                await self._place_from_coordinate_to_coordinate(bx, by, tx, ty)
                bench[bi] = field[r][c]
                field[r][c] = champ
                continue

        return benched_count

    def _get_best_fitting_champion_for_bench_slot(
        self, used_best_champions: list[Champion], bench: list[Champion | None], field: list[list[Champion | None]]
    ):
        for bi, champ in enumerate(bench):
            if champ is None:
                continue
            if champ not in [ch for row in field for ch in row if ch is not None] and champ not in used_best_champions:
                return bi, champ
        return None

    async def _arrange_bench_to_best_configured(
        self, rest_benched_count: int, bench: list[Champion | None], field: list[list[Champion | None]]
    ):
        used_best_champions = []
        for bc in range(rest_benched_count):
            best_champ = self._get_best_fitting_champion_for_bench_slot(used_best_champions, bench, field)

            if best_champ is None:
                break

            bi, champ = best_champ
            used_best_champions.append(champ)
            bx, by = self.planning.bench_coordinates[bi]
            tx, ty = self.planning.bench_coordinates[bc]
            await self._place_from_coordinate_to_coordinate(bx, by, tx, ty)
            bench[bi] = bench[bc]
            bench[bc] = champ

    async def place_configured_champions(
        self, field_sold_count: int, bench: list[Champion | None], field: list[list[Champion | None]]
    ):
        """
        Places/rearranges configured champions while respecting constraints:
        - Never sells here
        - Never increases the number of units on field more than initial
        - Rearranges configured champs already on field to their configured hex
        - If configured champ is on bench and its configured hex is occupied (by another), swap it in
        - Puts the next missing configured champ into bench[0] (if available on bench)
        """
        configured_lookup = self._get_configured_lookup()

        benched_count = await self._arrange_field_to_configured(configured_lookup, bench, field)
        rest_benched_count = await self._arrange_bench_to_field_configured(
            configured_lookup, benched_count + field_sold_count, bench, field
        )

        # we do this because we could've leveled up, so more champs fit on bench now
        rest_benched_count += 1
        rest_benched_count = min(rest_benched_count, len(bench))

        await self._arrange_bench_to_best_configured(rest_benched_count, bench, field)
