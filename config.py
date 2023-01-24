# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

from bamboolib._path import BAMBOOLIB_LIBRARY_CONFIG_PATH

from typing import Dict, Any
from pathlib import Path
from functools import reduce

import operator
import toml
import collections
import os


USER_CONFIG_PATH = BAMBOOLIB_LIBRARY_CONFIG_PATH / "config.toml"

# Keeping default config in a file somewhere in the package is error prone, since
# we need to include non-python files in MANIFEST.in
# e.g. this is a problem when renaming the toml file we would also need to adjust the MANIFEST.in
DEFAULT_CONFIG = """
[global]
show_live_code_export = true
export_transformation_descriptions = true
undo_levels = 5
random_seed = 123
log_errors = false

[plotly]
row_limit = 10000

[plot_creator]
add_figure_name_to_code_export = false

[plugins]
hide_search_options = []

[enterprise]
modifications = []
"""

# Types and samples of config options:
# global
# show_live_code_export: Boolean e.g. true
# export_transformation_descriptions: Boolean e.g. true
# undo_levels : int e.g. 1
# random_seed : int e.g. 123
#
# plotly
# row_limit : int e.g. 10000
#
# plugins
# hide_search_options: list of class names e.g. [ "GroupbyWithMultiselect", "GroupbyWithRename",]
#
# enterprise
# modifications: list of strings e.g. ["confidential_mode"]


# All variables in config will be persisted. If you want to have session variables, define them
# here instead
SHOW_BAMBOOLIB_UI = False
SHOW_NEW_VERSION_NOTIFICATION = True


_config_options: Dict[str, Any] = {}


def safe_touch(path):
    path.parents[0].mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)


def flatten(d, parent_key="", sep="."):
    """Flattens the potentially nested config file."""
    items = []
    for key, value in d.items():
        new_key = parent_key + sep + key if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten(value, new_key, sep=sep).items())
        else:
            items.append((new_key, value))
    return dict(items)


def dict_intersection(dict1, dict2):
    """
    Get the intersection of two dicts.

    :return: dict.
    """
    dict1_keys = set(dict1)
    dict2_keys = set(dict2)
    common_keys = dict1_keys.intersection(dict2_keys)

    output_dict = {key: dict2[key] for key in common_keys}
    return output_dict


def read_toml(path):
    with open(path, "r") as f:
        file_content = f.read()
        parsed_config_file = toml.loads(file_content)
        return parsed_config_file


def get_value_from_dict(data_dict, key):
    """
    Get a value from a potentially nested dict.

    :param data_dict: potentially nested dict.
    :param key: string. The key sequence path leading to the value we want to get.

    Example:
    my_dict = dict(a = dict(b = "c"))
    get_value_from_dict(my_dict, "a.b")  # returns "c"
    """
    map_list = key.split(".")
    return reduce(operator.getitem, map_list, data_dict)


def set_value_in_dict(data_dict, key, value):
    """Set a value in a potentially nested dict."""
    map_list = key.split(".")
    key_without_last = ".".join(map_list[:-1])
    get_value_from_dict(data_dict, key_without_last)[map_list[-1]] = value


def merge_config_dicts(
    user_options: Dict[str, Any], default_options: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create the user's sepcific config dict by updating the default config by the user settings.

    We do that to be backward compatible.
    """
    config_options = default_options

    config_options_flattened = flatten(config_options)
    user_options_flattened = flatten(user_options)

    _update_dict_flattened = dict_intersection(
        config_options_flattened, user_options_flattened
    )
    config_options_flattened.update(_update_dict_flattened)

    for key, value in config_options_flattened.items():
        set_value_in_dict(config_options, key, value)

    return config_options


def _set_option(key, value):
    """sets the option"""
    value_in_config = get_value_from_dict(_config_options, key)
    if isinstance(value, type(value_in_config)):
        set_value_in_dict(_config_options, key, value)
    else:
        raise TypeError(
            "The value of the config option must be of type %s, but was %s"
            % (type(value_in_config), type(value))
        )


def persist_config():
    safe_touch(USER_CONFIG_PATH)
    toml.dump(_config_options, open(USER_CONFIG_PATH, "w"))


def parse_config():
    global _config_options
    safe_touch(USER_CONFIG_PATH)
    user_options = read_toml(USER_CONFIG_PATH)

    default_options = toml.loads(DEFAULT_CONFIG)
    _config_options = merge_config_dicts(
        user_options=user_options, default_options=default_options
    )


# User facing APIs


def reset_options() -> None:
    """Resets the config options."""
    USER_CONFIG_PATH.unlink()
    parse_config()


def set_option(key: str, value) -> None:
    """
    Set a config option by key / value pair.

    :param key: string. The key of the option, like "global.show_bamboolib_ui".
    :param value: The value of the option.
    """
    _set_option(key, value)
    persist_config()


def get_option(key: str):
    """
    Return the current value of a given config option.

    :param key: string. The config option key, like "global.plotting.colors.bar_color".
    """
    return get_value_from_dict(_config_options, key)


def is_in_confidential_mode():
    """
    Return True if bamboolib is in confidential mode.
    """
    try:
        return "confidential_mode" in get_option("enterprise.modifications")
    except:
        return False


parse_config()
