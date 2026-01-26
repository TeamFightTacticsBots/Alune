"""
Collection of helper methods.
"""

import asyncio
from pathlib import Path
import sys
from time import sleep
from typing import TYPE_CHECKING

import cv2
from loguru import logger
import numpy
from numpy import ndarray

if TYPE_CHECKING:
    from alune import screen
    from alune.adb import ADB
    from alune.images import Button


def get_application_path(relative_path: str | None = None) -> str:
    """
    Gets the path the application is being run from.
    For the python version, this will be the project folder.
    For the executable, this will be the folder it is in.
    Use this for config & logs.

    Args:
        relative_path: An optional relative path that will get added to the result.

    Returns:
         An absolute version of the application path.
    """
    # '_MEIPASS' is set by pyinstaller
    if hasattr(sys, "_MEIPASS"):
        path = Path(sys.executable).parent.absolute()
    else:
        path = Path(__file__).parent.parent.absolute()

    if relative_path:
        return str(path / relative_path)

    return str(path)


def get_resource_path(relative_path: str | None = None):
    """
    Gets the path image resources are at.
    For the python version, this will be the project folder.
    For the executable, this will be a folder that's created in %APPDATA%.
    Use this for images.

    Args:
        relative_path: An optional relative path that will get added to the result.

    Returns:
        An absolute version of the resource path.
    """
    if hasattr(sys, "_MEIPASS"):
        path = Path(getattr(sys, "_MEIPASS")).absolute()
    else:
        path = Path(__file__).parent.parent.absolute()

    if relative_path:
        return str(path / relative_path)

    return str(path)


def is_version_string_newer(version_one: str, version_two: str, ignore_minor_mismatch: bool = False):
    """
    Checks if version_one is newer than version_two.

    Args:
        version_one: The semantic version string to check.
        version_two: The semantic version string to check against.
        ignore_minor_mismatch: Optional, whether to ignore that the minor version mismatches. Defaults to false.

    Returns:
        Whether version_one is newer than version_two.
    """
    version_one_parts = version_one.split(".")
    version_two_parts = version_two.split(".")
    version_part_amount = min(len(version_one_parts), len(version_two_parts))

    for i in range(version_part_amount):
        try:
            if int(version_one_parts[i]) <= int(version_two_parts[i]):
                continue

            if ignore_minor_mismatch and i == version_part_amount - 1:
                logger.warning("There is a newer minor version of TFT available. Please update as soon as possible.")
                return False

            return True
        except ValueError:
            logger.warning(
                f"We could not check version {version_one} against {version_two}. "
                f"Assuming the installed version ({version_two}) is newer."
            )
            return False
    return False


def raise_and_exit(error: str, exit_code: int = 1) -> None:
    """
    Raise the given text as an error and then exit the application

    Args:
        error: The image we should look at.
        exit_code: The relative or absolute path to the image to be found. Defaults to 1.
    """
    logger.error(error)
    logger.warning("Due to an error, we are exiting Alune in 10 seconds. You can find all logs in alune-output/logs.")
    sleep(10)
    sys.exit(exit_code)


async def choose_one_if_visible(adb: "ADB", screen: "screen", button: "Button") -> bool:
    """
    If a 'choose one' offer is visible, click through it.

    Returns:
        True if an offer was handled.
    """
    screenshot = await adb.get_screen()

    is_choose_one_hidden = screen.get_button_on_screen(screenshot, button.choose_one_hidden, precision=0.9)
    if is_choose_one_hidden:
        logger.debug("Choose one is hidden, clicking it to show offers")
        await adb.click_button(button.choose_one_hidden)
        await asyncio.sleep(0.3)
        screenshot = await adb.get_screen()

    is_choose_one_active = screen.get_button_on_screen(screenshot, button.choose_one, precision=0.9)
    if is_choose_one_active:
        logger.debug("Choosing from an item or a choice offer")
        await adb.click_button(button.choose_one)
        await asyncio.sleep(0.1)
        return True

    return False


def get_line_center_points_based_on_edges(x_left: int, x_right: int, y: int, count: int):
    """
    Creates 'count' evenly spaced centers from left to right (inclusive endpoints).
    For TFT: endpoints are centers of first and last cell in that row.
    """
    if count < 2:
        return [(x_left, y)]

    step = (x_right - x_left) / (count - 1)
    return [(int(round(x_left + i * step)), y) for i in range(count)]


def get_row_center_points_based_on_edges(x: int, y_top: int, y_bottom: int, count: int):
    """
    Creates 'count' evenly spaced centers from top to bottom (inclusive endpoints).
    For TFT: endpoints are centers of first and last cell in that row.
    """
    if count < 2:
        return [(x, y_top)]

    step = (y_bottom - y_top) / (count - 1)
    return [(x, int(round(y_top + i * step))) for i in range(count)]


def _clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))


def get_roi_from_coordinate(img: ndarray, cx: int, cy: int, half: int):
    """
    Gets a square ROI from the given center coordinate.
    """
    h, w = img.shape[:2]
    x0 = _clamp(cx - half, 0, w - 1)
    x1 = _clamp(cx + half, 0, w)
    y0 = _clamp(cy - half, 0, h - 1)
    y1 = _clamp(cy + half, 0, h)
    return img[y0:y1, x0:x1]


def get_presence_score(now_roi: ndarray, empty_roi: ndarray):
    """
    Gets a presence score between two ROIs.
    """
    now_blur = cv2.GaussianBlur(now_roi, (3, 3), 0)
    empty_blur = cv2.GaussianBlur(empty_roi, (3, 3), 0)

    diff = cv2.absdiff(now_blur, empty_blur)
    return float(numpy.mean(diff))


def get_printable_champion_version(bench, field):
    """
    Converts the given bench and field champion objects into their printable names.
    """
    return (
        [champ.name if champ else None for champ in bench],
        [[champ.name if champ else None for champ in row] for row in field],
    )


def get_printable_item_version(items):
    """
    Converts the given item objects into their printable names.
    """
    return ([item.name if item else None for item in items],)
