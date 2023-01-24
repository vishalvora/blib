# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import pandas as pd
import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, DF_NEW, notification

from bamboolib.widgets.selectize import Singleselect, Multiselect

from bamboolib.transformations.base_components import (
    SelectorGroupMixin,
    SelectorMixin,
    SingleColumnSelector,
)


class KeyPair(SelectorMixin, widgets.HBox):
    """Manages a <key of left df>, <key of right df> pair."""

    def __init__(self, left_options, right_options, show_delete_button=None, **kwargs):
        super().__init__(show_delete_button=show_delete_button, **kwargs)

        self.dropdowns = {"left": None, "right": None}
        self.set_options("left", left_options, focus_left_after_init=show_delete_button)
        self.set_options("right", right_options)

        self.render()

    def render(self):
        self.children = [
            self.dropdowns["left"],
            widgets.HTML(" and "),
            self.dropdowns["right"],
            self.delete_selector_button,
        ]

    def set_options(self, side, options, focus_left_after_init=False):
        old_value = None
        if self.dropdowns[side] is not None:
            old_value = self.dropdowns[side].value

        focus_after_init = (side == "left") if focus_left_after_init else False

        self.dropdowns[side] = SingleColumnSelector(
            options=options,
            value=old_value,
            focus_after_init=focus_after_init,
            set_soft_value=True,
            width="sm",
        )

        if side == "left":
            self.dropdowns[side].on_change(
                lambda dropdown: self._maybe_set_right_value(dropdown.value)
            )

    def _maybe_set_right_value(self, value):
        """If the key of the left df exists in the right df, we pre-select it for the user."""
        self.dropdowns["right"].value = value
        self.dropdowns["right"].focus()


class KeyPairSection(SelectorGroupMixin, widgets.VBox):
    """Manages a group of `KeyPair`s."""

    def __init__(self, left_df, right_df):
        super().__init__()
        self.dataframes = {"left": left_df, "right": right_df}

        self.init_selector_group(add_button_text="add keys")

        self.children = [
            widgets.HTML("Based on the Keys"),
            self.selector_group,
            self.add_selector_button,
        ]

    def create_selector(self, show_delete_button=None, **kwargs):
        return KeyPair(
            list(self.dataframes["left"].columns),
            list(self.dataframes["right"].columns),
            selector_group=self,
            show_delete_button=show_delete_button,
        )

    def change_df(self, side, df):
        self.dataframes[side] = df
        self._update_key_pair_options()

    def _update_key_pair_options(self):
        for index, key_pair in enumerate(self.get_selectors()):
            for side in ["left", "right"]:
                key_pair.set_options(
                    side,
                    list(self.dataframes[side].columns),
                    focus_left_after_init=(index == 0),
                )
            key_pair.render()

    def get_keys(self, side="left"):
        return list(
            set([selector.dropdowns[side].value for selector in self.get_selectors()])
        )


class TableSelector(widgets.VBox):
    """Manages the table selection section ("Merge between X and Y")."""

    def __init__(self, transformation, symbols):
        super().__init__()
        self.transformation = transformation
        self.df = self.transformation.get_df()

        candidates = [
            key for key in symbols.keys() if isinstance(symbols[key], pd.DataFrame)
        ]
        self.df_dict = {
            name: symbols[name] for name in candidates if not name.startswith("_")
        }

        self.left_df_dropdown = Singleselect(
            options=["Current dataframe"],
            value="Current dataframe",
            set_soft_value=True,
            enabled=False,
            width="sm",
        )

        self.right_df_dropdown = Singleselect(
            options=list(self.df_dict.keys()), set_soft_value=True, width="sm"
        )

        def update_right_df(widget):
            self.change_df("right", self.df_dict[widget.value])
            self.transformation.update_columns_selector()

        self.right_df_dropdown.on_change(update_right_df)

        self.children = [
            widgets.HTML("Between the dataframes"),
            widgets.HBox(
                [self.left_df_dropdown, widgets.HTML(" and "), self.right_df_dropdown]
            ),
        ]

    def get_dataframes(self):
        return [self.df, self.df_dict[self.right_df_dropdown.value]]

    def get_name_of_right_dataframe(self):
        return self.right_df_dropdown.value

    def set_change_df_callback(self, callback):
        self.change_df = callback


KEEP_ALL_COLUMNS = "Keep all columns"
SELECT_SOME_COLUMNS = "Select some columns"
DROP_SOME_COLUMNS = "Drop some columns"


class ColumnsSelector(widgets.VBox):
    """Allows selecting a few columns of the right dataframe."""

    def __init__(self, transformation, df):
        super().__init__()
        self.transformation = transformation
        self.df = df

        self.type = Singleselect(
            options=[KEEP_ALL_COLUMNS, SELECT_SOME_COLUMNS, DROP_SOME_COLUMNS],
            set_soft_value=True,
            width="lg",
            on_change=self.update_layout,
        )

        self.columns_outlet = widgets.HBox()

        self._create_columns()

        self.children = [self.type, self.columns_outlet]

    def _create_columns(self):
        self.columns = Multiselect(
            options=list(self.df.columns), focus_after_init=True, width="lg"
        )

    def update_layout(self, *args):
        if self.type.value == KEEP_ALL_COLUMNS:
            self.columns_outlet.children = []
        else:
            self.columns_outlet.children = [self.columns]

    def get_subset_code(self, needed_columns):
        if self.type.value == KEEP_ALL_COLUMNS:
            return ""

        if self.type.value == SELECT_SOME_COLUMNS:
            selected_columns = self.columns.value
            to_be_added = [
                column for column in needed_columns if column not in selected_columns
            ]
            final_columns = to_be_added + selected_columns
            return f"[{final_columns}]"

        if self.type.value == DROP_SOME_COLUMNS:
            to_be_dropped = [
                column for column in self.columns.value if column not in needed_columns
            ]
            return f".drop(columns={to_be_dropped})"


class JoinTransformation(Transformation):
    """Join two dataframes."""

    def __init__(self, *args, column=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.symbols = self.df_manager.symbols
        self.join_type_dropdown = Singleselect(
            options=[
                ("Inner Join", "inner"),
                ("Left Join", "left"),
                ("Right Join", "right"),
                ("Outer Join", "outer"),
            ],
            placeholder="Join type",
            focus_after_init=True,
            set_soft_value=True,
            width="md",
        )

        self.table_selector = TableSelector(self, self.symbols)
        left_df, right_df = self.table_selector.get_dataframes()
        self.key_selector = KeyPairSection(left_df, right_df)
        self.table_selector.set_change_df_callback(self.key_selector.change_df)

        self.columns_selector_outlet = widgets.VBox()
        self.update_columns_selector()

    def update_columns_selector(self):
        _, right_df = self.table_selector.get_dataframes()
        right_df_name = self.table_selector.get_name_of_right_dataframe()

        self.columns_selector = ColumnsSelector(self, right_df)
        self.columns_selector_outlet.children = [
            widgets.HTML(f"and, from {right_df_name}"),
            self.columns_selector,
        ]

    def render(self):
        self.set_title("Join dataframes")
        self.set_content(
            widgets.HTML("Perform"),
            self.join_type_dropdown,
            self.table_selector,
            self.key_selector,
            self.columns_selector_outlet,
            self.rename_df_group,
        )

    def get_description(self):
        join_label = self.join_type_dropdown.label
        df_right_name = self.table_selector.get_name_of_right_dataframe()

        left_keys = self.key_selector.get_keys("left")
        right_keys = self.key_selector.get_keys("right")
        keys_list = []
        for index, column in enumerate(left_keys):
            keys_list.append(f"{column}={right_keys[index]}")
        keys_string = ", ".join(keys_list)

        return f"<b>{join_label}</b> with {df_right_name} where {keys_string}"
        # eg Inner Join with left_df where Pclass=Pclass, Age=Age

    def _join_on_single_key(self):
        """Returns True if left and right keys match. We can simplify the code in this case."""
        return self.key_selector.get_keys("left") == self.key_selector.get_keys("right")

    def _get_key_code(self):
        left_keys = self.key_selector.get_keys("left")
        right_keys = self.key_selector.get_keys("right")
        if self._join_on_single_key():
            code = f"on={left_keys}"
        else:
            code = f"left_on={left_keys}, right_on={right_keys}"
        return code

    def get_exception_message(self, exception):
        if isinstance(exception, ValueError):
            return notification(
                """It seems like the columns of the two dataframes do not have the same data types.<br><br>
                Please make sure that the columns have the same or compatible data types. You might want to use <b>Change data type</b> for this""",
                type="error",
            )
        if isinstance(exception, KeyError):
            # The error is sometimes "KeyError: 'region'" and sometimes "KeyError: 'region' not in index"
            return notification(
                """It seems like one of the key columns does not exist any more in one of the dataframes. This can happen if you changed the dataframes while the user interface was still open.<br><br>
                Please close the "Join dataframes" window and open it again in order to refresh the user interface.""",
                type="error",
            )
        return None

    def get_code(self):
        df_right = self.table_selector.get_name_of_right_dataframe()

        subset = self.columns_selector.get_subset_code(
            needed_columns=self.key_selector.get_keys("right")
        )

        join = self.join_type_dropdown.value
        keys = self._get_key_code()

        return (
            f"{DF_NEW} = pd.merge({DF_OLD}, {df_right}{subset}, how='{join}', {keys})"
        )
        # eg df = pd.merge(df, left_df, how='inner', left_on=['Age', 'Pclass'], right_on=['Age', 'Pclass'])

    def reset_preview_columns_selection(self):
        return True
