# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


class BamboolibError(Exception):
    """
    A custom error object.

    Use it if you want to show custom error messages to the user when writing TransformationPlugins.
    The error message will be displayed as HTML and without the error traceback.

    Example:
    >>> def is_valid_transformation(self):
    >>>     if self.column_input.value is None:  # user has not selected a column in UI
    >>>         raise BamboolibError(
    >>>             \"""
    >>>             You haven't specified the column in which you want to replace text.
    >>>             Please select a column.
    >>>             \"""
    >>>         )
    >>>     return True
    """

    pass
