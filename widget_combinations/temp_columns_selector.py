# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


# ATTENTION: This class and file is meant to be refactored and changed before using it in more places.
# Please check if the `ColumnsSelector` already supports what you are looking for.
# Most likely, the usages of `TempColumnsSelector` should be replaced by `ColumnsSelector`.

import ipywidgets as widgets

from bamboolib.helper import DF_OLD, BamboolibError

from bamboolib.widgets import Multiselect, Singleselect

ALL_COLUMNS = "[All columns]"
FIRST_100_COLUMNS = "[First 100 columns]"
LAST_100_COLUMNS = "[Last 100 columns]"

TOP_OPTIONS = []
BOTTOM_OPTIONS = []


class SpecialSelector(widgets.VBox):
    def __init__(self, manager=None, **kwargs):
        self.manager = manager
        super().__init__(**kwargs)

    @property
    def columns(self):
        raise NotImplementedError

    def focus_dropdown(self):
        return False

    def get_columns_code(self):
        raise NotImplementedError

    def get_df_code(self):
        return f"{DF_OLD}[{self.get_columns_code()}]"


class DropdownItemSpecialSelector(SpecialSelector):
    def focus_dropdown(self):
        return True


class AllColumns(DropdownItemSpecialSelector):
    def get_df_code(self):
        # this is an exception where it is more efficient to not use the inheritance
        # because that would return df[df.columns] instead of just df
        return f"{DF_OLD}"

    def get_columns_code(self):
        return f"{DF_OLD}.columns"

    @property
    def columns(self):
        return self.manager.df.columns


class First100Columns(DropdownItemSpecialSelector):
    def get_columns_code(self):
        return f"{DF_OLD}.columns[0:100]"

    @property
    def columns(self):
        return self.manager.df.columns[0:100]


class Last100Columns(DropdownItemSpecialSelector):
    def get_columns_code(self):
        return f"{DF_OLD}.columns[-101:-1]"

    @property
    def columns(self):
        return self.manager.df.columns[-101:-1]


SELECTOR_OPTIONS = {
    ALL_COLUMNS: AllColumns,
    FIRST_100_COLUMNS: First100Columns,
    LAST_100_COLUMNS: Last100Columns,
}


class TempColumnsSelector(widgets.VBox):
    """
    Attention: This class is meant to be refactored and changed before using it in more places.
    Please check if the `ColumnsSelector` already supports what you are looking for.
    Most likely, the usages of TempColumnsSelector should be replaced by `ColumnsSelector`.

    A widget to select columns.
    The widget goes beyond just selecting multiple columns by name but also allows selectors like:
    All columns, First 100 columns, Last 100 columns
    """

    def __init__(
        self,
        df=None,
        width="md",
        selection=None,
        show_all_columns=True,
        show_first_and_last=False,
        multi_select_width=None,
        focus_after_init=False,
        css_classes=[],
        on_change=None,
    ):
        super().__init__()
        self.add_class("bamboolib-overflow-visible")

        self.df = df
        self.width = width
        if multi_select_width is None:
            self.multi_select_width = width
        else:
            self.multi_select_width = multi_select_width
        if not (show_first_and_last or show_all_columns):
            raise ValueError(
                "Either show_all_columns or show_first_and_last must be True"
            )
        self.on_change = on_change

        self._options = []
        if show_all_columns:
            self._options.append(ALL_COLUMNS)
        if show_first_and_last:
            self._options.append(FIRST_100_COLUMNS)
            self._options.append(LAST_100_COLUMNS)
        self._options += TOP_OPTIONS
        self._options += list(self.df.columns)
        self._options += BOTTOM_OPTIONS

        self.default_special_selector = (
            FIRST_100_COLUMNS if show_first_and_last else ALL_COLUMNS
        )

        if selection is None:
            self._set_special_selector(
                special_name=self.default_special_selector,
                set_soft_value=True,
                css_classes=css_classes,
                no_focus=True,
            )
        else:
            self.set_selection(selection)

    def has_special_selector(self):
        return any(
            value in SELECTOR_OPTIONS.keys() for value in self._get_current_values()
        )

    def has_column_names(self):
        return not self.has_special_selector()

    def _get_current_values(self):
        if self._main_selector.__class__ == Multiselect:
            values = self._main_selector.value
        else:
            values = [self._main_selector.value]
        return values

    def _selection_changed(self, *args):
        if self.has_special_selector():
            self._set_special_selector()
        else:
            if self._main_selector.__class__ != Multiselect:
                self._set_names_selector(value=self._get_current_values())
        if self.on_change is not None:
            self.on_change(self)

    def _set_names_selector(self, value=[], focus_after_init=True, css_classes=[]):
        self._main_selector = Multiselect(
            placeholder="Choose column(s)",
            options=self._options,
            value=value,
            focus_after_init=focus_after_init,
            width=self.multi_select_width,
            on_change=self._selection_changed,
            css_classes=css_classes,
        )

        self.children = [self._main_selector]

    def _set_special_selector(
        self, special_name=None, set_soft_value=False, css_classes=[], no_focus=False
    ):
        if special_name is None:
            for value in self._get_current_values():
                if value in SELECTOR_OPTIONS.keys():
                    special_name = value
                    break
        else:
            if special_name not in self._options:
                # in case we are trying to set all columns but only first x exist, we are recovering to first x
                special_name = self.default_special_selector

        self._special_selector = SELECTOR_OPTIONS[special_name](manager=self)

        self._main_selector = Singleselect(
            placeholder="Choose column(s)",
            options=self._options,
            value=special_name,
            focus_after_init=False,  # if no_focus else self._special_selector.focus_dropdown(),
            set_soft_value=set_soft_value,
            width=self.width,
            on_change=self._selection_changed,
            css_classes=["bamboolib-columns-selector-special"] + css_classes,
        )

        self.children = [self._main_selector, self._special_selector]

    @property
    def value(self):
        if self.has_column_names():
            return self._main_selector.value
        else:
            return self._special_selector.columns

    @value.setter
    def value(self, value):
        # only supports setting column names via their name
        self._main_selector.value = value

    def get_df_code(self):
        if self.has_column_names():
            if len(self._main_selector.value) == 0:
                raise BamboolibError(
                    "No columns are selected.<br>Please select one or multiple columns"
                )
            return f"{DF_OLD}[{self._main_selector.value}]"
        else:
            return self._special_selector.get_df_code()

    def get_columns_code(self):
        if self.has_column_names():
            return f"{self._main_selector.value}"
        else:
            return self._special_selector.get_columns_code()

    def get_selection(self):
        if self.has_column_names():
            return dict(type="column_names", value=self._main_selector.value)
        else:
            return dict(type=self._main_selector.value)

    def set_selection(self, selection):
        if selection["type"] == "column_names":
            some_names_exist = any(
                [value in self._options for value in selection["value"]]
            )
            if some_names_exist:
                # Multiselect will try to set as many values as possible
                self._set_names_selector(
                    value=selection["value"], focus_after_init=False
                )
            else:
                self._set_special_selector(special_name=self.default_special_selector)
        else:
            self._set_special_selector(special_name=selection["type"])
