"""
Module for image recognition on the screen.
"""

from dataclasses import dataclass

import cv2
from cv2.typing import MatLike
from imutils.object_detection import non_max_suppression
from loguru import logger
import numpy
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


def get_image_from_path(path: str) -> MatLike | None:
    """
    Get an image at a path.

    Args:
        path: The relative or absolute path to the image to be found.

    Returns:
        The image or none if it does not exist.
    """
    image_to_find = cv2.imread(path, 0)

    if image_to_find is None:
        logger.warning(f"The image {path} does not exist on the system, or we do not have permission to read it.")
        return None

    return image_to_find


def get_match_template(
    image: ndarray,
    image_to_find: MatLike,
    bounding_box: BoundingBox | None = None,
) -> ndarray:
    """
    Searches an image for an image to find with an optional bounding box.

    Args:
        image: The image we should look at.
        image_to_find: The image we should find.
        bounding_box: The bounding box to cut the image down to
            or none for the full image. Defaults to none.

    Returns:
        A numpy array with all matched results.
    """
    crop = image
    if bounding_box:
        crop = image[
            bounding_box.min_y : bounding_box.max_y,
            bounding_box.min_x : bounding_box.max_x,
        ]

    return cv2.matchTemplate(crop, image_to_find, cv2.TM_CCOEFF_NORMED)


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
    image_to_find = get_image_from_path(path)
    if image_to_find is None:
        return None

    search_result = get_match_template(image=image, image_to_find=image_to_find, bounding_box=bounding_box)

    _, max_precision, _, max_location = cv2.minMaxLoc(search_result)
    if max_precision < precision:
        return None

    return ImageSearchResult(
        x=max_location[0] + (bounding_box.min_x if bounding_box else 0),
        y=max_location[1] + (bounding_box.min_y if bounding_box else 0),
        height=image_to_find.shape[0],
        width=image_to_find.shape[1],
    )


def get_all_on_screen(
    image: ndarray,
    path: str,
    bounding_box: BoundingBox | None = None,
    precision: float = 0.9,
) -> list[ImageSearchResult]:
    """
    Check if a given image is detected on screen in a specific window's area.

    Args:
        image: The image we should look at.
        path: The relative or absolute path to the image to be found.
        bounding_box: The bounding box to cut the image down to
            or none for the full image. Defaults to none.
        precision: The precision to be used when matching the image. Defaults to 0.9.

    Returns:
        All positions of the image and their width and height
    """
    image_to_find = get_image_from_path(path)
    if image_to_find is None:
        return []

    search_result = get_match_template(image=image, image_to_find=image_to_find, bounding_box=bounding_box)

    (y_coordinates, x_coordinates) = numpy.where(search_result >= precision)
    to_find_height, to_find_width = image_to_find.shape[:2]
    matches = []

    for x, y in zip(x_coordinates, y_coordinates):
        matches.append((x, y, x + to_find_width, y + to_find_height))
    matches_without_duplicates = non_max_suppression(numpy.array(matches))

    image_search_results = []
    offset_x = bounding_box.min_x if bounding_box else 0
    offset_y = bounding_box.min_y if bounding_box else 0
    for min_x, min_y, max_x, max_y in matches_without_duplicates:
        image_search_results.append(
            ImageSearchResult(
                x=min_x + offset_x,
                y=min_y + offset_y,
                width=to_find_width,
                height=to_find_height,
            )
        )

    return image_search_results
