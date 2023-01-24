# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


from pandas.api.types import (
    is_numeric_dtype,
    is_object_dtype,
    is_datetime64_any_dtype,
    is_bool_dtype,
    is_categorical_dtype,
    is_string_dtype,
)

import re
import math
import pandas as pd
import ipywidgets as widgets

from bamboolib.helper import (
    Transformation,
    list_to_string,
    DF_OLD,
    DF_NEW,
    log_error,
    BamboolibError,
    string_to_code,
)

from bamboolib.widgets import (
    Singleselect,
    Multiselect,
    Text,
    Button,
    BamAutocompleteTextV1,
)

from bamboolib.transformations.base_components import SelectorGroupMixin, SelectorMixin

from bamboolib.transformations.column_formula_transformation import (
    _replace_column_names,
)


MAX_UNIQUE_COLUMN_VALUES_FOR_DROPDOWN = 100_000

AND_CONNECTOR_STRING = "&"
OR_CONNECTOR_STRING = "|"

CONTAINS = "contains"


class ConditionMixin:
    """
    Base class for handling a filter condition.

    :param description_template: string template for the description of a filter condition.
    :param code_template: string code template for the filter condition.
    """

    def __init__(
        self,
        condition_row,
        description_template="",
        code_template="",
        first_render=True,
        **kwargs,
    ):
        super().__init__()
        self.condition_row = condition_row
        self.df = condition_row.df
        self.column = condition_row.column
        self.description_template = description_template
        self.code_template = code_template
        self.focus_after_init = not first_render

    def is_valid_condition(self):
        return True

    def get_description(self):
        raise NotImplementedError

    def get_code(self):
        raise NotImplementedError

    def test_set_value(self, value):
        # This is not always needed because it is currently only used for tests
        raise NotImplementedError

    def value_is_not_empty(self, value, value_name="textfield"):
        if value == "":
            raise BamboolibError(f"The {value_name} is empty.<br>Please insert a value")
        else:
            return True


class SimpleDropdownDefaultCondition(ConditionMixin, widgets.VBox):
    """Filter condition that needs no additional input, e.g. select where X is missing."""

    def get_description(self):
        return self.description_template % self.column

    def get_code(self):
        return self.code_template % string_to_code(self.column)


class SimpleTextfieldCondition(ConditionMixin, widgets.VBox):
    """Filter condition that needs a text input, e.g. select rows that start with 'X'."""

    def __init__(self, *args, value="", **kwargs):
        super().__init__(*args, **kwargs)

        self.textfield = Text(
            value=value,
            placeholder="value",
            focus_after_init=self.focus_after_init,
            execute=self.condition_row,
        )
        self.children = [self.textfield]

    def is_valid_condition(self):
        return self.value_is_not_empty(self.textfield.value)

    def get_description(self):
        return self.description_template % (self.column, self.textfield.value)

    def get_code(self):
        text = self.textfield.value
        text = text.replace("'", "\\'")
        return self.code_template % (string_to_code(self.column), text)

    def test_set_value(self, value):
        self.textfield.value = value


class FormulaCondition(ConditionMixin, widgets.VBox):
    """
    Filter condition that needs a formula (i.e. column name autocompletion) input, e.g.
    select rows where age != age_mean.
    """

    def __init__(self, *args, value="", **kwargs):
        super().__init__(*args, **kwargs)

        self.column_names = self.df.columns.tolist()

        self.formula_input = BamAutocompleteTextV1(
            focus_after_init=self.focus_after_init,
            placeholder="Value",
            column_names=self.column_names,
            margin_top=2,
            nrows=1,
        )
        # Executes the FilterTransformation when enterkey is pressed
        self.formula_input.on_submit(lambda _: self.condition_row.execute())

        self.children = [self.formula_input]

    def _parse_formula(self, formula: str) -> None:
        if formula == "":
            return

        parsed_formula = _replace_column_names(formula, self.column_names)
        return parsed_formula

    def is_valid_condition(self) -> bool:
        return self.value_is_not_empty(self.formula_input.value)

    def get_description(self) -> str:
        return self.description_template % (self.column, self.formula_input.value)

    def get_code(self) -> str:
        parsed_formula = self._parse_formula(self.formula_input.value)
        return self.code_template % (string_to_code(self.column), parsed_formula)

    def test_set_value(self, value):
        self.formula_input.value = str(value)


class ContainsFilterTextfieldCondition(ConditionMixin, widgets.VBox):
    """
    Filter condition "select rows that contain 'X'".

    This one is different from :class:`SimpleTextfieldCondition` as it allows regular expressions.
    """

    def __init__(self, *args, value="", **kwargs):
        super().__init__(*args, **kwargs)

        self.textfield = Text(
            value=value,
            placeholder="text",
            focus_after_init=self.focus_after_init,
            execute=self.condition_row,
        )

        self.case_sensitive_checkbox = widgets.Checkbox(
            value=False, description="case-sensitive"
        )
        self.case_sensitive_checkbox.add_class("bamboolib-checkbox")

        self.regexp_checkbox = widgets.Checkbox(
            value=False, description="regular expression"
        )
        self.regexp_checkbox.add_class("bamboolib-checkbox")

        self.children = [
            widgets.VBox(
                [self.textfield, self.case_sensitive_checkbox, self.regexp_checkbox]
            )
        ]

    def is_valid_condition(self):
        return self.value_is_not_empty(self.textfield.value)

    def get_description(self):
        if self.case_sensitive_checkbox.value:
            flag_info = "case-sensitive"
        else:
            flag_info = "not case-sensitive"
        if self.regexp_checkbox.value:
            flag_info += ", regular expression"
        flag_info = "(%s)" % flag_info
        return self.description_template % (
            self.column,
            self.textfield.value,
            flag_info,
        )

    def get_code(self):
        text = self.textfield.value
        text = text.replace("'", "\\'")
        case_sensitive = self.case_sensitive_checkbox.value
        is_regex = self.regexp_checkbox.value
        return self.code_template % (
            string_to_code(self.column),
            text,
            case_sensitive,
            is_regex,
        )


class DatetimeTextfieldCondition(ConditionMixin, widgets.VBox):
    """Filter condition for datetime columns."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.textfield = Text(
            value="",
            placeholder="2020-12-31 22:58:10",
            focus_after_init=self.focus_after_init,
            execute=self.condition_row,
        )
        self.children = [self.textfield]

    def is_valid_condition(self):
        return self.value_is_not_empty(self.textfield.value)

    def get_description(self):
        text_value = self.textfield.value.strip()
        return self.description_template % (self.column, text_value)

    def get_code(self):
        text_value = self.textfield.value.strip()
        return self.code_template % (string_to_code(self.column), text_value)


class TextfieldSelector(SelectorMixin, widgets.HBox):
    """Tiny text input mixin. Helper for :class:`TextfieldSelectorGroup`."""

    def __init__(self, focus_after_init=False, **kwargs):
        super().__init__(**kwargs)

        self.text_input = Text(focus_after_init=focus_after_init, width="xs")

        self.children = [self.text_input, self.delete_selector_button]


class TextfieldSelectorGroup(SelectorGroupMixin, widgets.VBox):
    """
    Manages instances of class TextfieldSelector.

    We use this class in the "has values" filter condition when the filtered column has too many
    unique values for our selectize to handle.
    """

    def __init__(self, *args, focus_after_init=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.focus_after_init = focus_after_init

        self.init_selector_group(add_button_text="add value")

        self.children = [self.selector_group, self.add_selector_button]

    def get_initial_selector(self):
        return self.create_selector(
            show_delete_button=False, focus_after_init=self.focus_after_init
        )

    def get_new_selector(self):
        return self.create_selector(show_delete_button=True, focus_after_init=True)

    def create_selector(
        self, show_delete_button=None, focus_after_init=False, **kwargs
    ):
        return TextfieldSelector(
            selector_group=self,
            show_delete_button=show_delete_button,
            focus_after_init=focus_after_init,
            **kwargs,
        )

    def get_value_list(self):
        text_values = [selector.text_input.value for selector in self.get_selectors()]
        return [text for text in text_values if text != ""]


class SelectizeValueSelector(Multiselect):
    """
    We use this class in the "has values" filter condition when the filtered column has not too many
    unique values for our selectize to handle (the default).
    """

    def get_value_list(self):
        return self.value


class MultiColumnValuesCondition(ConditionMixin, widgets.VBox):
    """Filter condition "select where column has value(s) x, y, z.""" ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        series = self.df[self.column]
        if series.nunique() < MAX_UNIQUE_COLUMN_VALUES_FOR_DROPDOWN:
            self.selector_group = SelectizeValueSelector(
                options=self._get_value_options(series),
                width="md",
                focus_after_init=self.focus_after_init,
            )
        else:
            self.selector_group = TextfieldSelectorGroup(
                focus_after_init=self.focus_after_init
            )

        self.children = [self.selector_group]

    def _get_value_options(self, series):
        """Get the unique values in the column `series`."""
        if str(series.dtype) == "category":
            unique_values = series.cat.categories.tolist()
            return [(str(item), item) for item in unique_values]
        else:
            # dtype is object/string
            unique_values = list(series.unique())
            # there is a small chance that the column contains non-string objects
            # this is the case when the dtype was object and most but not all values are strings
            return [item for item in unique_values if isinstance(item, str)]

    def _get_value_list(self):
        """Get the values entered/selected by the user."""
        return self.selector_group.get_value_list()

    def is_valid_condition(self):
        if len(self._get_value_list()) > 0:
            return True
        else:
            raise BamboolibError(
                f"The multiselect input is empty.<br>Please select at least one value"
            )

    def get_description(self):
        unquoted_value_list = list_to_string(self._get_value_list(), quoted=False)
        return self.description_template % (self.column, unquoted_value_list)

    def get_code(self):
        value_list = []
        for value in self._get_value_list():
            if isinstance(value, str):
                value = value.replace("'", "\\'")
            value_list.append(value)
        return self.code_template % (string_to_code(self.column), value_list)


"""
Filter configs. Used to populate the filter UI.

All potential filter contitions and the classes that handle them plus extra required options.
"""

STARTS_WITH_LABEL = "starts with"
STRING_DROPDOWN_OPTIONS = {
    "has value(s)": {
        "embeddable_class": MultiColumnValuesCondition,
        "embeddable_kwargs": {
            "description_template": "%s is one of: %s",
            "code_template": f"{DF_OLD}[%s].isin(%s)",
        },
    },
    STARTS_WITH_LABEL: {
        "embeddable_class": SimpleTextfieldCondition,
        "embeddable_kwargs": {
            "description_template": "%s starts with %s",
            "code_template": f"{DF_OLD}[%s].str.startswith('%s', na=False)",
        },
    },
    CONTAINS: {
        "embeddable_class": ContainsFilterTextfieldCondition,
        "embeddable_kwargs": {
            "description_template": "%s contains %s %s",
            "code_template": f"{DF_OLD}[%s].str.contains('%s', case=%s, regex=%s, na=False)",
        },
    },
    "ends with": {
        "embeddable_class": SimpleTextfieldCondition,
        "embeddable_kwargs": {
            "description_template": "%s ends with %s",
            "code_template": f"{DF_OLD}[%s].str.endswith('%s', na=False)",
        },
    },
    "is missing": {
        "embeddable_class": SimpleDropdownDefaultCondition,
        "embeddable_kwargs": {
            "description_template": "%s is missing",
            "code_template": f"{DF_OLD}[%s].isna()",
        },
    },
    "is not missing": {
        "embeddable_class": SimpleDropdownDefaultCondition,
        "embeddable_kwargs": {
            "description_template": "%s is not missing",
            "code_template": f"{DF_OLD}[%s].notna()",
        },
    },
}


DATETIME_DROPDOWN_OPTIONS = {
    "<": {
        "embeddable_class": DatetimeTextfieldCondition,
        "embeddable_kwargs": {
            "description_template": "%s < %s",
            "code_template": f"{DF_OLD}[%s] < '%s'",
        },
    },
    "<=": {
        "embeddable_class": DatetimeTextfieldCondition,
        "embeddable_kwargs": {
            "description_template": "%s <= %s",
            "code_template": f"{DF_OLD}[%s] <= '%s'",
        },
    },
    "==": {
        "embeddable_class": DatetimeTextfieldCondition,
        "embeddable_kwargs": {
            "description_template": "%s == %s",
            "code_template": f"{DF_OLD}[%s] == '%s'",
        },
    },
    "!=": {
        "embeddable_class": DatetimeTextfieldCondition,
        "embeddable_kwargs": {
            "description_template": "%s != %s",
            "code_template": f"{DF_OLD}[%s] != %s",
        },
    },
    ">": {
        "embeddable_class": DatetimeTextfieldCondition,
        "embeddable_kwargs": {
            "description_template": "%s > %s",
            "code_template": f"{DF_OLD}[%s] > '%s'",
        },
    },
    ">=": {
        "embeddable_class": DatetimeTextfieldCondition,
        "embeddable_kwargs": {
            "description_template": "%s >= %s",
            "code_template": f"{DF_OLD}[%s] >= '%s'",
        },
    },
    "is missing": {
        "embeddable_class": SimpleDropdownDefaultCondition,
        "embeddable_kwargs": {
            "description_template": "%s is missing",
            "code_template": f"{DF_OLD}[%s].isna()",
        },
    },
    "is not missing": {
        "embeddable_class": SimpleDropdownDefaultCondition,
        "embeddable_kwargs": {
            "description_template": "%s is not missing",
            "code_template": f"{DF_OLD}[%s].notna()",
        },
    },
}


GREATER_THAN_LABEL = ">"
NUMERIC_DROPDOWN_OPTIONS = {
    "<": {
        "embeddable_class": FormulaCondition,
        "embeddable_kwargs": {
            "description_template": "%s < %s",
            "code_template": f"{DF_OLD}[%s] < %s",
        },
    },
    "<=": {
        "embeddable_class": FormulaCondition,
        "embeddable_kwargs": {
            "description_template": "%s <= %s",
            "code_template": f"{DF_OLD}[%s] <= %s",
        },
    },
    "==": {
        "embeddable_class": FormulaCondition,
        "embeddable_kwargs": {
            "description_template": "%s == %s",
            "code_template": f"{DF_OLD}[%s] == %s",
        },
    },
    "!=": {
        "embeddable_class": FormulaCondition,
        "embeddable_kwargs": {
            "description_template": "%s != %s",
            "code_template": f"{DF_OLD}[%s] != %s",
        },
    },
    GREATER_THAN_LABEL: {
        "embeddable_class": FormulaCondition,
        "embeddable_kwargs": {
            "description_template": "%s > %s",
            "code_template": f"{DF_OLD}[%s] > %s",
        },
    },
    ">=": {
        "embeddable_class": FormulaCondition,
        "embeddable_kwargs": {
            "description_template": "%s >= %s",
            "code_template": f"{DF_OLD}[%s] >= %s",
        },
    },
    "is missing": {
        "embeddable_class": SimpleDropdownDefaultCondition,
        "embeddable_kwargs": {
            "description_template": "%s is missing",
            "code_template": f"{DF_OLD}[%s].isna()",
        },
    },
    "is not missing": {
        "embeddable_class": SimpleDropdownDefaultCondition,
        "embeddable_kwargs": {
            "description_template": "%s is not missing",
            "code_template": f"{DF_OLD}[%s].notna()",
        },
    },
}


BOOLEAN_DROPDOWN_OPTIONS = {
    "is True": {
        "embeddable_class": SimpleDropdownDefaultCondition,
        "embeddable_kwargs": {
            "description_template": "%s is True",
            "code_template": f"{DF_OLD}[%s] == True",
        },
    },
    "is False": {
        "embeddable_class": SimpleDropdownDefaultCondition,
        "embeddable_kwargs": {
            "description_template": "%s is False",
            "code_template": f"{DF_OLD}[%s] == False",
        },
    },
    "is missing": {
        "embeddable_class": SimpleDropdownDefaultCondition,
        "embeddable_kwargs": {
            "description_template": "%s is missing",
            "code_template": f"{DF_OLD}[%s].isna()",
        },
    },
    "is not missing": {
        "embeddable_class": SimpleDropdownDefaultCondition,
        "embeddable_kwargs": {
            "description_template": "%s is not missing",
            "code_template": f"{DF_OLD}[%s].notna()",
        },
    },
}

CATEGORICAL_DROPDOWN_OPTIONS = {
    "has value(s)": {
        "embeddable_class": MultiColumnValuesCondition,
        "embeddable_kwargs": {
            "description_template": "%s is one of: %s",
            "code_template": f"{DF_OLD}[%s].isin(%s)",
        },
    },
    "is missing": {
        "embeddable_class": SimpleDropdownDefaultCondition,
        "embeddable_kwargs": {
            "description_template": "%s is missing",
            "code_template": f"{DF_OLD}[%s].isna()",
        },
    },
    "is not missing": {
        "embeddable_class": SimpleDropdownDefaultCondition,
        "embeddable_kwargs": {
            "description_template": "%s is not missing",
            "code_template": f"{DF_OLD}[%s].notna()",
        },
    },
}

SHOW_UNSUPPORTED_DTYPE_WARNING = "SHOW_UNSUPPORTED_DTYPE_WARNING"
SHOW_MIXED_OBJECT_COLUMN_WARNING = "SHOW_MIXED_OBJECT_COLUMN_WARNING"


class ConditionRow(SelectorMixin, widgets.VBox):
    """
    A `ConditionRow`consists of a column selector, a corresponding filter condition object, and
    a connector (logical and/or) used to concatenate multiple `ConditionRow`s.
    """

    def __init__(
        self,
        df,
        column=None,
        default_filter=None,
        default_filter_kwargs={},
        focus_after_init=False,
        selector_group=None,
        show_delete_button=False,
        **kwargs,
    ):
        super().__init__(
            selector_group=selector_group,
            show_delete_button=show_delete_button,
            **kwargs,
        )
        self.df = df
        self.condition_section = selector_group
        self.is_added_item = show_delete_button
        self.has_connector = self.is_added_item

        self.column = None
        self.column_dtype = None

        set_soft_value = True if column is None else False

        self.column_dropdown = Singleselect(
            options=list(self.df.columns),
            value=column,
            focus_after_init=focus_after_init,
            set_soft_value=set_soft_value,
            placeholder="Choose",
            width="xs",
            on_change=lambda _: self._update_selected_column(first_render=False),
        )

        if self.has_connector:
            self.connector = Singleselect(
                options=[("and", AND_CONNECTOR_STRING), ("or", OR_CONNECTOR_STRING)],
                placeholder="Logic",
                focus_after_init=True,
                width="xs",
                set_soft_value=True,
                on_change=lambda _: self.column_dropdown.focus(),
            )
        else:
            self.connector = widgets.HTML("")

        self.condition_outlet = widgets.HBox([])

        self.children = [
            widgets.HBox([self.connector, self.delete_selector_button]),
            self.condition_outlet,
        ]

        self._update_selected_column(
            default_filter=default_filter,
            default_filter_kwargs=default_filter_kwargs,
            first_render=True,
        )

    def _update_selected_column(self, **kwargs):
        self.column = self.column_dropdown.value
        self.column_dtype = self.df[self.column].dtype
        self._update_condition_dropdown(**kwargs)

    def _get_dropdown_options(self):
        """Depending on the data type of the selected column, get the correct filter condition options."""
        dtype = self.column_dtype
        if is_categorical_dtype(dtype):
            # the comparison uses str(dtype) because otherwise there is a pandas bug
            dtype = self.df[self.column].cat.categories.dtype
            if is_object_dtype(dtype) or is_string_dtype(dtype):
                return STRING_DROPDOWN_OPTIONS
            else:
                return CATEGORICAL_DROPDOWN_OPTIONS

        if is_object_dtype(dtype):
            # only check the first 10k rows for inference in order to be fast
            # 10k rows take 0.5ms
            # 10mio rows take 500ms
            inferred_dtype = pd.api.types.infer_dtype(self.df[self.column].head(10_000))
            if inferred_dtype == "string":
                # there is a small chance that the column contains non-string objects
                return STRING_DROPDOWN_OPTIONS
            else:
                return SHOW_MIXED_OBJECT_COLUMN_WARNING
        elif is_string_dtype(dtype):
            return STRING_DROPDOWN_OPTIONS
        elif is_datetime64_any_dtype(dtype):
            return DATETIME_DROPDOWN_OPTIONS
        # bool needs to be checked before numeric because bool is a numeric dtype in pandas
        elif is_bool_dtype(dtype):
            return BOOLEAN_DROPDOWN_OPTIONS
        elif is_numeric_dtype(dtype):
            return NUMERIC_DROPDOWN_OPTIONS
            # if we want to add numeric free text conditions, then we need to abstract the logic that
            # not all conditions have a dropdown but the dropdown condition is just one condition
            # details type and a free text type would be another. Compare the difference of the
            # GenericDropdownCondition and the NumericFreeTextCondition
        else:
            return SHOW_UNSUPPORTED_DTYPE_WARNING

    def _show_unsupported_column_type_warning(self):
        """Show a warning that we don't support filter for the current data type."""
        log_error(
            "missing feature", self, f"unsupported column dtype: {self.column_dtype}"
        )

        self.condition_outlet.children = [
            self.column_dropdown,
            widgets.HTML(
                f"""Sorry, columns with type <b>{self.column_dtype}</b> cannot be filtered yet. If you need this, please contact us via bamboolib-feedback@databricks.com"""
            ),
        ]

    def _show_mixed_object_column_warning(self):
        from bamboolib.transformations import (
            ToStringTransformer,
        )  # prevent circular import

        def open_to_string(button):
            df_manager = self.condition_section.transformation.df_manager
            wrangler = df_manager.wrangler
            parent_tabs = wrangler.parent_tabs
            outlet = wrangler.side_window_outlet

            ToStringTransformer(
                column=self.column, df_manager=df_manager, parent_tabs=parent_tabs
            ).add_to(outlet)

        go_to_string = Button(
            description="Convert To String", on_click=open_to_string, style="primary"
        )

        self.condition_outlet.children = [
            self.column_dropdown,
            widgets.VBox(
                [
                    widgets.HTML(
                        f"""The column '{self.column}' cannot be filtered because it has the dtype 'object' and contains values with multiple types.<br>
                    If you want to filter this column, <b>please convert the column into a string</b> by using the <b>"To String"</b> transformation."""
                    ),
                    go_to_string,
                ]
            ),
        ]

    def _update_condition_dropdown(self, **kwargs):
        self.dropdown_options = self._get_dropdown_options()
        if self.dropdown_options == SHOW_UNSUPPORTED_DTYPE_WARNING:
            self._show_unsupported_column_type_warning()
        elif self.dropdown_options == SHOW_MIXED_OBJECT_COLUMN_WARNING:
            self._show_mixed_object_column_warning()
        else:
            self._render_valid_condition_dropdown(**kwargs)

    def _render_valid_condition_dropdown(
        self, default_filter=None, first_render=True, **kwargs
    ):
        """Render the filter condition dropdown."""
        focus_after_init = not first_render
        set_soft_value = True if default_filter is None else False

        self.condition_dropdown = Singleselect(
            options=list(self.dropdown_options.keys()),
            value=default_filter,
            focus_after_init=focus_after_init,
            set_soft_value=set_soft_value,
            on_change=lambda _: self._update_condition_details_outlet(
                first_render=False
            ),
            width="xs",
        )

        self.condition_details_outlet = widgets.HBox([])
        self._update_condition_details_outlet(**kwargs)

        self.condition_outlet.children = [
            self.column_dropdown,
            self.condition_dropdown,
            self.condition_details_outlet,
        ]

    def _update_condition_details_outlet(
        self, default_filter_kwargs={}, first_render=True, **kwargs
    ):
        """Render the condition details, e.g. a text input when having a text input condition."""
        embeddable = self.dropdown_options[self.condition_dropdown.value][
            "embeddable_class"
        ]
        embeddable_kwargs = self.dropdown_options[self.condition_dropdown.value][
            "embeddable_kwargs"
        ]
        merged_kwargs = {
            **embeddable_kwargs,
            **default_filter_kwargs,
            "first_render": first_render,
        }
        self.condition = embeddable(self, **merged_kwargs)
        self.condition_details_outlet.children = [self.condition]

    def execute(self):
        self.condition_section.transformation.execute()

    def is_valid_condition(self):
        if self.dropdown_options in [
            SHOW_UNSUPPORTED_DTYPE_WARNING,
            SHOW_MIXED_OBJECT_COLUMN_WARNING,
        ]:
            raise BamboolibError(
                f"The column '{self.column}' cannot be filtered.<br>Please remove the column from the filter."
            )
        return self.condition.is_valid_condition()

    def get_code(self):
        condition = self.condition.get_code()

        if self.has_connector:
            connector = self._get_connector_code()
            return f"{connector} ({condition})"
        else:
            return condition

    def _get_connector_code(self):
        """In pandas, is either "&" or "|"."""
        if self.has_connector:
            return self.connector.value
        else:
            # The user should never see this
            raise Exception("The condition has no connector")

    def get_description(self):
        description = self.condition.get_description()

        if self.has_connector:
            connector = self.get_connector_description()
            return f"<b>{connector}</b> ({description})"
        else:
            return description

    """Functions that return metainfos, e.g. for logging."""

    def get_connector_description(self):
        if self.has_connector:
            return self.connector.label
        else:
            return ""

    def get_metadescription(self):
        metadescription = f"{self.column_dtype} {self.condition_dropdown.value}"

        if self.has_connector:
            connector = self.get_connector_description()
            return f"{connector} {metadescription}"
        else:
            return metadescription

    def get_metainfos(self):
        infos = {
            f"condition_column_dtype_{self.column_dtype}": True,
            f"condition_type_{self.condition_dropdown.value}": True,
        }
        if self.has_connector:
            infos[f"condition_connector_{self.connector.label}"] = True
        return infos

    """Functions for programmatically setting input values. Used for unit tests."""

    def test_select_column(self, column):
        self.column_dropdown.value = column

    def test_filter(self, greater_than=None, starts_with=None):
        if greater_than is not None:
            self.condition_dropdown.value = GREATER_THAN_LABEL
            self.condition.test_set_value(greater_than)
        if starts_with is not None:
            self.condition_dropdown.value = STARTS_WITH_LABEL
            self.condition.test_set_value(starts_with)


class ConditionSection(SelectorGroupMixin, widgets.VBox):
    """
    Manages all `ConditionRow`s.

    Hint for developer. You can call a conition directly, e.g.:

    cs = ConditionSection(df, "Age", NumericFreetextCondition)
    cs
    """

    def __init__(self, transformation, df, column=None, **kwargs):
        super().__init__()
        self.transformation = transformation
        self.df = df
        self.column = column
        self.kwargs = kwargs

        self.init_selector_group(add_button_text="add condition")

        self.children = [self.selector_group, self.add_selector_button]

    def create_selector(self, show_delete_button=None, **kwargs):
        """Create a filter condition row."""
        return ConditionRow(
            self.df,
            self.column,
            show_delete_button=show_delete_button,
            selector_group=self,
            **kwargs,
        )

    def get_initial_selector(self):
        """Create the first filter condition row."""
        return self.create_selector(show_delete_button=False, **self.kwargs)

    def is_valid_condition(self):
        """Check if the filter condition is valid."""
        return any(
            [condition.is_valid_condition() for condition in self.get_selectors()]
        )

    def get_valid_conditions(self):
        """Get all valid filter conditions."""
        return [
            condition
            for condition in self.get_selectors()
            if condition.is_valid_condition()
        ]

    def _build_string_from_valid_conditions(self, lambda_, template):
        result = ""
        for condition in self.get_valid_conditions():
            value = lambda_(condition)
            if result == "":
                result = value
            else:
                result = template % (result, value)
        return result

    def get_description(self):
        lambda_ = lambda condition: condition.get_description()
        template = "(%s) %s"
        return self._build_string_from_valid_conditions(lambda_, template)

    def get_code(self):
        lambda_ = lambda condition: condition.get_code()
        template = "(%s) %s"
        return self._build_string_from_valid_conditions(lambda_, template)

    """Functions returning meta information about the transformation. Used for logging."""

    def _get_condition_metaformula(self):
        lambda_ = lambda condition: condition.get_metadescription()
        template = "%s %s"
        return self._build_string_from_valid_conditions(lambda_, template)

    def _get_condition_metaconnections(self):
        lambda_ = lambda condition: condition.get_connector_description()
        template = "%s %s"
        return self._build_string_from_valid_conditions(lambda_, template)

    def get_metainfos(self):
        condition_metainfos = {}
        for condition in self.get_selectors():
            condition_metainfos = {**condition_metainfos, **condition.get_metainfos()}
        return {
            "condition_section_count": len(self.get_selectors()),
            "condition_metaformula": self._get_condition_metaformula(),
            "condition_metaconnections": self._get_condition_metaconnections(),
            **condition_metainfos,
        }

    """Functions used for unit test."""

    def test_select_column(self, column):
        self.get_selectors()[-1].test_select_column(column)

    def test_filter(self, **kwargs):
        self.get_selectors()[-1].test_filter(**kwargs)


class FilterTransformer(Transformation):
    """Manages the complete filter transformation."""

    def __init__(self, *args, column=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.condition_section = ConditionSection(self, self.get_df(), column)

        self.filter_type = Singleselect(
            options=[("Select rows", "keep"), ("Drop rows", "drop")],
            focus_after_init=True,
            set_soft_value=True,
            width="sm",
        )

    def render(self, **kwargs):
        self.set_title("Filter rows")
        self.set_content(
            self.filter_type,
            widgets.HTML("where"),
            self.condition_section,
            self.rename_df_group,
        )

    def _get_new_column_name(self):
        for i in range(0, 10_000_000):
            name = f"new_filter_column_{i}"
            if not name in self.get_df().columns:
                return name

    def is_valid_transformation(self):
        return self.condition_section.is_valid_condition()

    def get_description(self):
        boolean_series_description = self.condition_section.get_description()

        type_ = self.filter_type.value
        if type_ == "keep":
            return f"<b>Keep rows</b> where {boolean_series_description}"
        if type_ == "drop":
            return f"<b>Drop rows</b> where {boolean_series_description}"

    def get_code(self):
        boolean_series_code = self.condition_section.get_code()

        type_ = self.filter_type.value
        if type_ == "keep":
            code = f"{DF_NEW} = {DF_OLD}.loc[{boolean_series_code}]"
        if type_ == "drop":
            code = f"{DF_NEW} = {DF_OLD}.loc[~({boolean_series_code})]"
        return code

    def get_metainfos(self):
        return {
            "filter_rows_type": self.filter_type.value,
            **self.condition_section.get_metainfos(),
        }

    def get_transformation_insight(self):
        """Get any information about the impact of the filter on the dataset."""
        old_rows = self.df_manager.get_penultimate_df().shape[0]
        new_rows = self.df_manager.get_current_df().shape[0]
        removed_rows = old_rows - new_rows
        percentage = (float(removed_rows) / old_rows) * 100
        # use math.floor in order to turn 99.9 into 99 instead of rounding up to 100
        # motivating example - removing 3000 from 3003 rows:
        # "removed 3,000 rows (100%)" feels weird when still 3 rows are left
        # we prefer "removed 3,000 rows (99%)
        # With this approach, the other direction is also no problem:
        # e.g. "removed 3 rows (0%)"
        percentage = math.floor(percentage)
        return widgets.HTML(f"Filter: removed {removed_rows:,} rows ({percentage}%)")

    """Functions for programmatically setting input values. Used for unit tests."""

    def test_select_column(self, column):
        self.condition_section.test_select_column(column)

    def test_filter(self, **kwargs):
        self.condition_section.test_filter(**kwargs)
