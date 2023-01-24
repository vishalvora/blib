# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

from bamboolib.plugins import TransformationPlugin, DF_OLD, Singleselect, Multiselect

from bamboolib.helper import (
    Transformation,
    notification,
    BamboolibError,
    string_to_code,
    AuthorizedPlugin,
)

import ipywidgets as widgets


class NumericTransformation(Transformation):
    """
    Acts like a decorator for Transformation plugins. It makes sure that the decorated
    Transformation plugin is only rendered if there are numeric columns the data.

    Attention: NumericTransformation _must_ come before TransformationPlugin when
    inheriting from both.
    """

    def init_numeric_transformation(self):
        """TO BE OVERIDDEN by any child"""
        pass

    def render_numeric_transformation(self):
        """TO BE OVERIDDEN by any child"""
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.numeric_columns = list(
            self.get_df().select_dtypes(include=["number"]).columns
        )
        if self.has_numeric_columns():
            self.init_numeric_transformation()

    def render(self):
        if self.has_numeric_columns():
            self.render_numeric_transformation()
        else:
            # LATER: allow this anyway? and implicitly convert the column to numeric? maybe show a warning?
            message = notification(
                "<b>Error:</b> Currently, the dataframe contains no numeric columns.",
                type="error",
            )
            # Attention: set content on outlet because we dont want to show an execute button
            self.outlet.set_content(message)

    def has_numeric_columns(self):
        return len(self.numeric_columns) > 0

    def user_changed_column_input(self, column, suffix=""):
        """
        Whenever the user picks a column, we make sure that the "new column name"
        textfield value is filled with "<column>_<suffix>"
        """
        if column is None:
            column = ""
        else:
            column += f"_{suffix}"
        self.set_column(column)


class PercentageChange(NumericTransformation, AuthorizedPlugin, TransformationPlugin):

    name = "Percentage change"
    description = "Window function: calculate the percentage change of a column, optionally within groups."

    def init_numeric_transformation(self):
        new_column_suffix = "pct_change"
        columns = list(self.get_df().columns)

        self.value_column_input = Singleselect(
            options=self.numeric_columns,
            placeholder="Choose column",
            focus_after_init=True,
            on_change=lambda dropdown: self.user_changed_column_input(
                dropdown.value, new_column_suffix
            ),
        )
        self.groupby_columns_input = Multiselect(
            options=columns, placeholder="Choose column(s) - optional"
        )
        self.user_changed_column_input(self.value_column_input.value, new_column_suffix)

    def render_numeric_transformation(self):
        self.set_title("Calculate percentage change")
        self.set_content(
            widgets.HTML("Calculate percentage change of"),
            self.value_column_input,
            widgets.HTML("For each group in - optional"),
            self.groupby_columns_input,
            self.rename_column_group,
        )

    def get_code(self):
        if len(self.groupby_columns_input.value) == 0:
            groupy_column_code = ""
        else:
            groupy_column_code = f".groupby({self.groupby_columns_input.value})"

        return f"""{DF_OLD}[{string_to_code(self.new_column_name_input.value)}] = {DF_OLD}{groupy_column_code}[{string_to_code(self.value_column_input.value)}].transform('pct_change')"""

    def is_valid_transformation(self):
        if self.value_column_input.value is None:
            raise BamboolibError(
                """
                You haven't specified the column for which you want to calculate the percentage change.
                Please select a column.
            """
            )
        return True


class CumulativeProduct(NumericTransformation, AuthorizedPlugin, TransformationPlugin):

    name = "Cumulative product"
    description = (
        "Window function: calculate the cumulative product, optionally within groups."
    )

    def init_numeric_transformation(self):
        new_column_suffix = "cumprod"
        columns = list(self.get_df().columns)

        self.value_column_input = Singleselect(
            options=self.numeric_columns,
            placeholder="Choose column",
            focus_after_init=True,
            on_change=lambda dropdown: self.user_changed_column_input(
                dropdown.value, new_column_suffix
            ),
        )
        self.groupby_columns_input = Multiselect(
            options=columns, placeholder="Choose column(s) - optional"
        )
        self.user_changed_column_input(self.value_column_input.value, new_column_suffix)

    def render_numeric_transformation(self):
        self.set_title("Calculate cumulative product")
        self.set_content(
            widgets.HTML("Calculate cumulative product of"),
            self.value_column_input,
            widgets.HTML("For each group in - optional"),
            self.groupby_columns_input,
            self.rename_column_group,
        )

    def get_code(self):
        if len(self.groupby_columns_input.value) == 0:
            groupy_column_code = ""
        else:
            groupy_column_code = f".groupby({self.groupby_columns_input.value})"

        return f"""{DF_OLD}[{string_to_code(self.new_column_name_input.value)}] = {DF_OLD}{groupy_column_code}[{string_to_code(self.value_column_input.value)}].cumprod()"""

    def is_valid_transformation(self):
        if self.value_column_input.value is None:
            raise BamboolibError(
                """
                You haven't specified the column for which you want to calculate the cumulative product.
                Please select a column.
            """
            )
        return True


class CumulativeSum(NumericTransformation, AuthorizedPlugin, TransformationPlugin):

    name = "Cumulative sum"
    description = (
        "Window function: calculate the cumulative sum, optionally within groups."
    )

    def init_numeric_transformation(self):
        new_column_suffix = "cumsum"
        columns = list(self.get_df().columns)

        self.value_column_input = Singleselect(
            options=self.numeric_columns,
            placeholder="Choose column",
            focus_after_init=True,
            on_change=lambda dropdown: self.user_changed_column_input(
                dropdown.value, new_column_suffix
            ),
        )
        self.groupby_columns_input = Multiselect(
            options=columns, placeholder="Choose column(s) - optional"
        )
        self.user_changed_column_input(self.value_column_input.value, new_column_suffix)

    def render_numeric_transformation(self):
        self.set_title("Calculate cumulative sum")
        self.set_content(
            widgets.HTML("Calculate cumulative sum of"),
            self.value_column_input,
            widgets.HTML("For each group in - optional"),
            self.groupby_columns_input,
            self.rename_column_group,
        )

    def get_code(self):
        if len(self.groupby_columns_input.value) == 0:
            groupy_column_code = ""
        else:
            groupy_column_code = f".groupby({self.groupby_columns_input.value})"

        return f"""{DF_OLD}[{string_to_code(self.new_column_name_input.value)}] = {DF_OLD}{groupy_column_code}[{string_to_code(self.value_column_input.value)}].cumsum()"""

    def is_valid_transformation(self):
        if self.value_column_input.value is None:
            raise BamboolibError(
                """
                You haven't specified the column for which you want to calculate the cumulative sum.
                Please select a column.
            """
            )
        return True
