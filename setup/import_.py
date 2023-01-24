# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

from pathlib import Path
from bamboolib.helper import log_jupyter_action, log_setup
from bamboolib import __version__

# import analytics  # deactivated via removing import
import logging

# adjust analytics logging of segment
# read more here: https://segment.com/docs/sources/server/python/#logging
# available logging levels: https://docs.python.org/3/library/logging.html#logging-levels
# logging.getLogger('segment').setLevel('DEBUG')  # if you want to see upload errors
logging.getLogger("segment").setLevel("CRITICAL")

# # deactivated via removing import
# analytics.write_key = "Mf5XZHIsmD73CEFeN9gOSyNHzCBeaFhS"  # production
# #  analytics.write_key = "bkUgi5ariVh5BH9FhbxRyS97369omkoQ"  # DEV
log_jupyter_action("other", "JupyterCell", "import bamboolib")


IPYTHON_STARTUP_FOLDER = Path.home() / ".ipython" / "profile_default" / "startup"
STARTUP_FILE = IPYTHON_STARTUP_FOLDER / "bamboolib_autoimport.py"


def _create_or_reset_startup_file():
    if STARTUP_FILE.exists():
        STARTUP_FILE.unlink()  # deletes the old file
        # this is important if someone messed around with the file
        # if he calls our method, he expects that we repair everything
        # therefore, we delete the old file and write a new, valid version
    STARTUP_FILE.touch()  # create a new file


def _create_auto_startup_file(auto_import=False, extend_pandas_df=False):
    auto_import_code = "import bamboolib as bam"
    if not auto_import:
        auto_import_code = f"# {auto_import_code}"

    extend_pandas_df_code = "bam._enable_rich_pandas_df()"
    if not extend_pandas_df:
        extend_pandas_df_code = f"# {extend_pandas_df_code}"

    with STARTUP_FILE.open("w") as file:
        file.write(
            f"""
# HOW TO DEACTIVATE AUTO-IMPORT:
# if you dont want to auto-import bamboolib, you have two options:
# 0) if you want to disable the auto-import but sometimes keep using bamboolib
#    you can uncomment the import statement below
# 1) if you never want to use bamboolib again, you can delete this file

try:
    {auto_import_code}
    {extend_pandas_df_code}
    pass
except:
    pass
"""
        )


def maybe_print(message, should_print):
    if should_print:
        print(message)


def maybe_print_startup_folder_error(should_print):
    maybe_print(
        f"Error: Could not find the default IPython startup folder at {IPYTHON_STARTUP_FOLDER}",
        should_print,
    )


def _update_startup_file(auto_import=False, extend_pandas_df=False):
    if not IPYTHON_STARTUP_FOLDER.exists():
        maybe_print_startup_folder_error(True)
        return False

    try:
        _create_or_reset_startup_file()
        _create_auto_startup_file(
            auto_import=auto_import, extend_pandas_df=extend_pandas_df
        )
    except:
        maybe_print(
            "bamboolib error: there was an error when updating the startup file",
            should_print=True,
        )
    return True


def _enable(print_messages=True):
    from bamboolib.setup.ipython_display import extend_pandas_ipython_display

    extend_pandas_ipython_display()

    _update_startup_file(auto_import=False, extend_pandas_df=True)

    maybe_print(
        "Success: the bamboolib extension was enabled successfully. You can disable it via 'bam.disable()'. You will now see a magic bamboolib button when you display your dataframes, for example via 'df'",
        print_messages,
    )
    return True


def enable(print_messages=True):
    """
    When this method is called, bamboolib will add the interactive Dataframe view to pandas.DataFrames.

    If you no longer want this, you can call `disable`
    """
    log_setup("other", "JupyterCell", "bam.enable()")
    _enable(print_messages=print_messages)


def _enable_rich_pandas_df():
    # _enable_rich_pandas_df is only called inside the auto_startup file
    # we could use this call to set a global flag that marks that bamboolib was auto-imported
    log_jupyter_action("other", "ipython startup", "auto_import bamboolib")


def _disable(print_messages=True):
    from bamboolib.setup.ipython_display import reset_pandas_ipython_display

    reset_pandas_ipython_display()

    _update_startup_file(auto_import=False, extend_pandas_df=False)

    maybe_print(
        f"The bamboolib extension was disabled. You can enable it again via 'bam.enable()'. In case that bamboolib was not helpful to you, we are sorry and would like to fix this. Please write us a quick mail to info@8080labs.com so that we can serve you better in the future. Best regards, Tobias and Florian",
        print_messages,
    )
    return True


def disable(print_messages=True):
    """
    When this method is called, bamboolib's interactive Dataframe view for pandas.DataFrames will be removed/disabled.

    If you want to add/enable it again, please use `enable`
    """
    log_setup("other", "JupyterCell", "bam.disable()")
    _disable(print_messages=print_messages)


def _maybe_add_autostartup_file():
    if IPYTHON_STARTUP_FOLDER.exists() and (not STARTUP_FILE.exists()):
        try:
            _create_or_reset_startup_file()
            _create_auto_startup_file(auto_import=False, extend_pandas_df=False)
        except:
            print("bamboolib error: unable to add autostartup file")
