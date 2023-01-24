# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, DF_NEW
from bamboolib.widgets.selectize import Multiselect


ALL_COLUMNS_DESCRIPTOR = "[All columns]"


class DropNaTransformation(Transformation):
    """Remove rows with missing values (NAs) in one or more columns."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.column_selectize = Multiselect(
            options=[ALL_COLUMNS_DESCRIPTOR] + list(self.get_df().columns),
            placeholder="Choose column(s)",
            value=[ALL_COLUMNS_DESCRIPTOR],
            focus_after_init=True,
            width="lg",
        )

    def render(self):
        self.set_title("Drop missing values")
        self.set_content(
            widgets.HTML("Drop rows with any missing value in"),
            self.column_selectize,
            self.rename_df_group,
        )

    def get_description(self):
        col_names = self.column_selectize.value

        if ALL_COLUMNS_DESCRIPTOR in col_names:
            col_names = ALL_COLUMNS_DESCRIPTOR

        return f"<b>Drop missing values</b> in {col_names}"

    def _drop_na_in_all_columns(self):
        column_names = self.column_selectize.value
        return (ALL_COLUMNS_DESCRIPTOR in column_names) or len(column_names) == 0

    def get_code(self):
        column_names = self.column_selectize.value

        if self._drop_na_in_all_columns():
            code = ""
        else:
            code = f"subset={column_names}"

        return f"{DF_NEW} = {DF_OLD}.dropna({code})"

    def get_metainfos(self):
        return {
            "drop_na_columns_count": len(self.column_selectize.value),
            "drop_na_in_all_columns": self._drop_na_in_all_columns(),
        }
