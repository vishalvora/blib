# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, DF_NEW

from bamboolib.widgets.selectize import Singleselect
from bamboolib.transformations.columns_selector import ColumnsSelector

KEEP = "keep"
DROP = "drop"

TRANSFORMATIONS = {
    KEEP: {"description": "<b>Select columns</b>", "code": f"%s"},
    DROP: {"description": "<b>Drop columns</b>", "code": f"{DF_OLD}.drop(columns=%s)"},
}


class SelectColumns(Transformation):
    """Select/delete one or multiple columns."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.select_type = Singleselect(
            options=[("Select", KEEP), ("Drop", DROP)],
            set_soft_value=True,
            focus_after_init=True,
            width="sm",
        )

        self.columns = ColumnsSelector(
            transformation=self, show_all_columns=False, width="lg"
        )

    def render(self):
        self.set_title("Select or drop columns")
        self.set_content(self.select_type, self.columns, self.rename_df_group)

    def get_description(self):
        return TRANSFORMATIONS[self.select_type.value]["description"]

    def get_code(self):
        type_ = self.select_type.value
        if type_ == KEEP:
            code = self.columns.get_df_code()
        else:
            code = self.columns.get_columns_code()

        subset_code = TRANSFORMATIONS[type_]["code"] % code

        return f"{DF_NEW} = {subset_code}"

    def reset_preview_columns_selection(self):
        # reset when selecting new columns but keep selection when just dropping columns
        type_ = self.select_type.value
        return type_ == KEEP

    def get_metainfos(self):
        return {
            "select_columns_count": len(self.columns.value),
            "select_columns_type": self.select_type.value,
        }

    def test_select_columns(self, columns):
        self.select_type.value = KEEP
        self.columns.value = columns

    def test_drop_columns(self, columns):
        self.select_type.value = DROP
        self.columns.value = columns
