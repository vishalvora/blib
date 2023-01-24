# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import logging

from bamboolib._path import BAMBOOLIB_LIBRARY_CONFIG_PATH
from bamboolib.config import get_option

ERROR_LOG_FILE = BAMBOOLIB_LIBRARY_CONFIG_PATH / "ERROR_LOGS"

file_logger = logging.getLogger("bamboolib.file_logger")
file_logger.setLevel(logging.DEBUG)

try:
    BAMBOOLIB_LIBRARY_CONFIG_PATH.mkdir(parents=True, exist_ok=True)
    # the FileHandler will create a file if none exists BUT the folder has to exist
    handler = logging.FileHandler(ERROR_LOG_FILE)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    file_logger.addHandler(handler)
except PermissionError:
    # most likely the permission to create the directory or file were denied
    # in this case, the logger just wont log to a file
    if get_option("global.log_errors"):
        file_logger.exception(
            "PermissionError when trying to set the FileHandler for the file_loggger"
        )


def print_log_contents():
    """
    Prints all the contents of the log file.

    Usage during error diagnosis:
    >>> bam.setup.file_logger.print_log_contents()

    If this does not work, then we can use a workaround which does not import bamboolib:
    >>> from pathlib import Path
    >>> ERROR_LOG_FILE = Path.home() / ".bamboolib" / "ERROR_LOGS"
    >>> with open(ERROR_LOG_FILE, "r") as file:
    >>>     print(file.read())
    """
    with open(ERROR_LOG_FILE, "r") as file:
        print(file.read())
