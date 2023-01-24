# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, string_to_code

from bamboolib.transformations.base_components import (
    ValueSelector,
    SingleColumnSelector,
)
from bamboolib.transformations.filter_transformer import ConditionSection


class SetValuesTransformation(Transformation):
    """Update column values based on boolean condition."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column = None
        self.df = self.get_df()

        self.condition_section = ConditionSection(
            self, self.df, self.column, focus_after_init=True
        )

        self.target_column_dropdown = SingleColumnSelector(
            options=list(self.df.columns),
            set_soft_value=True,
            width="md",
            on_change=self._update_value_selectors,
        )

        self.positive_value_box = widgets.VBox([])
        self.negative_value_box = widgets.VBox([])

        self.add_else_checkbox = widgets.Checkbox(
            value=False, description="add 'else' value"
        )
        self.add_else_checkbox.observe(
            lambda value: self._update_else_section(), names="value"
        )
        self.add_else_checkbox.add_class("bamboolib-checkbox")

        self.else_section = widgets.VBox([])

        self._update_value_selectors()

    def _update_value_selectors(self, *args, **kwargs):
        column = self.target_column_dropdown.value
        series = self.df[column]

        self.positive_value_selector = ValueSelector(
            self, series=series, columns=list(self.df.columns)
        )
        self.positive_value_box.children = [self.positive_value_selector]

        self.negative_value_selector = ValueSelector(
            self, series=series, columns=list(self.df.columns)
        )
        self.negative_value_box.children = [self.negative_value_selector]

    def render(self):
        self.set_title(f"Set values by conditions")
        self.set_content(
            widgets.HTML("<h4>If</h4>"),
            self.condition_section,
            widgets.HTML("<h4>Set value of column</h4>"),
            self.target_column_dropdown,
            widgets.HTML("<h4>To</h4>"),
            self.positive_value_box,
            self.add_else_checkbox,
            self.else_section,
        )

    def _update_else_section(self):
        if self.add_else_checkbox.value:
            self.else_section.children = [
                widgets.HTML("<h4>and otherwise to</h4>"),
                self.negative_value_box,
            ]
        else:
            self.else_section.children = []

    def is_valid_transformation(self):
        assert(self.condition_section.is_valid_condition())

        assert(self.positive_value_selector.is_valid_value())
        if self.add_else_checkbox.value:
            assert(self.negative_value_selector.is_valid_value())
        return True

    def get_description(self):
        boolean_series_description = self.condition_section.get_description()
        target_column = self.target_column_dropdown.value
        new_value = self.positive_value_selector.get_value_description()

        description = f"<b>Set values</b> of {target_column} to {new_value} where {boolean_series_description}"

        if self.add_else_checkbox.value:
            else_value = self.negative_value_selector.get_value_description()
            description += f" and otherwise to {else_value}"

        return description

    def get_code(self):
        boolean_series_code = self.condition_section.get_code()
        target_column = string_to_code(self.target_column_dropdown.value)
        new_value = self.positive_value_selector.get_value_code()

        if self.add_else_checkbox.value:
            else_value = self.negative_value_selector.get_value_code()
            # calculating the tmp_condition mask before the update is important
            # eg when Age is numeric and you update values of Age where Age < 18 to "infant" and else to "adult"
            # if the tmp condition is not separated, the first update will change Age into a string column
            # and thus, the numeric filter wont work for the else statement
            # therefore, the mask needs to be calculated before the updates
            code = f"""tmp_condition = {boolean_series_code}
{DF_OLD}.loc[tmp_condition, {target_column}] = {new_value}
{DF_OLD}.loc[~tmp_condition, {target_column}] = {else_value}"""
        else:
            code = f"{DF_OLD}.loc[{boolean_series_code}, {target_column}] = {new_value}"
        return code
