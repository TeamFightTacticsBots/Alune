"""
Collection of helper methods.
"""

from pathlib import Path
import sys

from loguru import logger


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


def is_version_string_newer(version_one: str, version_two: str):
    """
    Checks if version_one is newer than version_two.

    Args:
        version_one: The semantic version string to check
        version_two: The semantic version string to check against

    Returns:
        Whether version_one is newer than version_two.
    """
    version_one_parts = version_one.split(".")
    version_two_parts = version_two.split(".")

    for i in range(min(len(version_one_parts), len(version_two_parts))):
        if int(version_one_parts[i]) > int(version_two_parts[i]):
            return True
    return False


def raise_and_exit(error: str, exit_code: int = 1) -> None:
    """
    Raise the given text as an error and then exit the application

    Args:
        error: The image we should look at.
        exit_code: The relative or absolute path to the image to be found. Defaults to 1.
    """
    logger.error(error)
    sys.exit(exit_code)
