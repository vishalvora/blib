# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, DF_NEW, BamboolibError

from bamboolib.widgets.selectize import Singleselect
from bamboolib.transformations.columns_selector import ColumnsSelector


class DropDuplicatesTransformer(Transformation):
    """Remove duplicated rows in a dataframe, i.e. only keep distinct rows."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.column_selectize = ColumnsSelector(
            transformation=self, focus_after_init=True, set_all_columns_as_default=True
        )

        self.keep_dropdown = Singleselect(
            options=[
                ("keep first duplicate", "first"),
                ("keep last duplicate", "last"),
            ],
            set_soft_value=True,
            width="lg",
        )

    def render(self):
        self.set_title("Remove Duplicates")
        self.set_content(
            widgets.HTML("Identify duplicates based on"),
            self.column_selectize,
            widgets.HTML("and"),
            self.keep_dropdown,
            self.rename_df_group,
        )

    def get_description(self):
        col_names = self.column_selectize.value

        return f"<b>Drop duplicates</b> based on {col_names}"

    def is_valid_transformation(self):
        if len(list(self.column_selectize.value)) <= 0:
            raise BamboolibError(
                "No columns are selected.<br>Please select one or multiple columns"
            )
        return True

    def get_code(self):
        col_names = list(self.column_selectize.value)
        keep = self.keep_dropdown.value

        if len(col_names) == len(self.df_manager.get_current_df().columns):
            subset_code = ""
        else:
            subset_code = f"subset={col_names}, "

        return f"{DF_NEW} = {DF_OLD}.drop_duplicates({subset_code}keep='{keep}')"

    def get_metainfos(self):
        return {"drop_duplicates_keep": self.keep_dropdown.value}
