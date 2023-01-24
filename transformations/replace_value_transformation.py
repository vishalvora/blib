# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import pandas as pd
import numpy as np
import ipywidgets as widgets

from bamboolib.helper import Transformation, notification, DF_OLD, string_to_code

from bamboolib.transformations.base_components import (
    ValueSelector,
    SingleColumnSelector,
)

REPLACE_IN_ALL_COLUMNS_STRING = "BAMBOO_REPLACE_IN_ALL_COLUMNS"


class ReplaceValueTransformation(Transformation):
    """Substitute *exact* cell values in one or all columns."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.df = self.get_df()
        self.column = None
        all_columns_option = [("[All columns]", REPLACE_IN_ALL_COLUMNS_STRING)]
        column_names = [(column, column) for column in list(self.df.columns)]

        self.column_dropdown = SingleColumnSelector(
            placeholder="Choose column(s)",
            value=self.column,
            options=all_columns_option + column_names,
            set_soft_value=True,
            focus_after_init=True,
            width="md",
            on_change=self._on_column_change,
        )

        self.find_value_box = widgets.VBox()
        self.replace_value_box = widgets.VBox()

        self._on_column_change()

    def _update_value_selectors(self):
        if self.column_dropdown.value == REPLACE_IN_ALL_COLUMNS_STRING:
            self.find_value = ValueSelector(self)
            self.replace_value = ValueSelector(self)
        else:
            series = self.df[self.column]
            self.find_value = ValueSelector(self, series=series)
            self.replace_value = ValueSelector(self, series=series)

        self.find_value_box.children = [self.find_value]
        self.replace_value_box.children = [self.replace_value]

    def render(self):
        self.set_title("Replace exact values")
        self.outlet.set_content(
            widgets.VBox(
                [
                    widgets.HTML("<h4>In</h4>"),
                    self.column_dropdown,
                    widgets.HTML("<h4>Find the exact value</h4>"),
                    self.find_value_box,
                    widgets.HTML("<h4>And replace with</h4>"),
                    self.replace_value_box,
                    widgets.HTML("<br>"),
                    self.execute_button,
                    widgets.HTML("<br>"),
                    notification(
                        """<b>Cannot do what you want?</b><br>
                                <ul>
                                    <li>If you want to <b>replace substrings</b>, please use 'String transformations'.</li>
                                    <li>If you want to <b>change values based on a condition</b>, please use 'Set/Update values'.</li>
                                </ul>"""
                    ),
                ]
            )
        )

    def _replacing_in_all_columns(self):
        return self.column == REPLACE_IN_ALL_COLUMNS_STRING

    def _on_column_change(self, *args, **kwargs):
        self.column = self.column_dropdown.value
        self._update_value_selectors()

    def get_column_description(self):
        if self._replacing_in_all_columns():
            return "all columns"
        else:
            return f"'{self.column}'"

    def get_description(self):
        find_value = self.find_value.get_value_description()
        replace_value = self.replace_value.get_value_description()
        return f"<b>Replace</b> {find_value} with {replace_value} in {self.get_column_description()}"

    def get_code_suffix(self):
        find_value = self.find_value.get_value_code()
        replace_value = self.replace_value.get_value_code()
        return f".replace({find_value}, {replace_value})"

    def get_code(self):
        if self._replacing_in_all_columns():
            prefix = f"{DF_OLD} = {DF_OLD}"
        else:
            prefix = f"{DF_OLD}[{string_to_code(self.column)}] = {DF_OLD}[{string_to_code(self.column)}]"
        suffix = self.get_code_suffix()
        return prefix + suffix

    def is_valid_transformation(self):
        return self.find_value.is_valid_value() and self.replace_value.is_valid_value()
