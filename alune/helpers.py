from loguru import logger
import sys

def raise_and_exit(
    error: str,
    exit_code: int = 1
) -> None:
    """
    Raise the given text as an error and then exit the application

    Args:
        error: The image we should look at.
        exit_code: The relative or absolute path to the image to be found. Defaults to 1.
    """
    logger.error(error)
    sys.exit(exit_code)
