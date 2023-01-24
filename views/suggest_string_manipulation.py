# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

import time

from bamboolib.helper import Viewable, VSpace
from bamboolib.widgets import Button

from bamboolib.transformations.filter_transformer import FilterTransformer, CONTAINS
from bamboolib.transformation_plugins.string_transformations import (
    SplitString,
    FindAndReplaceText,
)


class SuggestStringManipulation(Viewable):
    """
    A view that suggests string manipulations after the user highlighted a string of a column value with the mouse.
    This is intended to provide a shortcut for the user to express what they want to do.
    The user gets recommendations for suitable transformations and the parameters are prepopulated based on the user selection.
    """

    def __init__(self, side_window_outlet, column, string_, **kwargs):
        super().__init__(**kwargs)

        self.side_window_outlet = side_window_outlet

        self.column = column

        self.split_string = widgets.VBox(
            [
                self._make_button(
                    "Split string",
                    SplitString,
                    default_manipulation_options={
                        "selected_column_name": column,
                        "selected_pattern": string_,
                        "focus_column_input_after_init": False,
                    },
                ),
                widgets.HTML(
                    f"Split text in '{column}' based on the delimiter '{string_}'"
                ),
            ]
        )

        self.replace = widgets.VBox(
            [
                self._make_button(
                    "Find and replace text",
                    FindAndReplaceText,
                    default_manipulation_options={
                        "selected_column_name": column,
                        "find": string_,
                        "focus_column_input_after_init": False,
                    },
                ),
                widgets.HTML(f"Find and replace text '{string_}' in '{column}'"),
            ]
        )

        self.contains = widgets.VBox(
            [
                self._make_button(
                    "Filter rows",
                    FilterTransformer,
                    default_filter=CONTAINS,
                    default_filter_kwargs={"value": string_},
                ),
                widgets.HTML(f"Filter rows that contain '{string_}' in '{column}'"),
            ]
        )

    def render(self):
        spacer = VSpace("sm")
        self.set_title(f"Suggestions")

        self.set_content(self.replace, spacer, self.split_string, spacer, self.contains)

    def _make_button(self, description, transformer, new_outlet=None, **kwargs):
        if new_outlet is None:
            new_outlet = self.side_window_outlet

        def render_transformation_and_close_current_view(button):
            transformer(
                df_manager=self.df_manager, column=self.column, **kwargs
            ).add_to(new_outlet)

            if self.outlet == new_outlet:
                pass
            else:
                time.sleep(1)
                self.outlet.hide()

        return Button(
            description=description,
            on_click=render_transformation_and_close_current_view,
        )
