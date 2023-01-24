# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

# LATER: what if they want to pivot 2 columns at the same time? eg for a nested pivot table?
#   - they can just merge the two columns together beforehand. This is better anyway ...
#   - ALSO, we can add Multiselect for variable columns and then do the merge ourselves

import ipywidgets as widgets

from bamboolib.helper import Transformation, notification, DF_OLD, DF_NEW
from bamboolib._path import BAMBOOLIB_LIBRARY_ROOT_PATH

from bamboolib.transformations.base_components import SingleColumnSelector


class PivotTransformation(Transformation):
    """Reshape the dataframe from long to wide format."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.explanation_image = widgets.Image(
            value=open(
                BAMBOOLIB_LIBRARY_ROOT_PATH / "assets" / "img" / "long_to_wide.png",
                "rb",
            ).read(),
            format="png",
        )
        self.explanation_image.add_class("bamboolib-hint-img")

        if self._pivot_is_possible():
            self._init_UI()

    def render(self):
        self.set_title("Pivot long to wide format")

        if self._pivot_is_possible():
            self._show_UI()
        else:
            self._show_too_few_columns_error()

    def _pivot_is_possible(self):
        columns_count = len(list(self.get_df().columns))
        return columns_count >= 3

    def _init_UI(self):
        df = self.get_df()
        last_column = list(df.columns)[-1]
        penultimate_column = list(df.columns)[-2]
        self.variable_dropdown = SingleColumnSelector(
            placeholder="Variable column",
            options=list(df.columns),
            value=penultimate_column,
            set_soft_value=True,
            focus_after_init=True,
            width="md",
        )

        self.value_dropdown = SingleColumnSelector(
            placeholder="Value column",
            options=list(df.columns),
            value=last_column,
            set_soft_value=True,
            width="md",
        )

    def _show_UI(self):
        self.set_content(
            self.explanation_image,
            widgets.HTML("Pivot the variable and value columns."),
            self.variable_dropdown,
            self.value_dropdown,
            self.rename_df_group,
        )

    def _show_too_few_columns_error(self):
        columns_count = len(list(self.get_df().columns))

        self.outlet.set_content(
            widgets.VBox(
                [
                    self.explanation_image,
                    notification(
                        (
                            "Pivoting is only possible if the dataframe has <b>at least 3 columns</b>. "
                            f"Currently, the dataframe has only {columns_count} columns."
                        ),
                        type="warning",
                    ),
                ]
            )
        )

    def _remaining_columns(self):
        df = self.get_df()
        columns = list(df.columns)
        columns.remove(self.variable_dropdown.value)
        columns.remove(self.value_dropdown.value)
        return columns

    def get_description(self):
        variable = self.variable_dropdown.value
        value = self.value_dropdown.value
        return f"<b>Pivot dataframe</b> from long to wide format using the variable column '{variable}' and the value column '{value}'"

    def get_code(self):
        columns = self._remaining_columns()
        variable = self.variable_dropdown.value
        value = self.value_dropdown.value

        if len(columns) == 1:
            index = columns[0]
            code = f"{DF_NEW} = {DF_OLD}.pivot(index='{index}', columns='{variable}', values='{value}').reset_index()\n"
        else:
            # more than 1 remaining index columns
            columns = columns + [variable]
            code = f"{DF_NEW} = {DF_OLD}.set_index({columns})['{value}'].unstack(-1).reset_index()\n"

        code += f"{DF_NEW}.columns.name = ''"
        return code
