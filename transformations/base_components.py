# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.widgets import Button, Singleselect, CloseButton, Text

from bamboolib.helper import DF_OLD, string_to_code, safe_cast, notification, BamboolibError

VALUE_FROM_CATEGORICAL_SERIES = "value"
STRING_VALUE = "text value (string)"
NUMERIC_VALUE = "numeric value"
BOOLEAN_VALUE = "boolean (true/false)"
COLUMN_VALUE = "value of column"
MISSING_VALUE = "missing value"


class SelectorMixin:
    """
    Base class that contains an input element and a Button to remove itself.

    Specifics need to be implemented by its child.
    SelectorMixin needs to be a part of a SelectorGroupMixin.
    """

    def __init__(self, *args, selector_group=None, show_delete_button=None, **kwargs):
        if show_delete_button is True:
            if selector_group is None:
                raise NotImplementedError

        super().__init__(*args, **kwargs)

        self.selector_group = selector_group

        if show_delete_button:
            self.delete_selector_button = CloseButton(
                on_click=lambda button: self.selector_group.remove_selector(self)
            )
        else:
            self.delete_selector_button = widgets.HTML("")


class SelectorGroupMixin:
    """
    Base class for managing (including creation, removal, and listing of) a bunch of selectors.
    A selector typically is an implementation of SelectorMixin.

    Specifics need to be implemented by its child.
    """

    def create_selector(self, *args, show_delete_button=True, **kwargs):
        """Creates a selector, typically an implementation of SelectorMixin."""
        raise NotImplementedError

    def get_initial_selector(self):
        """Create the first selector."""
        return self.create_selector(show_delete_button=False)

    def get_new_selector(self):
        """Create every but the first selector."""
        return self.create_selector(show_delete_button=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def init_selector_group(self, add_button_text="add", add_first_selector=True):
        """Create the container that holds all selectors."""
        # this method can only be called AFTER everything is setup for calling self.create_selector
        if add_first_selector:
            selectors = [self.get_initial_selector()]
        else:
            selectors = []
        self.selector_group = widgets.VBox(selectors)
        self.selector_group.add_class("bamboolib-overflow-visible")

        self.add_selector_button = Button(
            description=add_button_text, on_click=lambda button: self.add_selector()
        )

    def get_selectors(self):
        """Get all current selectors."""
        return self.selector_group.children

    def remove_selector(self, selector):
        """Remove a selector from the selector group."""
        output = list(self.selector_group.children)
        output.remove(selector)
        self.selector_group.children = output

    def add_selector(self):
        """Add a selector to the selector group."""
        output = list(self.selector_group.children)
        output.append(self.get_new_selector())
        self.selector_group.children = output


class ValueSelector(widgets.HBox):
    """
    Used when we want to e.g. replace values in a dataset. The user can then specify to replace
    values with "string value X", with "non-string value Y", or with "missing value". With a
    ValueSelector, the user doens't have to explicitely quote values in a text input field when he
    wants to set a column to a string value.

    This may become obsolete in the future when we let the user set string values by explicitely
    quoting them and treating unquoted values in text input fields as numbers/bools.
    """

    def __init__(
        self,
        transformation,
        series=None,
        columns=[],
        show_column=True,
        show_missing_value=True,
    ):
        super().__init__()
        self.transformation = transformation
        self.series = series
        self.columns = columns

        if (series is not None) and (str(series.dtype) == "category"):
            options = [VALUE_FROM_CATEGORICAL_SERIES]
        else:
            options = [STRING_VALUE, NUMERIC_VALUE, BOOLEAN_VALUE]
        if show_missing_value:
            options.append(MISSING_VALUE)
        if show_column and len(columns) > 0:
            options.append(COLUMN_VALUE)

        self.type_dropdown = Singleselect(
            placeholder="Value type",
            options=options,
            width="sm",
            set_soft_value=True,
            on_change=lambda widget: self._update_value_type(focus_after_init=True),
        )

        self.detail_outlet = widgets.VBox([])

        self.children = [self.type_dropdown, self.detail_outlet]
        self._update_value_type(focus_after_init=False)

    def _update_value_type(self, focus_after_init=False):
        if self.type_dropdown.value == MISSING_VALUE:
            self.value_input = widgets.HTML()  # empty placeholder
        elif self.type_dropdown.value == VALUE_FROM_CATEGORICAL_SERIES:
            self.value_input = Singleselect(
                placeholder="Choose value",
                options=[(str(value), value) for value in self.series.cat.categories],
                focus_after_init=focus_after_init,
                set_soft_value=True,
                width="md",
            )
        elif self.type_dropdown.value == COLUMN_VALUE:
            self.value_input = SingleColumnSelector(
                placeholder="Choose column",
                options=self.columns,
                focus_after_init=focus_after_init,
                width="md",
            )
        elif self.type_dropdown.value == BOOLEAN_VALUE:
            self.value_input = Singleselect(
                placeholder="Choose value",
                value="True",  # Attention: value(s) have to be strings because they are forwarded literally as code string
                options=["True", "False"],
                focus_after_init=focus_after_init,
                width="md",
            )
        else:  # NUMERIC_VALUE or STRING_VALUE
            self.value_input = Text(
                value="",
                placeholder="",
                focus_after_init=focus_after_init,
                execute=self.transformation,
            )

        self.detail_outlet.children = [self.value_input]

    def should_quote_value(self):
        """
        :return bool if the value has to be quoted within the code e.g. for strings and categorical values

        The old logic was not stable because pandas might handle numbers in a object column as float
        and then it would not work if we quote the float values (based on the dtype of the column
        which is supposed to be string-like.
        Might be different once there is an explicit string type for columns?
        This was the old logic:
        if column_type is REPLACE_IN_ALL_COLUMNS_STRING:
            try:
                float(self.value_input.value)
            except:
                return True  # quote because the value does not seem to be a number
            return False  # dont quote because it seems to be a number
        else:
            # https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.api.types.is_float_dtype.html
            # and
            # https://github.com/pandas-dev/pandas/blob/v0.25.1/pandas/core/dtypes/common.py#L1585-L1616
            return pd.api.types.is_object_dtype(
                column_type
            ) or pd.api.types.is_datetime64_any_dtype(column_type)
        """
        if self.type_dropdown.value == STRING_VALUE:
            return True
        elif self.type_dropdown.value == VALUE_FROM_CATEGORICAL_SERIES:
            if isinstance(self.value_input.value, str):
                return True
        else:
            return False

    def get_value_code(self):
        if self.type_dropdown.value == MISSING_VALUE:
            return "np.nan"
        elif self.type_dropdown.value == COLUMN_VALUE:
            return f"{DF_OLD}[{string_to_code(self.value_input.value)}]"
        elif self.should_quote_value():
            return string_to_code(self.value_input.value)
        else:
            return self.value_input.value

    def get_value_description(self):
        if self.type_dropdown.value == MISSING_VALUE:
            return MISSING_VALUE
        elif self.type_dropdown.value == COLUMN_VALUE:
            return f"value of column '{self.value_input.value}'"
        else:
            return self.value_input.value
    
    def is_valid_value(self):
        if self.type_dropdown.value == NUMERIC_VALUE:
            is_int = safe_cast(self.value_input.value, int, None) is not None
            is_float = safe_cast(self.value_input.value, float, None) is not None
            if not (is_int or is_float):
                raise BamboolibError(
                    f"""Numerical Format Error: We could not transform your input <b>{self.value_input.value}</b> into a valid numerical value.<br>
                    <br>
                    Examples for valid values:
                    <ul>
                        <li>10</li>
                        <li>10.5</li>
                        <li>10000.123</li>
                        <li>1e-08</li>
                    </ul>
                    The decimal separator needs to be a point instead of a comma""",
                )
        # in all other cases
        return True


class SingleColumnSelector(Singleselect):
    """Widget for selecting a single column of a dataset."""

    def __init__(self, *args, placeholder="Choose column", **kwargs):
        super().__init__(*args, placeholder=placeholder, **kwargs)
