# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import pandas as pd
import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, string_to_code

from bamboolib.transformations.base_components import ValueSelector
from bamboolib.transformations.columns_selector import ColumnsSelector

from bamboolib.widgets import Singleselect


class Option(widgets.VBox):
    """Base class for the replace option."""

    def __init__(self, transformation=None, **kwargs):
        self.transformation = transformation
        super().__init__(**kwargs)

    def get_code(self):
        raise NotImplementedError

    def is_valid_value(self):
        return True

class CustomValue(Option):
    """Replace with custom value."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.value = ValueSelector(
            self.transformation, show_column=False, show_missing_value=False
        )
        self.children = [self.value]

    def get_code(self):
        return f".fillna({self.value.get_value_code()})"

    def is_valid_value(self):
        return self.value.is_valid_value()

class Mean(Option):
    """Replace with mean of column."""

    def get_code(self):
        df_code = self.transformation.get_df_code()
        return f".fillna({df_code}.mean())"


class Median(Option):
    """Replace with median of column."""

    def get_code(self):
        df_code = self.transformation.get_df_code()
        return f".fillna({df_code}.median())"


class Mode(Option):
    """Replace with mode of column."""

    def get_code(self):
        df_code = self.transformation.get_df_code()
        return f".fillna({df_code}.mode().iloc[0])"


class ForwardFill(Option):
    """Forward fill nas in column."""

    def get_code(self):
        return f".fillna(method='ffill')"


class BackwardFill(Option):
    """Backward fill nas in column."""

    def get_code(self):
        return f".fillna(method='backfill')"


OPTIONS = [
    ("Value (text, numeric, boolean)", CustomValue),
    ("Mean of column", Mean),
    ("Median of column", Median),
    ("Mode (most frequent value) of column", Mode),
    ("Last valid value (forward fill)", ForwardFill),
    ("Next valid value (backward fill)", BackwardFill),
]


class ReplaceMissingValues(Transformation):
    """Fill / Impute missing values (NAs) in one or more columns."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.df = self.get_df()

        self.column = ColumnsSelector(
            transformation=self,
            width="lg",
            focus_after_init=True,
            set_all_columns_as_default=True,
        )
        self.type_dropdown = Singleselect(
            options=OPTIONS, set_soft_value=True, on_change=self._update_type_outlet, width="lg",
        )
        self.type_outlet = widgets.VBox()
        self.type_option = None

        self._update_type_outlet()

    def _update_type_outlet(self, *args):
        self.type_option = self.type_dropdown.value(transformation=self)
        self.type_outlet.children = [self.type_option]

    def render(self):
        self.set_title("Replace missing values")
        self.set_content(
            widgets.VBox(
                [
                    widgets.HTML("Replace missing values in"),
                    self.column,
                    widgets.HTML("with"),
                    self.type_dropdown,
                    self.type_outlet,
                ]
            )
        )

    def get_description(self):
        return f"<b>Replace missing values</b>"

    def get_df_code(self):
        return self.column.get_df_code()

    def get_code(self):
        df_code = self.get_df_code()
        return f"{df_code} = {df_code}{self.type_option.get_code()}"

    def is_valid_transformation(self):
        return self.type_option.is_valid_value()
