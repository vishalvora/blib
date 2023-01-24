# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

from bamboolib.helper import string_to_code
import pandas as pd
import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, BamboolibError

from bamboolib.widgets import Multiselect, Text
from bamboolib.transformations.columns_selector import ColumnsSelector


class LabelEncoder(Transformation):
    """Turn a categoric column into numeric integer codes (factorize)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.columns = ColumnsSelector(
            transformation=self,
            focus_after_init=True,
            set_all_columns_as_default=False,
            width=None,  # element has width of longest content
        )

        self.na_sentinel = Text(
            value="-1", description="Code for missing values:", execute=self
        )
        self.new_column_suffix = Text(
            value="_label", description="Suffix for new column name:", execute=self
        )

        self.sort_label_codes = widgets.Checkbox(
            value=True, description="Sort label codes (most common value = 0)"
        )
        self.sort_label_codes.add_class("bamboolib-checkbox")

    def render(self):
        self.set_title("LabelEncoder")
        self.set_content(
            widgets.HTML("Encode the columns"),
            self.columns,
            widgets.HTML("<br>"),
            self.sort_label_codes,
            self.na_sentinel,
            self.new_column_suffix,
        )

    def is_valid_transformation(self):
        try:
            int(self.na_sentinel.value)
        except:
            raise BamboolibError(
                f"""The code for the missing values needs to be an integer (e.g. 0, 1, -1, etc).<br>
            It seems like the current value ({self.na_sentinel.value}) is not an integer.<br>
            Please adjust the value"""
            )
        return True

    def get_description(self):
        return "LabelEncoder"

    def get_code(self):
        code = ""
        for index, column in enumerate(self.columns.value):
            suffix = self.new_column_suffix.value
            # Attention: the sort flag in pandas has the opposite meaning than our statement
            sort = not self.sort_label_codes.value
            na_sentinel = self.na_sentinel.value
            if index != 0:
                code += "\n"
            code += f"""{DF_OLD}[{string_to_code(f"{column}{suffix}")}] = {DF_OLD}[{string_to_code(column)}].factorize(sort={sort}, na_sentinel={na_sentinel})[0]"""
        return code
