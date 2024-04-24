"""
Module to handle anything related to images and buttons (images that result in a click) we use.
"""

from dataclasses import dataclass
from enum import auto
from enum import StrEnum
from random import Random

from alune import helpers


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
        return Coordinate(
            random.randint(self.min_x, self.max_x),
            random.randint(self.min_y, self.max_y),
        )

    def is_inside(self, coordinate: Coordinate) -> bool:
        """
        Check if a coordinate is inside this bounding box.

        Args:
             coordinate: The coordinate to check.

        Returns:
            Whether the coordinate is inside this bounding box.
        """
        return self.min_x <= coordinate.x <= self.max_x and self.min_y <= coordinate.y <= self.max_y


class Image(StrEnum):
    """
    An image enum which holds the path to the image as a value.
    """

    # noinspection PyMethodParameters
    # pylint: disable-next=no-self-argument,redefined-outer-name
    def _generate_next_value_(name, start, count, last_values):
        """
        The effective method called by auto().

        Args:
            name: The name of the enum key.
            start: Not used in StrEnum.
            count: Not used in StrEnum.
            last_values: Not used in StrEnum.

        Returns:
            The value that the key should have.
        """
        return helpers.get_resource_path(f"alune/images/{name.lower()}.png")

    RITO_LOGO = auto()
    CLOSE_LOBBY = auto()
    ACCEPTED = auto()
    COMPOSITION = auto()
    ITEMS = auto()
    FIRST_PLACE = auto()
    BACK = auto()
    SETTINGS = auto()
    PICK_AUGMENT = auto()
    CAROUSEL = auto()


class Trait(StrEnum):
    """
    The same as ImageEnum, but images are intentionally in a different place and will
    change with each set.
    """

    # noinspection PyMethodParameters
    # pylint: disable-next=no-self-argument,redefined-outer-name
    def _generate_next_value_(name, start, count, last_values):
        return helpers.get_resource_path(f"alune/images/traits/{name.lower()}.png")

    HEAVENLY = auto()


class ClickButton:  # pylint: disable=too-few-public-methods
    """
    A button which can and will be clicked.
    """

    def __init__(self, click_box: BoundingBox):
        """
        Create a ClickButton.

        Args:
             click_box: The bounding box in which the button can be clicked.
        """
        self.click_box = click_box


class ImageButton:  # pylint: disable=too-few-public-methods
    """
    A button which can and will be clicked, which also holds an Image the button is
    recognized by.
    """

    def __init__(self, click_box: BoundingBox, capture_area: BoundingBox | None = None):
        """
        Create an ImageButton.

        Args:
            click_box: The bounding box in which the button can be clicked.
            capture_area: An optional area that limits in which we recognize the button.
        """
        self.click_box = click_box
        self.capture_area = capture_area
        self.image_path = None

    def set_image_path(self, button_name: str):
        """
        Sets the path to the image. Set automatically on module load of images.py.

        Args:
            button_name: The file name of the button, without extension.
        """
        self.image_path = helpers.get_resource_path(f"alune/images/buttons/{button_name}.png")


@dataclass
class Button:
    """
    Class which holds all buttons the bot recognizes and clicks.
    """

    # Buttons with an image, the variable name must be the same as the image name.
    play = ImageButton(BoundingBox(950, 600, 1200, 650))
    accept = ImageButton(BoundingBox(525, 520, 755, 545))
    exit_now = ImageButton(
        click_box=BoundingBox(550, 425, 740, 440),
        capture_area=BoundingBox(520, 400, 775, 425),
    )
    check = ImageButton(BoundingBox(555, 425, 725, 470))
    normal_game = ImageButton(BoundingBox(50, 250, 275, 580))
    buy_xp = ImageButton(
        click_box=BoundingBox(35, 593, 124, 682),
        capture_area=BoundingBox(9, 550, 170, 708),
    )
    buy_xp_disabled = ImageButton(
        click_box=BoundingBox(35, 593, 124, 682),
        capture_area=BoundingBox(9, 550, 170, 708),
    )
    return_to_board = ImageButton(
        click_box=BoundingBox(1155, 595, 1242, 682),
        capture_area=BoundingBox(1128, 568, 1269, 709),
    )
    choose_one = ImageButton(
        click_box=BoundingBox(636, 91, 693, 186),
        capture_area=BoundingBox(1128, 568, 1269, 709),
    )
    choose_one_hidden = ImageButton(
        click_box=BoundingBox(1155, 595, 1242, 682),
        capture_area=BoundingBox(1128, 568, 1269, 709),
    )

    # Buttons without an image.
    store_card_one = ClickButton(BoundingBox(180, 47, 363, 272))
    store_card_two = ClickButton(BoundingBox(402, 47, 585, 272))
    store_card_three = ClickButton(BoundingBox(624, 47, 807, 272))
    store_card_four = ClickButton(BoundingBox(845, 47, 1028, 272))
    store_card_five = ClickButton(BoundingBox(1067, 47, 1250, 272))
    augment_one = ClickButton(BoundingBox(170, 120, 424, 520))
    augment_two = ClickButton(BoundingBox(516, 120, 770, 520))
    augment_three = ClickButton(BoundingBox(863, 120, 1117, 520))
    augment_one_roll = ClickButton(BoundingBox(266, 602, 323, 659))
    augment_two_roll = ClickButton(BoundingBox(612, 602, 669, 659))
    augment_three_roll = ClickButton(BoundingBox(659, 602, 1016, 659))

    @classmethod
    def get_store_cards(cls):
        """
        Utility method to get all five store card buttons.

        Returns:
             List of all five store card ClickButtons.
        """
        return [
            cls.store_card_one,
            cls.store_card_two,
            cls.store_card_three,
            cls.store_card_four,
            cls.store_card_five,
        ]

    @classmethod
    def get_augments(cls):
        """
        Utility method to get all three augment buttons.

        Returns:
            List of all three augment ClickButtons.
        """
        return [
            cls.augment_one,
            cls.augment_two,
            cls.augment_three,
        ]

    @classmethod
    def get_augment_rolls(cls):
        """
        Utility method to get all three augment buttons.

        Returns:
            List of all three augment ClickButtons.
        """
        return [
            cls.augment_one_roll,
            cls.augment_two_roll,
            cls.augment_three_roll,
        ]


# Assigns the variable name of an ImageButton to the image path.
for name, button in vars(Button).items():
    if name.startswith("__") or not isinstance(button, ImageButton):
        continue

    button.set_image_path(name)
