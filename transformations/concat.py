# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import pandas as pd

import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, DF_NEW, BamboolibError
from bamboolib.widgets.selectize import Singleselect, Multiselect


CONCAT_DIRECTIONS = [
    ("vertically (below each other)", "vertical"),
    ("horizontally (side by side)", "horizontal"),
]


class Concat(Transformation):
    """Concatenate (union / stack) multiple dataframes vertically or horizontally."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.df_dict = self._get_other_df_names_from_symbols()

        self.dfs_to_concat = Multiselect(
            options=list(self.df_dict.keys()),
            placeholder="Select dataframe(s)",
            focus_after_init=True,
            width="lg",
        )
        self.concat_direction = Singleselect(
            options=CONCAT_DIRECTIONS,
            placeholder="Choose direction",
            set_soft_value=True,
            width="lg",
        )

    def _get_other_df_names_from_symbols(self):
        """
        Returns a dict containing all dataframes available in the notebook that
        aren't the current dataframe.
        """
        symbols = self.df_manager.symbols
        return {
            key: symbols[key]
            for key in symbols.keys()
            if isinstance(symbols[key], pd.DataFrame)
            and not (
                key.startswith("_") or (key == self.df_manager.get_current_df_name())
            )
        }

    def _check_column_index_is_not_multi_index(self, selected_df_names):
        """Check if any dataframe has a column multi-index."""
        for df_name in selected_df_names:
            if isinstance(self.df_dict[df_name].columns, pd.MultiIndex):
                raise BamboolibError(
                    f"""<b>{df_name}</b>'s column index is a multi-index which is why we cannot combine
                    it with the other dataframes.<br>Please flatten <b>{df_name}</b>'s columns.
                    Contact our <a href='mailto:support@8080labs.com'>support team</a> for help."""
                )

    def _check_row_index_is_not_multi_index(self, selected_df_names):
        """Check if any dataframe has a row multi-index."""
        for df_name in selected_df_names:
            if isinstance(self.df_dict[df_name].index, pd.MultiIndex):
                raise BamboolibError(
                    f"""<b>{df_name}</b>'s row index is a multi-index which is why we cannot combine
                    it with the other dataframes.<br>Please reset the row index first. Contact our
                    <a href='mailto:support@8080labs.com'>support team</a> for help."""
                )

    def render(self):
        self.set_title("Concatenate")
        self.set_content(
            widgets.HTML("Concatenate the dataframe(s)"),
            self.dfs_to_concat,
            self.concat_direction,
            widgets.HTML("to the current dataframe"),
            self.rename_df_group,
        )

    def get_description(self):
        combine_string = (
            "vertically"
            if self.concat_direction.value == "vertical"
            else "horizontally"
        )
        return f"Concatenate dataframes {combine_string}"

    def is_valid_transformation(self):
        selected_df_names = self.dfs_to_concat.value

        no_dfs_selected = len(selected_df_names) == 0
        if no_dfs_selected:
            raise BamboolibError(
                "You did not select any dataframes for the concatenation.<br>Please select at least 1 dataframe."
            )

        self._check_column_index_is_not_multi_index(selected_df_names)

        if self.concat_direction.value == "horizontal":
            self._check_row_index_is_not_multi_index(selected_df_names)

        return True

    def get_code(self):
        is_horizontal_concat = self.concat_direction.value == "horizontal"

        df_names_to_concat = [DF_OLD] + self.dfs_to_concat.value
        if is_horizontal_concat:
            df_names_to_concat = [
                f"{df_name}.reset_index(drop=True)" for df_name in df_names_to_concat
            ]

        df_names_to_concat_string = ", ".join(df_names_to_concat)
        axis_int = 1 if is_horizontal_concat else 0
        ignore_index_code = "" if is_horizontal_concat else ", ignore_index=True"

        return f"{DF_NEW} = pd.concat([{df_names_to_concat_string}], axis={axis_int}{ignore_index_code})"

    """Functions to programmatically set user input. Used for unit tests."""

    def test_set_dfs_to_concat(self, df_names):
        self.dfs_to_concat.value = df_names

    def test_set_concat_direction(self, direction):
        VALID_DIRECTIONS = [element[1] for element in CONCAT_DIRECTIONS]
        if not direction in VALID_DIRECTIONS:
            raise ValueError(f"direction must be one of {VALID_DIRECTIONS}")

        self.concat_direction.value = direction
