# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

from bamboolib.plugins import TransformationPlugin, DF_OLD, DF_NEW, Singleselect
from bamboolib.helper import AuthorizedPlugin
import ipywidgets as widgets


DROP_NA_COLUMNS_OPTIONS = (
    ("only missing values", "all"),
    ("at least 1 missing value", "any"),
)


class DropColumnsWithMissingValues(AuthorizedPlugin, TransformationPlugin):
    """
    Plugin for dropping columns that contain only missing values or that contain at least 1 missing
    value.
    """

    name = "Drop columns with missing values"
    description = (
        "Drop columns that contain at least one missing value or only missing values"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.drop_na_option = Singleselect(
            options=DROP_NA_COLUMNS_OPTIONS,
            placeholder="Choose ...",
            focus_after_init=True,
            set_soft_value=True,
        )

    def render(self):
        self.set_title("Drop columns with missing values")
        self.set_content(
            widgets.HTML("Drop all columns that contain"),
            self.drop_na_option,
            self.rename_df_group,
        )

    def get_description(self):
        return "<b>Drop columns with missing values</b>"

    def get_code(self):
        return f"{DF_NEW} = {DF_OLD}.dropna(how='{self.drop_na_option.value}', axis=1)"
