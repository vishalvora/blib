# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


# Note: in the future, we might reuse some of the blocks and logic from the plot_creator because they are very similar


import pandas as pd
import traceback
import textwrap
import ipywidgets as widgets
from IPython.display import Markdown, HTML, display
from bamboolib.helper import string_to_code

from bamboolib.helper import (
    TabViewable,
    log_action,
    log_error,
    execute_asynchronously,
    notification,
)

from bamboolib.widgets import (
    Button,
    CloseButton,
    CodeOutput,
    CopyButton,
    Multiselect,
    Singleselect,
    TableOutput,
    Text,
    TracebackOutput,
)

CONFIG_TYPE_KWARGS = "kwargs"
CONFIG_TYPE_METHOD = "code"
CONFIG_TYPE_HINT = "hint"

# ATTENTION: due to the fact that as of Jan 7 2022 we are not enabled to use widgets.Layout
# we needed to hardcode the CSS classes
# if you change the LABEL_WIDTH you need to make sure that the corresponding CSS class exists
# e.g. currently this is the pattern bamboolib-width-{LABEL_WIDTH}
# and thus bamboolib-width-180px
LABEL_WIDTH = "180px"

SHOW_CODE = True

ERROR_MESSAGE_NONNUMERIC_AGGREGATION = textwrap.dedent(
    """
You have selected a non-numeric column for the 'Values' property.<br>
<br>
Please add the property 'Aggregation Function' to the UI and specify an aggregation function that can be applied to non-numeric columns, e.g. 'Count/Size', 'First Value', or 'Last Value'.
"""
).strip()

ERROR_MESSAGE_COLUMN_DOES_NOT_EXIST_ANYMORE = textwrap.dedent(
    """
One of the columns that you use does not exist in the dataframe any more.<br>
This usually happens when you changed the dataframe and then switched back to the Pivot Table view.<br>
<br>
Now, you have 2 options:<br>
1) Undo your dataframe changes<br>
2) Reset the Pivot Table UI with the button below:
"""
).strip()

ERROR_MESSAGE_COLUMN_IN_MULTIPLE_DIMENSIONS = textwrap.dedent(
    """
You have selected a column for multiple dimensions e.g. for 'Columns', 'Rows' or 'Values'.<br>
This is (usually) not allowed because columns should only be used in 1 dimension.<br>
<br>
Please remove the column that is used in multiple dimensions from at least 1 dimension.
"""
).strip()


class ConfigItem(widgets.HBox):
    """
    A generic ConfigItem that is used for inheritance

    :param parent: parent widget
    :param was_added_automatically: bool if widget was added automatically
    """

    def __init__(self, parent, *args, was_added_automatically=False, **kwargs):
        super().__init__(*args, **kwargs)
        self._content = []
        self.parent = parent
        self.was_added_automatically = was_added_automatically

    def get_code(self):
        """
        TO BE OVERRIDEN

        Return code
        """
        raise NotImplementedError

    def get_type(self):
        """
        TO BE OVERRIDEN

        Returns the type of the ConfigItem.
        Should be one of [CONFIG_TYPE_KWARGS, CONFIG_TYPE_METHOD, CONFIG_TYPE_HINT]
        """
        raise NotImplementedError

    def render_again(self):
        pass

    def set_content(self, *embeddables, **kwargs):
        """
        Method to set the content of the widget

        Example:
        >>> item.set_content(widgets.HTML("My name"), widgets.HTML("Something else"))
        """
        self._content = list(embeddables)
        self.render()

    def is_valid(self):
        """
        :return bool if the config item is valid
        """
        return self.get_code() != ""

    def is_kwarg(self):
        """
        :return bool if the config provides a kwarg for the code
        """
        return self.get_type() == CONFIG_TYPE_KWARGS

    def is_method(self):
        """
        :return bool if the config provides a method as input to the code
        """
        return self.get_type() == CONFIG_TYPE_METHOD

    def render(self):
        self.render_again()
        output = []
        output += self._content
        self.children = output


class TextfieldKwargsItem(ConfigItem):
    """
    A base class for kwarg items that require text input

    Example:
    >>> class MarginsName(TextfieldKwargsItem):
    >>>     name = "Margins - column/row name"
    >>>     kwarg = "margins_name"
    >>>     placeholder = "Name of the margin, e.g. All"
    >>>     value = "All"
    >>>     has_string_value = True
    """

    name = "TO BE OVERRIDEN"
    kwarg = "TO BE OVERRIDEN"
    placeholder = ""
    value = ""
    has_string_value = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.name = widgets.HTML(f"{self.__class__.name}:").add_class(
            f"bamboolib-width-{LABEL_WIDTH}"
        )

        self.textfield = Text(
            value=self.__class__.value,
            placeholder=self.__class__.placeholder,
            focus_after_init=True,
            width="lg",
            on_submit=self.parent.update_output,
        )

        self.delete_button = CloseButton(
            on_click=lambda button: self.parent.remove_config(self)
        )

        output = [self.name, self.textfield, self.delete_button]
        hbox = widgets.HBox(output)

        self.set_content(hbox)

    def get_code(self):
        if self.textfield.value == "":
            return ""

        if self.__class__.has_string_value:
            value = string_to_code(self.textfield.value)
        else:
            value = self.textfield.value

        return f", {self.__class__.kwarg}={value}"

    def get_type(self):
        return CONFIG_TYPE_KWARGS


class MarginsName(TextfieldKwargsItem):
    name = "Margins - column/row name"
    kwarg = "margins_name"
    placeholder = "Name of the margin, e.g. All"
    value = "All"
    has_string_value = True


class FillValue(TextfieldKwargsItem):
    name = "Replace missing values"
    kwarg = "fill_value"
    placeholder = "Numeric replace value, e.g. 0"


class TextfieldMethodItem(TextfieldKwargsItem):
    """
    A base class for method items that require text input
    """

    code = "TO BE OVERRIDEN"

    def get_type(self):
        return CONFIG_TYPE_METHOD

    def get_code(self):
        if self.textfield.value == "":
            return ""

        if self.__class__.has_string_value:
            value = string_to_code(self.textfield.value)
        else:
            value = self.textfield.value

        return self.__class__.code % value


class SetPrecision(TextfieldMethodItem):
    name = "Set precision"
    code = ".set_precision(%s)"
    placeholder = "Max total number of digits, eg 4"


class MultipleColumnsKwargsItem(ConfigItem):
    """
    A base class for kwarg items that require multiple columns of the Dataframe as input
    """

    name = "TO BE OVERRIDEN"
    kwarg = "TO BE OVERRIDEN"
    placeholder = "Choose columns"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.name = widgets.HTML(f"{self.__class__.name}:").add_class(
            f"bamboolib-width-{LABEL_WIDTH}"
        )

        self.columns_list = Multiselect(
            options=self._get_options(),
            placeholder=self.__class__.placeholder,
            focus_after_init=True,
            width="lg",
            on_change=self.parent.update_output,
        )

        self.delete_button = CloseButton(
            on_click=lambda button: self.parent.remove_config(self)
        )

        output = [self.name, self.columns_list, self.delete_button]
        hbox = widgets.HBox(output)
        hbox.add_class("bamboolib-overflow-visible")

        self.set_content(hbox)
        self.add_class("bamboolib-overflow-visible")

    def get_code(self):
        if self.columns_list.value is []:
            return ""
        else:
            return f", {self.__class__.kwarg}={self.columns_list.value}"

    def get_type(self):
        return CONFIG_TYPE_KWARGS

    def _get_options(self):
        return self.parent.df.columns


class Columns(MultipleColumnsKwargsItem):
    name = "Columns"
    kwarg = "columns"


class Rows(MultipleColumnsKwargsItem):
    name = "Rows"
    kwarg = "index"


class SingleChoiceKwargsItem(ConfigItem):
    """
    A base class for kwarg items that require a single choice as input
    """

    name = "TO BE OVERRIDEN"
    kwarg = "TO BE OVERRIDEN"
    placeholder = "Choose option"
    has_string_value = False
    set_soft_value = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.name = widgets.HTML(f"{self.__class__.name}:").add_class(
            f"bamboolib-width-{LABEL_WIDTH}"
        )

        focus_after_init = True if not self.was_added_automatically else False

        set_soft_value = self.__class__.set_soft_value

        self.dropdown = Singleselect(
            options=self._get_options(),
            placeholder=self.__class__.placeholder,
            focus_after_init=focus_after_init,
            set_soft_value=set_soft_value,
            width="lg",
            on_change=self.parent.update_output,
        )

        self.delete_button = CloseButton(
            on_click=lambda button: self.parent.remove_config(self)
        )

        self.hbox = widgets.HBox()
        self.hbox.add_class("bamboolib-overflow-visible")

        self.set_content(self.hbox)
        self.add_class("bamboolib-overflow-visible")

        self.render_again()
        if set_soft_value:
            self.parent.update_output()

    def render_again(self):
        output = [self.name, self.dropdown]
        output.append(self.delete_button)
        self.hbox.children = output

    def get_code(self):
        if self.dropdown.value is None:
            return ""

        if self.__class__.has_string_value:
            value = f"""'{self.dropdown.value}'"""
        else:
            value = self.dropdown.value

        return f", {self.__class__.kwarg}={value}"

    def get_type(self):
        return CONFIG_TYPE_KWARGS

    def _get_options(self):
        raise NotImplementedError


class BooleanKwargsItem(SingleChoiceKwargsItem):
    placeholder = "Choose state"

    def _get_options(self):
        return [("True", True), ("False", False)]


class Margins(BooleanKwargsItem):
    name = "Margins"
    kwarg = "margins"


class Dropna(BooleanKwargsItem):
    name = "Keep columns with missing values only"
    kwarg = "dropna"

    def _get_options(self):
        return [("True", False), ("False", True)]


class Observed(BooleanKwargsItem):
    name = "Only show observed categorical values"
    kwarg = "observed"


class SingleStringChoiceKwargsItem(SingleChoiceKwargsItem):
    has_string_value = True


class AggFunc_AggregationFunction(SingleStringChoiceKwargsItem):
    name = "Aggregation function"
    kwarg = "aggfunc"
    placeholder = "Choose function"

    def _get_options(self):
        # from pandas.core.basy.py - SelectionMixin
        return [
            ("Count (size)", "size"),  # with missing values
            ("Count (excl. missings)", "count"),
            ("Sum", "sum"),
            ("Mean/Average", "mean"),
            ("Median", "median"),
            ("Min", "min"),
            ("Max", "max"),
            ("First value", "first"),
            ("Last value", "last"),
            ("Number of unique values", "nunique"),
            # distribution metrics
            ("Standard deviation - std", "std"),
            ("Variance", "var"),
            ("Standard error of the mean - sem", "sem"),
            ("Mean absolute deviation - mad", "mad"),
            ("Skew", "skew"),
            ("All (boolean operator)", "all"),
            ("Any (boolean operator)", "any"),
            ("Index of max value", "idxmax"),
            ("Index of min value", "idxmin"),
            ("Product of all values", "prod"),
        ]


class SingleColumnNameKwargsItem(SingleStringChoiceKwargsItem):
    """
    A base class for kwarg items that require a single column of the Dataframe as input
    """

    placeholder = "Choose column"

    def _get_options(self):
        return self.parent.df.columns


class Values(SingleColumnNameKwargsItem):
    name = "Values"
    kwarg = "values"


PIVOT_CONFIGS = [
    Columns,
    Rows,
    Values,
    AggFunc_AggregationFunction,
    Margins,
    MarginsName,
    FillValue,
    Dropna,
    SetPrecision,
]


class PivotTable(TabViewable):
    """
    A view to create a PivotTable
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.symbols = self.df_manager.symbols
        self.initialize_view()

    def initialize_view(self):
        """
        Setup all variables and values that are needed for a new pivot table
        """

        self.df = self.df_manager.get_current_df()
        self.old_df_columns = list(self.df.columns)

        self.big_spacer = widgets.VBox([self.spacer for i in range(15)])

        self.top_notification_outlet = widgets.VBox()
        self.pivot_outlet = widgets.HBox()
        self.pivot_outlet.add_class("bamboolib-pivot-html")
        self.code_outlet = widgets.VBox()
        self.code_output = CodeOutput(code="")

        self._current_render_id = 0

        self.rendered_config_classes = (
            []
        )  # this could be removed if we use the classes from the items for some of the checks
        self.config_items = []

        self.config_outlet_for_search = widgets.HBox()
        self.config_outlet_for_search.add_class("bamboolib-overflow-visible")

        self.config_outlet_for_items = widgets.VBox()
        self.config_outlet_for_items.add_class("bamboolib-overflow-visible")

        self._render_config_search(focus_after_init=True)

        self.update_output()

    def _render_config_search(self, focus_after_init=False):
        options = [
            (option.name, option)
            for option in PIVOT_CONFIGS
            if option not in self.rendered_config_classes
        ]

        if len(options) == 0:
            self.config_outlet_for_search.children = []
        else:
            self.label = widgets.HTML(f"Add property:").add_class(
                f"bamboolib-width-{LABEL_WIDTH}"
            )
            self.config_search = Singleselect(
                options=options,
                placeholder="Add property",
                focus_after_init=focus_after_init,
                width="lg",
                set_soft_value=False,
                on_change=self._config_search_changed,
            )

            self.config_outlet_for_search.children = [self.label, self.config_search]

    def _config_search_changed(self, _=None):
        config_class = self.config_search.value
        self._add_config(config_class)

    def remove_config(self, item):
        """
        Remove config from the pivot table
        :param item: the config item that should be removed
        """
        try:
            self.config_items.remove(item)
            self.rendered_config_classes.remove(item.__class__)
        except:
            # when the user is working too fast, he might trigger this multiple times
            # this behavior might lead to an ValueError if the item does not exist any more
            return

        self._render_config_outlet()
        self._render_config_search()
        self.update_output()

    def _add_config(self, config_class, was_added_automatically=False):
        self.rendered_config_classes.append(config_class)
        self.config_items.append(
            config_class(self, was_added_automatically=was_added_automatically)
        )

        self._render_config_outlet()
        self._render_config_search()

    def _render_config_outlet(self, *args, **kwargs):
        for item in self.config_items:
            item.render()
        self.config_outlet_for_items.children = self.config_items

    def _render_code_outlet(self):
        code_string = self.get_code()

        copy_button = CopyButton(
            copy_string=code_string,
            style="primary",
            on_click=lambda _: log_action("export", self, "click copy code"),
        )

        def toggle_hide_or_show(button):
            global SHOW_CODE
            SHOW_CODE = not SHOW_CODE
            self._render_code_outlet()

        hide_or_show_button = Button(
            description="Hide code" if SHOW_CODE else "Show code",
            icon="chevron-up" if SHOW_CODE else "chevron-down",
            on_click=toggle_hide_or_show,
        )

        output = [widgets.HBox([copy_button, hide_or_show_button])]
        if SHOW_CODE:
            output.append(self._get_widget_with_code(code_string))
        self.code_outlet.children = output

    def _get_widget_with_code(self, code_string):
        self.code_output.code = code_string
        return self.code_output

    def get_code(self):
        """
        Get the code for the pivot table
        """
        valid_items = [item for item in self.config_items if item.is_valid()]

        kwargs_code = "".join(
            [item.get_code() for item in valid_items if item.is_kwarg()]
        )

        method_code = "".join(
            [item.get_code() for item in valid_items if item.is_method()]
        )

        df_name = self.df_manager.get_current_df_name()
        if self._pivot_table_returns_a_series(df_name, kwargs_code):
            return f"""pd.pivot_table({df_name}{kwargs_code}).to_frame(name='value').style{method_code}"""
        else:
            return f"""pd.pivot_table({df_name}{kwargs_code}).style{method_code}"""

    def _pivot_table_returns_a_series(self, df_name, kwargs_code):
        # the preparations for eval code are similar to eval_code in Transformation
        symbols = self.df_manager.symbols.copy()
        symbols["pd"] = pd
        symbols[df_name] = self.df_manager.get_current_df()

        try:
            # Attention: the code is only evaluated on a small subset (head(10)) in order to be fast
            result = eval(
                f"""pd.pivot_table({df_name}.head(10){kwargs_code})""", symbols, symbols
            )
            return isinstance(result, pd.Series)
        except:
            # The pivot_table might throw an error, e.g. DataError like below
            return False

    def update_output(self, *args, **kwargs):
        """
        Update the output of the pivot table.
        First, it checks if an update is possible.
        Then shows a Loading sign and tries to evaluate the code asynchronously in order not to block the UI.
        Eventually, displays the result of the code execution.
        In case that there was an error, a special error message might be shown.
        When multiple outputs are requested, only the last one will be shown.
        """
        if not any(item in self.rendered_config_classes for item in [Columns, Rows]):
            self.pivot_outlet.children = [
                notification("Please add the property 'Columns' or 'Rows'"),
                self.big_spacer,
            ]
            self.code_outlet.children = []
            return

        self.pivot_outlet.children = [widgets.HTML("Loading ..."), self.big_spacer]

        self._current_render_id += 1

        def evaluate_and_update(render_id):
            if self._current_render_id == render_id:
                try:
                    symbols = self.symbols.copy()
                    symbols[
                        self.df_manager.get_current_df_name()
                    ] = self.df_manager.get_current_df()
                    pivot = eval(self.get_code(), symbols, {"pd": pd})
                    result = TableOutput(pivot)
                except Exception as exception:
                    result = self._get_error_output(exception)
                    log_error(
                        "catched error", self, "show error output", error=exception
                    )

            if self._current_render_id == render_id:
                self.pivot_outlet.children = [result]
                self._render_code_outlet()

        execute_asynchronously(evaluate_and_update, self._current_render_id)

    def _get_error_output(self, exception):
        """
        Get the output that is shown in case of an exception
        """
        result = None
        # pandas.core.base.DataError: No numeric types to aggregate
        if "No numeric types to aggregate" in str(exception):
            result = notification(ERROR_MESSAGE_NONNUMERIC_AGGREGATION, type="error")
        elif isinstance(exception, KeyError):
            if self._df_columns_did_change():
                explanation = notification(
                    ERROR_MESSAGE_COLUMN_DOES_NOT_EXIST_ANYMORE, type="info"
                )
                button = Button("Reset UI", on_click=lambda _: self.reset_view())
                result = widgets.VBox([explanation, button])
            else:
                pass
                # there are multiple situations when the pivot table might throw an KeyError
                # eg when margins=True and there are multiple aggregations
                # https://github.com/pandas-dev/pandas/issues/12210
        elif (
            isinstance(exception, ValueError)
            and ("Grouper for" in str(exception))
            and ("not 1-dimensional" in str(exception))
        ):
            # ValueError: Grouper for 'Survived' not 1-dimensional
            # e.g. pd.pivot_table(df, columns=['Survived', 'Pclass'], index=['Survived'], values='Age').style
            result = notification(
                ERROR_MESSAGE_COLUMN_IN_MULTIPLE_DIMENSIONS, type="error"
            )

        if result is None:
            result = self._get_stacktrace(exception)
        return result

    def reset_view(self):
        """
        Reset the view to show a new pivot table and to recover from errors
        """
        self.initialize_view()
        self.render()

    def _get_stacktrace(self, exception):
        output = TracebackOutput()
        output.add_class("bamboolib-output-wrap-text")
        output.content += f"There was an error.\n\nIn case you cannot achieve the result that you want with the Pivot Table, there is a trick:\na PivotTable is just a combination of two single transformations, so you can usually achieve the same result as follows.\n\nFirst, you use the 'Groupby and aggregate' transformation and afterwards, the 'Pivot' transformation. This combination is more stable and will give you the same result."
        output.content += "\n\n\n\n"
        output.content += f"{exception.__class__.__name__}: {exception}"
        output.content += "\n\n\n\n"

        try:
            code = self.get_code()
            output.content += "Code that produced the error:\n"
            output.content += "-----------------------------\n"
            output.content += code
            output.content += "\n\n\n\n"
        except:
            pass
        output.content += "Full stack trace:\n"
        output.content += "-----------------------------\n"
        output.content += traceback.format_exc()
        return output

    def render(self):
        self.set_title(f"Pivot Table")

        self.set_content(
            self.top_notification_outlet,
            self.config_outlet_for_items,
            self.config_outlet_for_search,
            self.code_outlet,
            self.pivot_outlet,
        )
        self.update_output()
        self._update_top_notification_outlet()

    def _df_columns_did_change(self):
        current_columns = list(self.df_manager.get_current_df().columns)
        return current_columns != self.old_df_columns

    def _update_top_notification_outlet(self):
        if self._df_columns_did_change():
            hint = notification(
                "The columns of the dataframe did change. You might want to reset the UI:"
            )
            button = Button("Reset UI", on_click=lambda _: self.reset_view())
            self.top_notification_outlet.children = [hint, button, widgets.HTML("<br>")]
        else:
            self.top_notification_outlet.children = []

    def get_metainfos(self):
        """
        Return metainfos about the object that are interesting for logging
        """
        return {
            f"pivot_table_config_{config.__class__.__name__}": True
            for config in self.config_items
        }

    def test_set_columns(self, column_names):
        """
        Method to set column_names during testing
        :param column_names: list of str - column names from the Dataframe
        """
        self.config_search.value = Columns
        columns_selector = self.config_items[-1]
        columns_selector.columns_list.value = column_names

    def test_set_rows(self, row_names):
        """
        Method to set rows during testing
        :param row_names: list of str - column names from the Dataframe
        """
        self.config_search.value = Rows
        rows_selector = self.config_items[-1]
        rows_selector.columns_list.value = row_names
