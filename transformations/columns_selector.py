# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.helper import DF_OLD, BamboolibError, string_to_code

from bamboolib.widgets import Multiselect, Singleselect, Text


ALL_COLUMNS = "[All columns]"
COLUMNS_WITH_DTYPE = "[Columns with data type]"
COLUMNS_BY_REGEX = "[Columns that match regex]"

NUMERIC_COLUMNS = "[Numeric columns]"
STRING_OR_OBJECT_COLUMNS = "[String/Text or Object columns]"
STRING_COLUMNS = "[String-only columns]"
OBJECT_COLUMNS = "[Object-only columns]"
CATEGORY_COLUMNS = "[Categoric/Factor columns]"
INTEGER_COLUMNS = "[Integer columns]"
FLOAT_COLUMNS = "[Float columns]"
BOOLEAN_COLUMNS = "[Boolean columns]"
DATETIME_COLUMNS = "[Datetime columns]"
TIMEDELTA_COLUMNS = "[Timedelta columns]"

COLUMNS_THAT_START_WITH = "[Columns that start with]"
COLUMNS_THAT_END_WITH = "[Columns that end with]"
COLUMNS_THAT_CONTAIN = "[Columns that contain]"

TOP_OPTIONS = [COLUMNS_WITH_DTYPE, COLUMNS_BY_REGEX]

BOTTOM_OPTIONS = [
    NUMERIC_COLUMNS,
    STRING_OR_OBJECT_COLUMNS,
    STRING_COLUMNS,
    OBJECT_COLUMNS,
    CATEGORY_COLUMNS,
    INTEGER_COLUMNS,
    FLOAT_COLUMNS,
    BOOLEAN_COLUMNS,
    DATETIME_COLUMNS,
    TIMEDELTA_COLUMNS,
    COLUMNS_THAT_START_WITH,
    COLUMNS_THAT_END_WITH,
    COLUMNS_THAT_CONTAIN,
]


class SpecialSelector(widgets.VBox):
    def __init__(self, manager=None, on_change=lambda: None, **kwargs):
        self.manager = manager
        self.on_change = on_change
        super().__init__(**kwargs)

    @property
    def columns(self):
        columns = self.manager.transformation.eval_code(self.get_columns_code())
        return columns

    def focus_dropdown(self):
        return False

    def get_columns_code(self):
        return f"{self.get_df_code()}.columns"

    def get_df_code(self):
        raise NotImplementedError


class DropdownItemSpecialSelector(SpecialSelector):
    def focus_dropdown(self):
        return True


class AllColumns(DropdownItemSpecialSelector):
    def get_df_code(self):
        return f"{DF_OLD}"


"""
Helper objects that hold the code for selecting columns of a particular data type.

Attention: When selecting columns by data type, we currently get the columns of a data frame
with df.select_dtypes().columns. This creates a data subset first and then picks the column
names, which is inefficient.

Alternative codes for getting columns of certain data types could be:

df_master.columns[df_master.dtypes.map(lambda col: pd.api.types.<METHOD>(col))]
with <METHOD> one of is_numeric_dtype, is_object_dtype, is_categorical_dtype, is_string_dtype, is_datetime64_any_dtype, is_timedelta64_dtype
"""


class NumericColumns(DropdownItemSpecialSelector):
    def get_df_code(self):
        return f"{DF_OLD}.select_dtypes('number')"


class StringOrObjectColumns(DropdownItemSpecialSelector):
    def get_df_code(self):
        return f"{DF_OLD}.select_dtypes(['string', 'object'])"


class StringColumns(DropdownItemSpecialSelector):
    def get_df_code(self):
        return f"{DF_OLD}.select_dtypes('string')"


class ObjectColumns(DropdownItemSpecialSelector):
    def get_df_code(self):
        return f"{DF_OLD}.select_dtypes('object')"


class CategoryColumns(DropdownItemSpecialSelector):
    def get_df_code(self):
        return f"{DF_OLD}.select_dtypes('category')"


class IntegerColumns(DropdownItemSpecialSelector):
    def get_df_code(self):
        return f"{DF_OLD}.select_dtypes('int')"


class FloatColumns(DropdownItemSpecialSelector):
    def get_df_code(self):
        return f"{DF_OLD}.select_dtypes('float')"


class BooleanColumns(DropdownItemSpecialSelector):
    def get_df_code(self):
        return f"{DF_OLD}.select_dtypes('bool')"


class DatetimeColumns(DropdownItemSpecialSelector):
    def get_df_code(self):
        return f"{DF_OLD}.select_dtypes('datetime')"


class TimedeltaColumns(DropdownItemSpecialSelector):
    def get_df_code(self):
        return f"{DF_OLD}.select_dtypes('timedelta')"


DTYPE_OPTIONS = [
    ("Numeric", ["number"]),
    ("String/Text or Object", ["string", "object"]),
    ("String only", ["string"]),
    ("Object only", ["object"]),
    ("Categoric/Factor", ["category"]),
    ("Integer", ["int"]),
    ("Float", ["float"]),
    ("Boolean", ["bool"]),
    ("Datetime", ["datetime"]),
    ("Timedelta", ["timedelta"]),
]


class ColumnsWithDtype(SpecialSelector):
    """Handles "selecting columns by data type"."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.data_type = Singleselect(
            options=[item[0] for item in DTYPE_OPTIONS],
            placeholder="Data type",
            focus_after_init=True,
            set_soft_value=True,
            width="md",
            on_change=self.on_change,
        )

        self.children = [self.data_type]

    def get_df_code(self):
        dtypes = [item for item in DTYPE_OPTIONS if item[0] == self.data_type.value][0][
            1
        ]
        return f"{DF_OLD}.select_dtypes({dtypes})"


class ColumnsByRegex(SpecialSelector):
    """Handles "selecting columns matching regex pattern"."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.text = Text(
            placeholder="Regex, e.g. e$",
            focus_after_init=True,
            width="sm",
            execute=self.manager.transformation,
            on_change=self.on_change,
        )

        self.children = [self.text]

    def get_df_code(self):
        # df.filter(regex="") causes "TypeError: Must pass either `items`, `like`, or `regex`" (pandas 1.1.2)
        regex_pattern = "^$" if self.text.value == "" else self.text.value
        regex_pattern = string_to_code(regex_pattern)

        return f"{DF_OLD}.filter(regex={regex_pattern})"


class ColumnsByStringOperation(SpecialSelector):
    """
    Handles "select columns that start/end with / contain".

    The specific string operation used for selecting columns is defined by self's children.
    """

    string_operation = "TO BE OVERRIDEN"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.text = Text(
            placeholder="String, e.g. foo",
            focus_after_init=True,
            width="sm",
            execute=self.manager.transformation,
            on_change=self.on_change,
        )

        self.children = [self.text]

    def get_df_code(self):
        text_value = string_to_code(self.text.value)
        string_operation = self.__class__.string_operation
        return f"{DF_OLD}.loc[:, {DF_OLD}.columns.str.{string_operation}({text_value})]"

    def get_columns_code(self):
        text_value = string_to_code(self.text.value)
        string_operation = self.__class__.string_operation
        return (
            f"{DF_OLD}.columns[{DF_OLD}.columns.str.{string_operation}({text_value})]"
        )


class ColumnsThatStartWith(ColumnsByStringOperation):
    string_operation = "startswith"


class ColumnsThatEndWith(ColumnsByStringOperation):
    string_operation = "endswith"


class ColumnsThatContain(ColumnsByStringOperation):
    string_operation = "contains"


SELECTOR_OPTIONS = {
    ALL_COLUMNS: AllColumns,
    COLUMNS_BY_REGEX: ColumnsByRegex,
    COLUMNS_WITH_DTYPE: ColumnsWithDtype,
    NUMERIC_COLUMNS: NumericColumns,
    STRING_OR_OBJECT_COLUMNS: StringOrObjectColumns,
    STRING_COLUMNS: StringColumns,
    OBJECT_COLUMNS: ObjectColumns,
    CATEGORY_COLUMNS: CategoryColumns,
    INTEGER_COLUMNS: IntegerColumns,
    FLOAT_COLUMNS: FloatColumns,
    BOOLEAN_COLUMNS: BooleanColumns,
    DATETIME_COLUMNS: DatetimeColumns,
    TIMEDELTA_COLUMNS: TimedeltaColumns,
    COLUMNS_THAT_START_WITH: ColumnsThatStartWith,
    COLUMNS_THAT_END_WITH: ColumnsThatEndWith,
    COLUMNS_THAT_CONTAIN: ColumnsThatContain,
}


class ColumnsSelector(widgets.VBox):
    """
    A special dropdown that allows more complex selections which need additional input from the user.

    E.g. when the user selects "columns of data type", we ask for the data type with a separate input.
    """

    def __init__(
        self,
        transformation=None,
        show_all_columns=True,
        set_all_columns_as_default=False,
        width="md",
        focus_after_init=False,
        css_classes=[],
        on_change=lambda: None,
    ):
        """
        :param show_all_columns: Do you want to show the "Select all column" option in the dropdown?
        """
        super().__init__()
        self.transformation = transformation
        self.df = self.transformation.get_df()
        self.width = width

        self._options = []
        if show_all_columns or set_all_columns_as_default:
            self._options += [ALL_COLUMNS]
        self._options += TOP_OPTIONS
        self._options += list(self.df.columns)
        self._options += BOTTOM_OPTIONS

        self.on_change = on_change

        if set_all_columns_as_default:
            self._set_special_selector(
                special_name=ALL_COLUMNS, set_soft_value=True, css_classes=css_classes
            )
        else:
            self._create_multi_select(
                focus_after_init=focus_after_init, css_classes=css_classes
            )

    def has_special_selector(self):
        """Returns True if the user has selected a special selector."""
        return any(
            value in SELECTOR_OPTIONS.keys() for value in self._get_current_values()
        )

    def has_column_names(self):
        """Returns True if the user has selected one or more column names."""
        return not self.has_special_selector()

    def _get_current_values(self):
        """
        Helper for returning the selected options in the dropdown in the correct format.

        :return: list. The selected element(s).
        """
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
                self._create_multi_select(value=self._get_current_values())

        self.on_change()

    def _create_multi_select(self, value=[], focus_after_init=True, css_classes=[]):
        self._main_selector = Multiselect(
            placeholder="Choose column(s)",
            options=self._options,
            value=value,
            focus_after_init=focus_after_init,
            width=self.width,
            on_change=self._selection_changed,
            css_classes=css_classes,
        )

        self.children = [self._main_selector]

    def _set_special_selector(
        self, special_name=None, set_soft_value=False, css_classes=[]
    ):
        """Create the special selector."""
        if special_name is None:
            for value in self._get_current_values():
                if value in SELECTOR_OPTIONS.keys():
                    special_name = value
                    break

        self._special_selector = SELECTOR_OPTIONS[special_name](
            manager=self, on_change=self.on_change
        )

        self._main_selector = Singleselect(
            placeholder="Choose column(s)",
            options=self._options,
            value=special_name,
            focus_after_init=self._special_selector.focus_dropdown(),
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
            return list(self._special_selector.columns)

    @value.setter
    def value(self, value):
        # only supports setting column names via their name
        self._main_selector.value = value
        self._selection_changed()

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
