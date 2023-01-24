# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import re
import pandas as pd
import ipywidgets as widgets

from bamboolib.helper import (
    DF_OLD,
    DF_NEW,
    replace_code_placeholder,
    log_action,
    guess_dataframe_name,
)
from bamboolib.widgets import Button
from bamboolib.config import get_option


LAST_LIST_ITEM = -1


def updates_live_code_export(function):
    """Decorator that updates the live code export."""

    def function_that_updates_live_code_export(self, *args, **kwargs):
        result = function(self, *args, **kwargs)
        self.update_live_code_export()
        return result

    return function_that_updates_live_code_export


def remove_html_tags(raw_html):
    """Remove HTML tags of a string."""
    # https://stackoverflow.com/questions/9662346/python-code-to-remove-html-tags-from-a-string
    cleanr = re.compile("<.*?>")
    cleantext = re.sub(cleanr, "", raw_html)
    return cleantext


class DfManager:
    """
        Manages events on the dataframe, e.g. the code export, name of the current df, dataframe normalizations,
        and transformation history.

        :param df: pandas.DataFrame to manage (i.e. to transform and sync with code export)
        :param df_name: string. Name of the dataframe, which can be found in `
    symbols`.
        :param setup_code: string or None. The code that is added to the code cell when DfManager is
            instantiated and not as a result of some execution.
        :param initial_user_code: string or None. The code that is in the user_cell before the DfManager takes
            over the control. This is important for the LiveCodeExport so that it knows which code to restore.
            Special cases: initial_user_code is None (during init) or "" (internally)
            DfManager will ask the Wrangler to determine the initial_user_code during the first code sync.

    """

    def __init__(
        self,
        df,
        symbols={},
        setup_code=None,
        df_name=None,
        initial_user_code=None,
        command_guid=None,
    ):
        super().__init__()
        self._initial_user_code = "" if initial_user_code is None else initial_user_code
        self._command_guid = "" if command_guid is None else command_guid
        if setup_code is None:
            self._setup_code = ""
        else:
            self._setup_code = setup_code.strip() + "\n"
        if len(symbols) == 0:
            from bamboolib.setup.user_symbols import get_user_symbols

            symbols = get_user_symbols()

        self.show_live_code_export = get_option("global.show_live_code_export")
        self.undo_levels = get_option("global.undo_levels")
        self.wrangler = None
        self.tab_section = None

        self._original_df = df
        self.original_df_preview_columns_selection = None

        if self._df_needs_normalization(df):
            # making a copy makes the display of the initial Wrangler very slow if the data is huge
            # other ideas:
            # - ask user if the df shall be normalized inplace or with copy
            df = df.copy()  # never alter the original df
        # always call the normalization method because it sets some internal state
        self.df = self._maybe_perform_normalization(df)

        self.symbols = symbols
        self._original_df_name = (
            guess_dataframe_name(df, symbols) if (df_name is None) else df_name
        )

        self.transformations = []
        self.redo_transformations = []

    def register_wrangler(self, wrangler):
        self.wrangler = wrangler

    def register_tab_section(self, tab_section):
        """
        :param tab_section: TabSection. Manages all tabs.
        """
        self.tab_section = tab_section

    def _maybe_normalize_transformation(self, transformation):
        # Hint: currently, each transformation creates a df copy decentrally if needed
        # this might result in unnecessary copies of the df but is an easier implementation

        did_normalize = any(
            [
                self._maybe_convert_series_to_frame_new(transformation),
                # column flattening needs to happen before reset_index, otherwise the names of the indices will have a trailing _
                self._maybe_flatten_columns_new(transformation),
                # maybe we want to have another reset_index logic here
                # because if the user filters, he might not always want to have his index reset
                # which in his case, would result in a new column
                # we might choose to skip this step here
                # or only reset named indices
                self._maybe_reset_index_new(transformation),
                self._maybe_turn_column_names_into_strings_new(transformation),
                self._maybe_rename_duplicate_column_names_new(transformation),
            ]
        )

        if did_normalize:
            transformation["description"] += " and, afterwards, normalized dataframe"

    def _df_needs_normalization(self, df):
        """We keep our dataframe in tidy format. If it's not, we need to normalize it."""
        return any(
            [
                isinstance(df, pd.Series),
                isinstance(df.columns, pd.MultiIndex),
                not self._is_valid_df_index(df),
                not self._all_columns_are_strings(df),
                self.has_duplicate_list_entries(df.columns),
            ]
        )

    def _maybe_perform_normalization(self, df):
        df = self._maybe_convert_series_to_frame(df)
        # column flattening needs to happen before reset_index, otherwise the names of the indices will have a trailing _
        df = self._maybe_flatten_columns(df)
        df = self._maybe_reset_index(df)
        df = self._maybe_turn_column_names_into_strings(df)
        df = self._maybe_rename_duplicate_column_names(df)
        return df

    def _maybe_convert_series_to_frame_new(self, transformation):
        did_normalize = False
        df = transformation["result_df"]

        if isinstance(df, pd.Series):
            did_normalize = True
            df = df.to_frame()
            transformation["result_df"] = df
            transformation["code"] += f"\n{DF_NEW} = {DF_NEW}.to_frame()"
        return did_normalize

    def _maybe_convert_series_to_frame(self, df):
        if isinstance(df, pd.Series):
            self._converted_to_frame = True
            df = df.to_frame()
        else:
            self._converted_to_frame = False
        return df

    def _maybe_flatten_columns_new(self, transformation):
        did_normalize = False
        df = transformation["result_df"]

        if isinstance(df.columns, pd.MultiIndex):
            did_normalize = True
            df = df.copy()

            df.columns = [
                "_".join([str(index) for index in multi_index])
                for multi_index in df.columns.ravel()
            ]

            transformation["result_df"] = df
            transformation[
                "code"
            ] += f"\n{DF_NEW}.columns = ['_'.join([str(index) for index in multi_index]) for multi_index in {DF_NEW}.columns.ravel()]"

        return did_normalize

    def _maybe_flatten_columns(self, df):
        if isinstance(df.columns, pd.MultiIndex):
            self._flattened_columns = True
            df.columns = [
                "_".join([str(index) for index in multi_index])
                for multi_index in df.columns.ravel()
            ]
        else:
            self._flattened_columns = False
        return df

    def _is_valid_df_index(self, df):
        # invalid indices
        is_named_index = df.index.name is not None
        is_multi_index = isinstance(df.index, pd.MultiIndex)
        is_datetime_index = pd.api.types.is_datetime64_any_dtype(df.index.dtype)
        is_invalid = is_named_index or is_multi_index or is_datetime_index

        # valid indices
        has_range_index = isinstance(df.index, pd.RangeIndex)
        # int_index is semantically the same as RangeIndex
        # for example created by pandas after a left join
        has_int_index = isinstance(df.index, pd.Int64Index)
        is_valid = has_range_index or has_int_index
        return is_valid and not is_invalid

    def _maybe_reset_index(self, df):
        if self._is_valid_df_index(df):
            self._did_reset_index = False
        else:
            self._did_reset_index = True
            df = df.reset_index()
        return df

    def _maybe_reset_index_new(self, transformation):
        did_normalize = False
        df = transformation["result_df"]

        if self._is_valid_df_index(df):
            pass
        else:
            did_normalize = True
            df = df.reset_index()
            transformation["result_df"] = df
            transformation["code"] += f"\n{DF_NEW} = {DF_NEW}.reset_index()"
        return did_normalize

    def _all_columns_are_strings(self, df):
        return all([isinstance(column, str) for column in df.columns])

    def _maybe_turn_column_names_into_strings_new(self, transformation):
        did_normalize = False
        df = transformation["result_df"]

        if self._all_columns_are_strings(df):
            pass
        else:
            did_normalize = True
            df = df.copy()

            df.columns = [str(column) for column in df.columns]

            transformation["result_df"] = df
            transformation[
                "code"
            ] += f"\n{DF_NEW}.columns = [str(column) for column in {DF_NEW}.columns]"
        return did_normalize

    def _maybe_turn_column_names_into_strings(self, df):
        if self._all_columns_are_strings(df):
            self._turned_column_names_into_strings = False
        else:
            self._turned_column_names_into_strings = True
            df.columns = [str(column) for column in df.columns]
        return df

    def _maybe_rename_duplicate_column_names_new(self, transformation):
        did_normalize = False
        df = transformation["result_df"]

        if self.has_duplicate_list_entries(df.columns):
            did_normalize = True
            df = df.copy()

            unique_column_names = self.create_unique_column_names(df.columns)
            df.columns = unique_column_names

            transformation["result_df"] = df
            transformation["code"] += f"\n{DF_NEW}.columns = {unique_column_names}"
        return did_normalize

    def _maybe_rename_duplicate_column_names(self, df):
        if self.has_duplicate_list_entries(df.columns):
            self._renamed_duplicate_columns = True
            self._renamed_column_names = self.create_unique_column_names(df.columns)
            df.columns = self._renamed_column_names
        else:
            self._renamed_duplicate_columns = False
        return df

    def has_duplicate_list_entries(self, list_):
        return len(list_) != len(set(list_))

    def create_unique_column_names(self, duplicate_columns):
        unique_columns = []

        for old_column in duplicate_columns:
            fudge = 1
            new_column = old_column

            while new_column in unique_columns:
                fudge += 1
                new_column = "{}_{}".format(old_column, fudge)

            unique_columns.append(new_column)
        return unique_columns

    def _df_was_normalized(self):
        return (
            self._converted_to_frame
            or self._flattened_columns
            or self._did_reset_index
            or self._turned_column_names_into_strings
            or self._renamed_duplicate_columns
        )

    def _user_added_transformations(self):
        return len(self.transformations) > 0

    def undo_is_possible(self):
        """Returns True if undo is possible. If it returns False, the undo button is disabled."""
        return self._user_added_transformations() and (
            self.undo_levels > len(self.redo_transformations)
        )

    def redo_is_possible(self):
        return len(self.redo_transformations) > 0

    def get_current_df(self):
        if self._user_added_transformations():
            return self.transformations[-1].result["result_df"]
            # LATER: if the result_df does not exist, we can derive it based on the previous steps?
        else:
            return self.df  # this is already potentially normalized

    def get_penultimate_df(self):
        if len(self.transformations) >= 2:
            penultimate_index = len(self.transformations) - 2
            return self.transformations[penultimate_index].result["result_df"]
        else:
            return self.df  # this is already potentially normalized

    def render_steps(self):
        """Render the transformation steps. They're e.g. displayed in the Transformation history view."""
        if self._user_added_transformations() or self._df_was_normalized():
            descriptions = []

            descriptions = self._maybe_add_normalization_descriptions(descriptions)
            descriptions = self._maybe_add_user_transformation_descriptions(
                descriptions
            )

            steps = widgets.VBox(descriptions)
        else:
            steps = widgets.HTML(
                "Currently, there is nothing to show. Please add some transformations"
            )
        return steps

    def _maybe_add_user_transformation_descriptions(self, descriptions):
        if self._df_was_normalized() and self._user_added_transformations():
            descriptions += [widgets.HTML("<b>Manual user transformations:</b>")]

        descriptions += [
            widgets.HTML(transformation.result["description"])
            for transformation in self.transformations
        ]

        if self.undo_is_possible():
            edit_button = Button(
                description="Edit last step", icon="pencil", style="primary"
            )
            edit_button.on_click(
                lambda _: log_action(
                    "general", "HistoryView", "click edit last transformation button"
                )
            )
            edit_button.on_click(self._open_edit_last_transformation)
            descriptions.append(edit_button)
        return descriptions

    def _open_edit_last_transformation(self, *args, **kwargs):
        self.transformations[LAST_LIST_ITEM].add_to(self.wrangler.side_window_outlet)

    def _maybe_add_normalization_descriptions(self, descriptions):
        if self._df_was_normalized():
            descriptions += [widgets.HTML("<b>Automatic dataframe normalization:</b>")]
        if self._converted_to_frame:
            descriptions += [
                widgets.HTML("Normalize series via converting to dataframe")
            ]
        if self._flattened_columns:
            descriptions += [
                widgets.HTML("Normalize columns via flattening multi-index columns")
            ]
        if self._did_reset_index:
            descriptions += [widgets.HTML("Normalize row index via reset")]
        if self._turned_column_names_into_strings:
            descriptions += [
                widgets.HTML("Normalize column names via converting them into strings")
            ]
        if self._renamed_duplicate_columns:
            descriptions += [
                widgets.HTML("Normalize column names via renaming duplicate names")
            ]
        return descriptions

    def _notify_df_did_change(self):
        """Notify all relevant components that the data has changed."""
        if self.wrangler is not None:
            self.wrangler.df_did_change()
        if self.tab_section is not None:
            self.tab_section.df_did_change()

    @updates_live_code_export
    def update_transformation(self, transformation):
        self.redo_transformations = []

        self._maybe_normalize_transformation(transformation.result)

        if self.is_new_transformation(transformation):
            if len(self.transformations) > self.undo_levels:
                # release the reference to the dataframe that cannot be recovered any more
                self.transformations[-(self.undo_levels + 1)].result["result_df"] = None
            self.transformations.append(transformation)
        self._notify_df_did_change()

    def is_new_transformation(self, transformation):
        if len(self.transformations) < 1:
            return True
        return self.transformations[LAST_LIST_ITEM] is not transformation

    @updates_live_code_export
    def undo(self):
        self._try_to_move_last_item_to_another_list(
            origin=self.transformations, target=self.redo_transformations
        )
        self._notify_df_did_change()

    @updates_live_code_export
    def redo(self):
        self._try_to_move_last_item_to_another_list(
            origin=self.redo_transformations, target=self.transformations
        )
        self._notify_df_did_change()

    def _maybe_update_user_symbols(self):
        if self.show_live_code_export and self._user_added_transformations():
            for transformation in self.transformations:
                df_name = transformation.result["new_df_name"]
                df = transformation.result["result_df"]
                self.symbols[df_name] = df
        else:
            df_name = self._original_df_name
            df = self._original_df
            self.symbols[df_name] = df

    def _try_to_move_last_item_to_another_list(self, origin, target):
        """Helper to handle undo/redo transformation events."""
        try:
            # if the user clicks the button faster then the app can render, there is a list index error
            last_item = origin[-1]

            # only continue if there was no error:
            del origin[-1]  # removes last item
            target.append(last_item)
        except:
            pass

    def get_setup_and_transformations_code(self):
        """
        Helper that returns the full code for all the stuff that has been done to the dataframe.
        Currently, the full code contains imports for pandas and numpy, setup code (e.g. from the data loader
        plugin) and transformations code (this includes potential normalization).
        """
        setup_code = self._setup_code
        transformations_code = self.get_transformations_code()
        if (setup_code == "") and (transformations_code == ""):
            return ""
        else:
            imports_code = "import pandas as pd; import numpy as np\n"
            return imports_code + setup_code + transformations_code

    def get_transformations_code(self):
        code = ""

        code = self._maybe_add_initial_normalization_code(code)
        code = replace_code_placeholder(code, old_df_name=self._original_df_name)

        for transformation in self.transformations:
            new_code = transformation.result["code"]
            new_code += "\n"

            new_code = replace_code_placeholder(
                new_code,
                old_df_name=transformation.result["old_df_name"],
                new_df_name=transformation.result["new_df_name"],
            )

            if get_option("global.export_transformation_descriptions"):
                description = remove_html_tags(transformation.result["description"])
                new_code = f"# Step: {description}\n{new_code}\n"

            code += new_code

        # Don't add the df again because otherwise we nudge the people to execute the cell again
        # AND afterwards do more transformations which then cannot be executed in the same cell any more
        # because the pandas operations are usually not idempotent
        # code += DF_OLD
        return code

    def _maybe_add_initial_normalization_code(self, code):
        """Maybe adds initial normalization code to code export."""
        if self._converted_to_frame:
            code += f"{DF_OLD} = {DF_OLD}.to_frame()\n"
        if self._flattened_columns:
            code += f'{DF_OLD}.columns = ["_".join([str(index) for index in multi_index]) for multi_index in {DF_OLD}.columns.ravel()]\n'
        if self._did_reset_index:
            code += f"{DF_OLD} = {DF_OLD}.reset_index()\n"
        if self._turned_column_names_into_strings:
            code += f"{DF_OLD}.columns = [str(column) for column in {DF_OLD}.columns]\n"
        if self._renamed_duplicate_columns:
            code += f"{DF_OLD}.columns = {self._renamed_column_names}\n"
        return code

    def update_live_code_export(self):
        self._update_jupyter_cell()
        self._maybe_update_user_symbols()

    def _update_jupyter_cell(self):
        """Writes the current code export to the jupyter cell."""
        if self.show_live_code_export:
            code = self.get_setup_and_transformations_code()
            if code != "":
                code += f"{self.get_current_df_name()}"
        else:
            code = ""  # remove code export

        if self.wrangler is not None:
            self.wrangler.grid.send(
                {
                    "type": "bam_live_code_export",
                    "code_export": code,
                    "initial_user_code": self._initial_user_code,
                    "command_guid": self._command_guid,
                }
            )

    def set_initial_user_code(self, code):
        self._initial_user_code = code

    def get_initial_user_code(self):
        return self._initial_user_code

    def set_command_guid(self, command_guid):
        self._command_guid = command_guid

    def set_preview_columns_selection(self, selection):
        if self._user_added_transformations():
            self.transformations[LAST_LIST_ITEM].result[
                "preview_columns_selection"
            ] = selection
        else:
            self.original_df_preview_columns_selection = selection

    def get_preview_columns_selection(self):
        if self._user_added_transformations():
            # later, when we are trying to add names to the selection,
            # we might need to access the last preview_columns_selection in case of an edit
            # otherwise, always adding to the current/last selection is not idempotent any more
            return self.transformations[LAST_LIST_ITEM].result[
                "preview_columns_selection"
            ]
        else:
            return self.original_df_preview_columns_selection

    def get_current_df_name(self):
        if self._user_added_transformations():
            name = self.transformations[LAST_LIST_ITEM].result["new_df_name"]
        else:
            name = self._original_df_name
        return name

    def get_penultimate_df_name(self):
        if len(self.transformations) >= 2:
            penultimate_index = len(self.transformations) - 2
            return self.transformations[penultimate_index].result["new_df_name"]
        else:
            return self._original_df_name

    def user_imported(self, symbol):
        """
        Returns True if the user imported a library

        :param symbol: symbol to import, NOT string.

        Example:
        print("import pandas as pd") if not self.user_imported(pd)
        """
        return any([symbol is value for name, value in self.symbols.items()])

    def get_symbols_with_masked_df(self, df_mask=None):
        """Helper method used for the custom code transformation."""
        if df_mask is None:
            df_mask = self.get_current_df()

        symbols = self.symbols.copy()

        # the following only works if there is only 1 df that is used (and there might be multiple references to it)
        # # overwrite symbol references in order to reference to the df_mask and not to the original df
        # df_names = get_dataframe_variable_names()
        # for variable_name in df_names:
        #     symbols[variable_name] = df_mask

        # only mask the current df because this is the only one that the user should use
        symbols[self.get_current_df_name()] = df_mask
        # if we want to mask the other dfs based on the virtual state of the user
        # then we need to determine the current df names in the transformations
        # and assign them their last result_df
        return symbols
