from dataclasses import dataclass
from random import Random

import cv2
from numpy import ndarray


@dataclass
class Coordinate:
    """
    Class to represent a coordinate on the screen.
    """

    x: int
    y: int

    def clone(self):
        """
        Get a clone of the coordinate, safe for modification.

        Returns:
            The cloned coordinate.
        """
        return Coordinate(x=self.x, y=self.y)

    def add(self, x: int, y: int):
        """
        Add the given values to the current coordinates.

        Returns:
             The modified coordinate object.
        """
        self.x += x
        self.y += y
        return self


@dataclass
class BoundingBox:
    """
    A dataclass holding information about a bounding box,
    a rectangle of two coordinate sets.
    """

    min_x: int
    min_y: int
    max_x: int
    max_y: int

    def to_tuple(self) -> tuple[int, int, int, int]:
        """
        Converts the bounding box to a tuple.

        Returns:
            A tuple, ordered min_x, min_y, max_x, max_y.

        """
        return self.min_x, self.min_y, self.max_x, self.max_y

    def get_width(self) -> int:
        """
        Get the width of the bounding box.

        Returns:
            The width as an integer.
        """
        return self.max_x - self.min_x

    def get_height(self) -> int:
        """
        Get the height of the bounding box.

        Returns:
            The height as an integer.
        """
        return self.max_y - self.min_y

    def get_random_point(self, random: Random) -> Coordinate:
        """
        Get a random point within this bounding box.

        Args:
            random: An instance of Random to be used.

        Returns:
            A random coordinate within the bounding box.
        """
        return Coordinate(random.randint(self.min_x, self.max_x), random.randint(self.min_y, self.max_y))


@dataclass
class ImageSearchResult(Coordinate):
    """
    A dataclass holding information about an image search result.
    """

    width: int
    height: int

    def get_middle(self):
        return Coordinate(self.x + (self.width // 2), self.y + (self.height // 2))


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
        print(
            f"The image {path} does not exist on the system "
            f"or we do not have permission to read it."
        )
        return None

    crop = image
    if bounding_box:
        crop = image[
            bounding_box.min_y: bounding_box.max_y, bounding_box.min_x: bounding_box.max_x
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
