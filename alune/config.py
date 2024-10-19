"""
Module to handle the configuration for the bot.
"""

import os.path
from random import Random
import shutil
from typing import Any

from loguru import logger
from ruamel.yaml import YAML

from alune import helpers
from alune import images

_random = Random()


class AluneConfig:
    """
    Alune config class.
    """

    def __init__(self):
        """
        Writes the configuration from resource (provided in repository) to storage path, loads the configuration from
        storage path to memory and updates the configuration if necessary.
        """
        yaml = YAML()

        config_resource_path = helpers.get_resource_path("alune/resources/config.yaml")
        config_path = helpers.get_application_path("alune-output/config.yaml")
        os.makedirs(os.path.dirname(config_path), exist_ok=True)

        if not os.path.isfile(config_path):
            shutil.copyfile(config_resource_path, config_path)

        with open(config_resource_path, mode="r", encoding="UTF-8") as config_resource:
            _config_resource: dict[str, Any] = yaml.load(config_resource)

        with open(config_path, mode="r", encoding="UTF-8") as config_file:
            self._config = yaml.load(config_file)

        if _config_resource.get("version") > self._config.get("version", 0):
            logger.warning("Config is outdated, creating a back-up and updating it.")

            shutil.copyfile(config_path, f"{config_path}.bak")

            if _config_resource.get("set") > self._config.get("set", 11):
                logger.warning("There is a new set, updating traits as well.")
                self._config["set"] = _config_resource["set"]
                self._config["traits"] = _config_resource["traits"]

            _config_resource.update(
                (key, self._config[key]) for key in self._config.keys() & _config_resource.keys() if key != "version"
            )
            with open(config_path, mode="w", encoding="UTF-8") as config_file:
                yaml.dump(_config_resource, config_file)

            self._config = _config_resource

        self._sanitize()

    def _sanitize(self):
        """
        Calls all sanitize methods.
        If necessary, user configured values will be overridden with a valid value (in memory, not in the file).
        The user should be notified of any invalid configurations.
        """
        self._sanitize_log_level()
        self._sanitize_game_mode()
        self._sanitize_traits()
        self._sanitize_adb_port()

    def _sanitize_adb_port(self):
        adb_port = self._config.get("adb_port", 5555)
        try:
            adb_port = int(adb_port)
        except ValueError:
            logger.warning(f"The configured adb port '{adb_port}' is not a number. Using 5555 instead.")
            adb_port = 5555
        self._config["adb_port"] = adb_port

    def _sanitize_log_level(self):
        """
        Sanitize the user configured log level by checking against valid values.
        """
        log_level = self._config.get("log_level", "INFO").upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            logger.warning(f"The configured log level '{log_level}' does not exist. Using INFO instead.")
            self._config["log_level"] = "INFO"

    def _sanitize_game_mode(self):
        """
        Sanitize the user configured game mode by checking against valid values.
        """
        game_mode = self._config.get("game_mode", "normal")
        if game_mode not in {"normal", "dawn of heroes"}:
            logger.warning(f"The configured game mode '{game_mode}' does not exist. Playing 'normal' instead.")
            self._config["game_mode"] = "normal"

    def _sanitize_traits(self):
        """
        Sanitize the user configured traits by checking against currently implemented traits.
        """
        if self._config["game_mode"] == "dawn of heroes":
            trait_class = images.DawnOfHeroesTrait
        else:
            trait_class = images.Trait

        current_traits = [trait.name for trait in list(trait_class)]
        configured_traits = self._config.get("traits", [])

        allowed_traits = []
        for trait in configured_traits:
            if trait.upper() not in current_traits:
                logger.warning(f"The configured trait '{trait}' does not exist. Skipping it.")
                continue
            allowed_traits.append(trait_class[trait.upper()])

        if len(allowed_traits) == 0:
            logger.warning(f"No valid traits were configured. Falling back to {trait_class.get_default_traits()}.")
            allowed_traits = trait_class.get_default_traits()

        self._config["traits"] = allowed_traits

    def get_log_level(self) -> str:
        """
        Get the level we're supposed to log at from the config.

        Returns:
            The configured level as a str.
        """
        return self._config["log_level"]

    def get_adb_port(self) -> int:
        """
        Get the adb port the user wants us to connect to.

        Returns:
            The port to attempt a connection to.
        """
        return self._config.get("adb_port", 5555)

    def get_traits(self) -> list[images.Trait]:
        """
        Get the list of traits we attempt to purchase.

        Returns:
            A list of traits we look for.
        """
        return self._config["traits"]

    def should_surrender(self) -> bool:
        """
        Get the surrender option the user wants.

        Returns:
            Whether we should surrender when possible.
        """
        return self._config["surrender_early"]

    def get_surrender_delay(self) -> int:
        """
        Get the surrender delay.

        Returns:
            An random Integer between [1 and surrender_random_delay]
            Returns 0 if feature disabled or negative value.
        """
        delay_upper_bound = self._config["surrender_random_delay"] or 0
        if delay_upper_bound <= 0:
            return 0
        return _random.randint(1, delay_upper_bound)

    def get_game_mode(self) -> str:
        """
        Get the game mode we should play.

        Returns:
            The game mode name.
        """
        return self._config["game_mode"]
