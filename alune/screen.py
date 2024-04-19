"""
Module for image recognition on the screen.
"""

from dataclasses import dataclass

import cv2
from loguru import logger
from numpy import ndarray

from alune.images import BoundingBox
from alune.images import Coordinate
from alune.images import ImageButton


@dataclass
class ImageSearchResult(Coordinate):
    """
    A dataclass holding information about an image search result.
    """

    width: int
    height: int

    def get_middle(self):
        """
        Get the middle of the image.
        """
        return Coordinate(self.x + (self.width // 2), self.y + (self.height // 2))


def get_button_on_screen(
    image: ndarray,
    button: ImageButton,
    precision: float = 0.8,
) -> ImageSearchResult | None:
    """
    Check if a given image is detected on screen in a specific window's area.

    Args:
        image: The image we should look at.
        button: The relative or absolute path to the image to be found.
        precision: The precision to be used when matching the image. Defaults to 0.9.

    Returns:
        The position of the image and it's width and height or None if it wasn't found
    """
    return get_on_screen(image, button.image_path, button.capture_area, precision)


def get_on_screen(
    image: ndarray,
    path: str,
    bounding_box: BoundingBox | None = None,
    precision: float = 0.8,
) -> ImageSearchResult | None:
    """
    Check if a given image is detected on screen in a specific window's area.

    Args:
        image: The image we should look at.
        path: The relative or absolute path to the image to be found.
        bounding_box: The bounding box to cut the image down to
            or none for the full image. Defaults to none.
        precision: The precision to be used when matching the image. Defaults to 0.9.

    Returns:
        The position of the image and it's width and height or None if it wasn't found
    """
    image_to_find = cv2.imread(path, 0)
    if image_to_find is None:
        logger.warning(f"The image {path} does not exist on the system " f"or we do not have permission to read it.")
        return None

    crop = image
    if bounding_box:
        crop = image[
            bounding_box.min_y : bounding_box.max_y,
            bounding_box.min_x : bounding_box.max_x,
        ]

    search_result = cv2.matchTemplate(crop, image_to_find, cv2.TM_CCOEFF_NORMED)

    _, max_precision, _, max_location = cv2.minMaxLoc(search_result)
    if max_precision < precision:
        return None

    return ImageSearchResult(
        x=max_location[0] + bounding_box.min_x if bounding_box else 0,
        y=max_location[1] + bounding_box.min_y if bounding_box else 0,
        height=image_to_find.shape[0],
        width=image_to_find.shape[1],
    )
