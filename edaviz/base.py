# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


from bamboolib import _environment as env
from bamboolib._authorization import auth as authorization_service
from bamboolib.config import get_option
from bamboolib.df_manager import DfManager

from bamboolib.widget_combinations import TempColumnsSelector
from bamboolib.widgets import Button, CopyButton, TracebackOutput
from bamboolib.helper import (
    log_action,
    notification,
    VSpace,
    TabSection,
    replace_code_placeholder,
    execute_asynchronously,
)

import traceback
from functools import wraps

import ipywidgets as widgets


# Constants
LOADING_ERROR_MESSAGE = "There was an error when loading the component:"
EMBEDDABLE_ERROR_MESSAGE = "There was an error when providing the component:"

SHOW_FUNCTION_HINTS = True


def css_spinner():
    return "<div class='bamboolib-load-spinner'></div>"


def get_loading_widget():
    return widgets.HTML(f"<br>{css_spinner()} Loading ...")


def get_default_outlet():
    return widgets.VBox([])


def get_function_hint(hint_string, df_manager, **kwargs):
    """
    Creates a function hint that can be copied to clipboard by clicking on it.
    """

    if not SHOW_FUNCTION_HINTS:
        return None

    hint_string = replace_code_placeholder(
        hint_string, old_df_name=df_manager.get_current_df_name()
    )

    return CopyButton(
        description=hint_string,
        copy_string=hint_string,
        style=None,
        css_classes=["bamboolib-button-function-hint"],
        on_click=lambda _: log_action(
            "viz", "function_hint", "copied function hint", function_hint=hint_string
        ),
    )


def _convert_to_list(x):
    # TODO: in case that the output is not an ipywidget, convert automatically? eg strings, graphs etc?
    if type(x) is list:
        output_list = x
    elif type(x) is tuple:
        output_list = list(x)
    elif x is None:
        output_list = []
    else:
        output_list = [x]
    return output_list


def high_level_function(original_function):
    """
    Decorator that simply collects some decorators which we use together all the time.

    The code

    @maybe_show_notifications
    @log_function
    @embeddable_with_outlet_blocking
    def original_function():
        pass

    becomes

    @high_level_function
    @embeddable_with_outlet_blocking
    def original_function():
        pass

    # see execution order
    # https://stackoverflow.com/questions/27342149/decorator-execution-order
    # wrapped = embeddable_with_outlet_blocking(wrapped)
    """

    @maybe_show_notifications
    @log_function
    @wraps(original_function)
    def patched_function(*args, **kwargs):
        return original_function(*args, **kwargs)

    return patched_function


def maybe_show_notifications(original_function):
    """
    Decorator that makes sure a user can only use decorated functions when she has a valid license.
    We apply this decorator to all customer facing functions.
    """

    @wraps(original_function)
    def patched_function(*args, show_notifications=True, **kwargs):
        error = authorization_service.get_authorization_error()
        if error is not None:
            return error

        embeddable = original_function(*args, show_notifications=False, **kwargs)

        return embeddable

    return patched_function


def log_function(original_function, **kwargs):
    """
    Decorator that logs the called function name.
    """

    @wraps(original_function)
    def logged_function(*args, **kwargs):
        log_action("viz", original_function.__name__, "called edaviz function")

        return original_function(*args, **kwargs)

    return logged_function


def log_class_init(original_function):
    """
    Decorator that logs the __init__ of a class.
    """

    @wraps(original_function)
    def logged_function(self, *args, **kwargs):
        log_action("viz", self.__class__.__name__, "called edaviz function")

        return original_function(self, *args, **kwargs)

    return logged_function


def _capture_traceback_in_widget(outlet=None):
    """Helper for _error_widget."""

    output = TracebackOutput()
    output.content += traceback.format_exc()
    return output


def _error_widget(error_msg=EMBEDDABLE_ERROR_MESSAGE, outlet=None):
    """
    Error widget object.

    :return: ipywidgets.VBox with the error message and error traceback
    """
    description = widgets.HTML(error_msg)
    traceback_ = _capture_traceback_in_widget(outlet=outlet)
    wrapped_content = widgets.VBox([description, traceback_])
    return wrapped_content


def lazy_widget_old(func, args=None, kwargs={}):
    """
    Lazy loads function func, passing args and kwargs to it.

    :param func: function to lazy-load.

    Usage:
    lazy_widget_old(missing_values_df, args=[df, df2], kwargs={'named_arg': 'lol'})

    Sample code:
    outlet, cb = lazy_widget_old(missing_values_df, [df])
    outlet
    cb()
    """

    loading = get_loading_widget()
    outlet = widgets.VBox([loading])

    def callback():
        try:
            func(*args, outlet=outlet, **kwargs)
        except:
            error_widget = _error_widget(LOADING_ERROR_MESSAGE, outlet=outlet)
            outlet.children = [error_widget]

    return outlet, callback


def new_lazy_widget_decorator(func, *args, **kwargs):
    """
    Lazy loads functions, passing args and kwargs to it.

    :param func: function to lazy-load.

    Usage:
    Like a normal function but the first attribute is the function which creates the widget, e.g.
    outlet, callback = new_lazy_widget_decorator(function, df, target, other_attr=other_attr, **kwargs)
    """

    loading = get_loading_widget()
    outlet = widgets.VBox([])
    outlet.children = [loading]

    def callback():
        try:
            func(*args, outlet=outlet, **kwargs)
        except:
            error_widget = _error_widget(LOADING_ERROR_MESSAGE, outlet=outlet)
            outlet.children = [error_widget]

    return outlet, callback


class Embeddable(widgets.VBox):
    """
    Makes sure all our EDA widgets are displayed where they belong inside of bamboolib.

    When you usually display widgets, you call display(). This however displays the widgets below the
    code cell where display() has been called. Embeddable gives us more control on where to display
    widgets.

    When the Embeddable should be able to be called like embeddable_with_outlet_blocking
    then we will create a new Subclass EmbeddableWithOutlet that can handle this type of call from external.
    This makes it easier to see if the alternative function signature is still needed
    """

    def __init__(self, *args, df_manager=None, parent_tabs=None, **kwargs):

        super().__init__()
        self.df_manager = df_manager
        self.parent_tabs = parent_tabs
        self.loading = get_loading_widget()
        self.__start_lifecycle__(
            *args, df_manager=df_manager, parent_tabs=parent_tabs, **kwargs
        )

    def __start_lifecycle__(self, *args, **kwargs):
        self.__call_init_embeddable__(*args, **kwargs)

    def __call_init_embeddable__(self, *args, **kwargs):
        try:
            self.init_embeddable(*args, **kwargs)
        except:
            self.set_content(_error_widget(EMBEDDABLE_ERROR_MESSAGE))

    def set_content(self, *contents):
        self.children = list(contents)


class AsyncEmbeddable(Embeddable):
    """
    An async version of Embeddable. Useful when creating the Embeddable should not block the kernel.
    """

    def __start_lifecycle__(self, *args, **kwargs):
        self.set_content(get_loading_widget())
        execute_asynchronously(self.__call_init_embeddable__, *args, **kwargs)


def _create_decorator_for_plain_embeddable(base_class):
    """
    Creates a decorator from base_class for plain embeddables. A plain embeddable is an embeddable
    that creates its own outlet (i.e. the space where it will display itself)
    """

    def decorator(old_function):
        class EmbeddableClass(base_class):
            def init_embeddable(self, *args, outlet=None, **kwargs):
                try:
                    output_list = _convert_to_list(old_function(*args, **kwargs))
                except:
                    output_list = [_error_widget(EMBEDDABLE_ERROR_MESSAGE)]

                if outlet is None:
                    self.set_content(*output_list)
                else:
                    # the outlet might be passed by new_lazy_widget_decorator or lazy_widget_old
                    # and then we need to show the output there
                    outlet.children = output_list

        @wraps(old_function)
        def return_embeddable(*args, **kwargs):
            return EmbeddableClass(*args, **kwargs)

        return return_embeddable

    return decorator


embeddable_plain_blocking = _create_decorator_for_plain_embeddable(Embeddable)
embeddable_plain_async = _create_decorator_for_plain_embeddable(AsyncEmbeddable)


def _create_decorator_for_embeddable_with_outlet(base_class):
    """
    Creates a decorator from base_class for embeddables with outlets. An embeddable with outlet is
    an embeddable whose outlet (i.e. the space where it will display itself) has already been created.
    """

    def decorator(old_function):
        class EmbeddableClass(base_class):
            def init_embeddable(
                self, *args, outlet=None, loading=None, border=False, **kwargs
            ):
                if outlet is None:
                    outlet = get_default_outlet()
                if loading is None:
                    loading = get_loading_widget()
                if border:
                    outlet.add_class("bamboolib-border-1px-solid-grey")

                try:
                    old_function(*args, outlet=outlet, loading=loading, **kwargs)
                except:
                    outlet.children = [_error_widget(EMBEDDABLE_ERROR_MESSAGE)]
                self.set_content(outlet)

        @wraps(old_function)
        def return_embeddable(*args, **kwargs):
            return EmbeddableClass(*args, **kwargs)

        return return_embeddable

    return decorator


embeddable_with_outlet_blocking = _create_decorator_for_embeddable_with_outlet(
    Embeddable
)
embeddable_with_outlet_async = _create_decorator_for_embeddable_with_outlet(
    AsyncEmbeddable
)


def user_exposed_function(original_function):
    """
    Decorator that maybe adds tabs in order to enable popup behavior etc.
    It is intended for high-level functions that the user might call directly via code.
    If the user calls the decorated function via code, we want to make sure she can still
    open interactive content in new tabs.

    This function should be used as the second decorator after the embeddable decorator because
    it needs to run before the embeddable is created.
    The wrapped functions need to receive df as first argument.
    """

    @wraps(original_function)
    def new_function(df, *args, df_manager=None, parent_tabs=None, **kwargs):
        return_tabs = False

        if df_manager is None:
            df_manager = DfManager(df)
        if parent_tabs is None:
            return_tabs = True
            parent_tabs = TabSection(df_manager)

        embeddable = original_function(
            df, *args, df_manager=df_manager, parent_tabs=parent_tabs, **kwargs
        )

        if return_tabs:
            from bamboolib.viz import EmbeddableToTabviewable

            tab_view = EmbeddableToTabviewable(
                title=original_function.__name__,
                embeddable=embeddable,
                df_manager=df_manager,
                parent_tabs=parent_tabs,
            )
            parent_tabs.add_tab(tab_view, closable=False)
            return parent_tabs
        else:
            return embeddable

    return new_function


def catch_empty_df(original_function):
    """
    Decorator that makes sure a function is not called if the dataset is empty.

    It can happen that after e.g. filtering in the GUI, the data has 0 rows. If a user then clicks on
    Explore Dataframe, it will be displayed with a message.
    """

    @wraps(original_function)
    def new_function(*args, **kwargs):
        df_manager = kwargs.get("df_manager", None)
        if df_manager is not None:
            row_count = df_manager.get_current_df().shape[0]
            if row_count == 0:
                return widgets.HTML(
                    "This component is not available because the dataframe contains 0 rows."
                )
        return original_function(*args, **kwargs)

    return new_function


class ColumnsReducer(AsyncEmbeddable):
    """
    Given a widget like the glimpse table or the correlation matrix, add a column selectize above
    the widget so that the user can look at results for specified columns. ColumnsReducer also only
    picks the first max_columns columns if the number of columns exceed max_columns.

    Wraps computation intensive widgets in order to avoid unnessarily long loading times.
    """

    def init_embeddable(
        self,
        df=None,
        max_columns=100,
        preview_columns_selection=None,  # this is usually passed in via kwargs but could also be accessed via df_manager
        on_render=None,
        columns_name="columns",
        render_content_after_init=True,
        **kwargs,
    ):
        """
        Set everything up and display the widget returned by on_render (if render_content_after_init
        is set to True)

        :param on_render: callable. Function that returns a widget.
        :param preview_columns_selection: list of columns that shall be pre-selected. None is default.
        """

        self.df = df
        self.on_render = on_render
        self.show_update_button = True

        self.content_outlet = widgets.VBox().add_class("bamboolib-min-height-250px")
        too_many_columns = len(df.columns) > max_columns

        self.selected_columns = TempColumnsSelector(
            df=df,
            show_all_columns=True,
            show_first_and_last=too_many_columns,
            selection=preview_columns_selection,
            on_change=lambda _: self._selection_changed(),
            width="sm",
            multi_select_width="xl",
        )

        header = []
        if too_many_columns:
            header.append(
                notification(
                    f"<b>Please note:</b> This component has a long loading time for more than {max_columns} {columns_name}.",
                    type="warning",
                )
            )
            header.append(VSpace("sm"))
        show_label = widgets.HTML("Show")
        show_label.add_class("bamboolib-element-next-to-selectize")

        show_line_contents = [show_label, self.selected_columns]
        if self.show_update_button:
            if render_content_after_init:
                description = "Update"
                style = "secondary"
            else:
                description = "Execute"
                style = "primary"
            show_line_contents.append(
                Button(
                    description=description,
                    on_click=lambda _: self._render_content(),
                    css_classes=["bamboolib-element-next-to-selectize"],
                    style=style,
                )
            )

        show_line = widgets.HBox(show_line_contents)
        show_line.add_class("bamboolib-overflow-visible")

        header.append(show_line)
        header.append(VSpace("md"))
        header.append(self.content_outlet)
        self.set_content(*header)

        # init
        if render_content_after_init:
            self._render_content()

    def _selection_changed(self):
        if self.show_update_button:
            return  # do nothing
        else:
            # Idea: also make this async?
            self._render_content()

    def _render_content(self):
        df_column_indices = self.selected_columns.value
        if len(df_column_indices) < 1:
            self.content_outlet.children = [widgets.HTML("Please select some columns")]
        else:
            self.content_outlet.children = [get_loading_widget()]
            # on_render might take a while if it is not async
            new_content = self.on_render(df_column_indices)
            self.content_outlet.children = [new_content]


class RowsSampler(AsyncEmbeddable):
    """
    Takes a random sample of the dataframe if it has too many rows to create plots in an acceptable
    time.
    """

    def init_embeddable(
        self, df=None, max_rows=get_option("plotly.row_limit"), notification_text=None, on_render=None, **kwargs
    ):
        self.df = df
        self.max_rows = max_rows
        self.on_render = on_render
        if notification_text is None:
            notification_text = f"Your dataframe has more than {self.max_rows:,} rows. This can lead to long loading times or your analysis might never show up. Therefore, we randomly sampled {self.max_rows:,} rows. You can remove the sampling. Alternatively, you can sample or filter the data yourself."
        self.notification_text = notification_text

        self.wrapped_content_outlet = widgets.VBox().add_class(
            "bamboolib-min-height-250px"
        )
        self.sample_df = df.shape[0] > max_rows

        self._render()

    def _remove_sampling(self):
        self.sample_df = False
        self._render()

    def _render(self):
        self._render_wrapping_content()
        self._render_wrapped_content()

    def _render_wrapping_content(self):
        content = []
        if self.sample_df:
            content += [
                notification(self.notification_text, type="warning"),
                Button(
                    description="Remove sampling",
                    on_click=lambda _: self._remove_sampling(),
                ),
                widgets.HTML("<br>"),
            ]
        content.append(self.wrapped_content_outlet)
        self.set_content(*content)

    def _render_wrapped_content(self):
        # on_render might take a while if it is not async
        self.wrapped_content_outlet.children = [get_loading_widget()]

        df = self.df
        if self.sample_df:
            df = df.sample(
                n=self.max_rows,
                replace=False,
                random_state=get_option("global.random_seed"),
            )

        new_content = self.on_render(df)
        self.wrapped_content_outlet.children = [new_content]
