# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import pandas as pd
import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, DF_NEW

from bamboolib.widgets.selectize import Singleselect

from bamboolib.transformations.base_components import (
    SelectorGroupMixin,
    SelectorMixin,
    SingleColumnSelector,
)


class SortDimension(SelectorMixin, widgets.HBox):
    """Manages a column to sort and its sort direction (A->Z or Z->A)."""

    def __init__(self, column_options, default_column=None, **kwargs):
        super().__init__(**kwargs)

        self.column_dropdown = SingleColumnSelector(
            options=column_options,
            value=default_column,
            focus_after_init=True,
            set_soft_value=True,
            width="sm",
        )

        self.direction_dropdown = Singleselect(
            options=[("ascending (A-Z)", True), ("descending (Z-A)", False)],
            width="sm",
            set_soft_value=True,
        )

        self.children = [
            self.column_dropdown,
            self.direction_dropdown,
            self.delete_selector_button,
        ]

    def test_select_column(self, column_name):
        self.column_dropdown.value = column_name

    def test_select_sort_direction(self, sort_direction: bool):
        self.direction_dropdown.value = sort_direction


class SortSection(SelectorGroupMixin, widgets.VBox):
    """Manages a group of `SortDimension`s."""

    def __init__(self, df, default_column=None):
        super().__init__()
        self.df = df
        self.default_column = default_column

        self.init_selector_group("add column")

        self.children = [self.selector_group, self.add_selector_button]

    def create_selector(self, default_column=None, show_delete_button=None, **kwargs):
        return SortDimension(
            list(self.df.columns),
            default_column=default_column,
            selector_group=self,
            show_delete_button=show_delete_button,
        )

    def get_initial_selector(self):
        return self.create_selector(
            default_column=self.default_column, show_delete_button=False
        )

    def get_columns(self):
        return [selector.column_dropdown.value for selector in self.get_selectors()]

    def get_directions(self):
        return [selector.direction_dropdown.value for selector in self.get_selectors()]

    def get_directions_string(self):
        return [selector.direction_dropdown.label for selector in self.get_selectors()]

    def test_select_column(self, column_name):
        self.get_selectors()[-1].test_select_column(column_name)

    def test_select_sort_direction(self, sort_direction: bool):
        self.get_selectors()[-1].test_select_sort_direction(sort_direction)


class SortTransformer(Transformation):
    """Sort one of multiple columns ascending or descending."""

    def __init__(self, *args, column=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sort_section = SortSection(self.get_df(), default_column=column)

    def render(self):
        self.set_title("Sort column(s)")
        self.set_content(self.sort_section, self.rename_df_group)

    def get_description(self):
        columns = self.sort_section.get_columns()
        directions = self.sort_section.get_directions_string()
        column_strings = []
        for index, value in enumerate(columns):
            column_strings.append(f"{columns[index]} {directions[index]}")
        full_column_string = ", ".join(column_strings)
        return f"<b>Sort column(s)</b> {full_column_string}"

    def get_code(self):
        columns = self.sort_section.get_columns()
        directions = self.sort_section.get_directions()
        return f"{DF_NEW} = {DF_OLD}.sort_values(by={columns}, ascending={directions})"

    def get_metainfos(self):
        return {"sort_dimensions_count": len(self.sort_section.get_columns())}

    def test_select_column(self, column_name):
        self.sort_section.test_select_column(column_name)

    def test_select_sort_direction(self, sort_direction: str):
        if sort_direction == "ascending":
            sort_direction_bool = True
        elif sort_direction == "descending":
            sort_direction_bool = False
        else:
            raise Exception("Invalid sort direction")

        self.sort_section.test_select_sort_direction(sort_direction_bool)
