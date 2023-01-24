# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import textwrap
from IPython.display import display

import ipywidgets as widgets
import pandas as pd
import numpy as np

from bamboolib import _environment as env
from bamboolib.helper.utils import (
    log_action,
    log_view,
    log_databricks_funnel_event,
    replace_code_placeholder,
    VSpace,
    exec_code,
)
from bamboolib.helper.error import BamboolibError
from bamboolib.helper.gui_outlets import (
    show_loader_and_maybe_error_modal,
    TabWindow,
    Window,
    WindowToBeOverriden,
    WindowWithLoaderAndErrorModal,
)
from bamboolib.widgets import Text, Button, BrowserCheck


def if_new_df_name_is_invalid_raise_error(new_df_name: str) -> None:
    if new_df_name.isidentifier():
        pass  # all good, the df_name seems to be a valid variable name
    else:
        # IMPORTANT: users who trigger this error very likely have little knowledge about Python
        # So, we need to explain this very clearly so that they accept those constraints of Python
        # because in the GUI world they often can give stuff any name they want

        # rules for writing identifiers
        # https://www.journaldev.com/13996/python-keywords-identifiers#:~:text=Rules%20for%20writing%20Identifiers,-There%20are%20some&text=That%20means%20Name%20and%20name%20are%20two%20different%20identifiers%20in%20Python.&text=Identifiers%20can%20be%20combination%20of,can%20not%20start%20with%20digit.
        raise BamboolibError(
            f"""The name of the new dataframe <code>{new_df_name}</code> is invalid because it is not a valid name for a Python variable.<br>
    <br>
    Please adjust the name and ensure the following:
    <ul>
    <li>The name contains no whitespace</li>
    <li>The name does not start with a number</li>
    <li>The name contains no special characters like !,#,@,%,$</li>
    </ul>
    <br>
    The following examples are valid names:
    <ul>
    <li><code>result</code></li>
    <li><code>dataframe_cleaned_2014</code></li>
    <li><code>df_IMPORTANT</code></li>
    </ul>
    """
        )


class Viewable:
    """
    The Viewable base class for content that can be shown within a Window

    Usage:
    - you have to override the `render` method to define the visual output
    - you have to call the `render_in` or `add_to` method to add the Viewable to a displayed Window

    Additionally, you might want to override the `get_exception_message` method


    Methods that you can use:
    - set_content
    - set_title
    - on_did_render
    - update
    - hide
    - is_displayed
    - is_visible
    - get_df

    """

    outlet = WindowToBeOverriden()  # The outlet needs to be a valid Window

    def render(self):
        """
        TO BE OVERRIDEN

        Use `set_content` and `set_title` to define the layout
        """
        raise NotImplementedError

    def get_exception_message(self, exception):
        """
        CAN BE OVERRIDEN

        Use it to show a custom message when an exception occured during a function that is wrapped
        with the `show_loader_and_maybe_error_modal` decorator e.g. the most common case is `execute`
        within a Transformation but this might also be another function of a Viewable
        """
        return None

    def __init__(
        self, *any_positional_arguments, df_manager=None, df=None, symbols={}, **kwargs
    ):
        if any_positional_arguments:
            raise ValueError(
                f"{self.__class__.__name__} only accepts keyword arguments, e.g. {self.__class__.__name__}(df=df)"
            )

        if df is not None:
            if isinstance(df, pd.DataFrame):
                from bamboolib.df_manager import (
                    DfManager,
                )  # inline import to prevent circular import

                df_manager = DfManager(df, symbols=symbols)
            else:
                raise ValueError(
                    f"The df keyword-argument needs to be a pandas.DataFrame or None but it is a {type(df)}"
                )

        self.df_manager = df_manager
        self.kwargs = kwargs
        self.spacer = VSpace("lg")

        self._did_render_callbacks = widgets.CallbackDispatcher()

    def _start_render_lifecycle(self, *args, **kwargs):
        self.render(*args, **kwargs)
        log_view("views", self, "render view")
        self._did_render_callbacks(self)

    def _setup_outlet(self, outlet, *args, push=False, **kwargs):
        self.outlet = outlet
        if push:
            self.outlet.push_view(self)
        else:
            self.outlet.show_view(self)
        self._start_render_lifecycle(*args, **kwargs)
        self.outlet.show()

    def on_did_render(self, callback, remove=False):
        """
        Add or remove an on_did_render callback.

        :param callback: a function that expects the widget itself as single argument
        :param remove: boolean

        Example:
        >>> viewable.on_did_render(lambda viewable: print("I was rendered!"))
        """
        self._did_render_callbacks.register_callback(callback, remove=remove)

    def render_in(self, outlet, *args, **kwargs):
        """
        Render the Viewable in the given outlet.
        This will also potentially remove any other Viewables from the outlet

        :param outlet: e.g. a `Window` instance
        """
        self._setup_outlet(outlet, *args, **kwargs)

    def add_to(self, outlet, *args, **kwargs):
        """
        Add the Viewable to the given outlet.
        This will add the Viewable to the top of the view hierarchy stack of the outlet.

        :param outlet: e.g. a `Window` instance
        """
        self._setup_outlet(outlet, *args, push=True, **kwargs)

    def update(self):
        """
        Potentially trigger a rerender of the Viewable
        """
        if self.is_displayed():
            self._start_render_lifecycle()

    def set_content(self, *embeddables, **kwargs):
        """
                Set the content of the Viewable's outlet. `set_content`
        is typically used inside `render`


                :param embeddables: unpacked list of embeddable widgets

                Example
                >>> import ipywidgets as widgets
                >>> def render(self):
                ...     self.set_title("Filter rows")
                ...     self.set_content(
                ...         # Use VBox to stack elements vertically
                ...         widgets.VBox([
                ...              widgets.HTML("Filter rows where Age < 18"),
                ...              widgets.Button("Start filtering")
                ...         ])
                ...     )
        """
        content_list = list(embeddables)
        self.outlet.set_content(widgets.VBox(content_list))

    def set_title(self, title):
        """
        Set the title for the Viewable's outlet which usually appears at the top. `set_title` is typically
        used inside `render`.



        :params title: str

        Example
        >>> def render(self):
        ...     self.set_title("Filter rows")
        """
        self.outlet.set_title(title)

    def hide(self):
        """
        Hide the Viewable (via hiding its outlet)
        """
        self.outlet.hide()

    def is_displayed(self):
        """
        :return bool if the Viewable is displayed inside a Window.

        Should be used to determine if (re)rendering a Viewable makes any sense.
        """
        return self.outlet.does_display(self)

    def is_visible(self):
        """
        :return bool if the Viewable is visible. That means that the outlet is visible and that the Viewable is displayed within the outlet
        """
        return self.is_displayed() and self.outlet.is_visible()

    def get_df(self):
        """
        :return the current DataFrame of the attached DataFrameManager (if any)
        :raises BamboolibError: when the method is called but no DataframeManager exists
        """
        if self.df_manager is not None:
            return self.df_manager.get_current_df()
        else:
            raise BamboolibError(
                "get_df() is not available because this viewable does not have a DataframeManager"
            )


class TabViewable(Viewable):
    """
    Base class for Viewables that can be shown within a TabSection

    In contrast to a Viewable, the TabViewable is also able to receive events via the
    `df_did_change` and `tab_got_selected` methods.

    Attention: the outlet should always be a `TabWindow`
    """

    def __init__(self, *args, parent_tabs=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_tabs = parent_tabs
        self._df_is_outdated = False

    def df_did_change(self):
        """
        Call this method when the DataFrame did change
        """
        self._df_is_outdated = True

    def tab_got_selected(self):
        """
        Call this method when the tab of this TabViewable got selected
        """
        if self._df_is_outdated:
            self._df_is_outdated = False
            self.render()

    def render_in(self, outlet):
        if isinstance(outlet, Window):
            super().render_in(outlet)
        else:
            # the outlet is a TabSection
            # this is a hotfix to enable the same API for TabViewables e.g.
            # `TabViewable().render_in(tab_section)`
            outlet.add_tab(self)

    def set_content(self, *embeddables, **kwargs):
        # Attention: this method was overriden and copied from Viewable
        # because we need to add a class to the wrapping widgets.VBox
        # This ensures that TabViewables have a min-height
        content_list = list(embeddables)
        box = widgets.VBox(content_list)
        box.add_class("bamboolib-min-height-for-tab-viewables")
        self.outlet.set_content(box)

    def _ipython_display_(self, *args, **kwargs):
        """
        This method is called by Jupyter when trying to display the object.
        We are setting up all the surrounding classes that are needed for the experience
        of displaying a TabViewable within a properly setup TabSection
        """
        from bamboolib.wrangler import (
            Wrangler,
        )  # inline import to prevent circular import

        df_manager = self.df_manager
        tab_section = TabSection(df_manager)
        tab_section.add_tab(
            Wrangler(df_manager=df_manager, parent_tabs=tab_section), closable=False
        )
        tab_section.add_tab(self, closable=False)
        display(tab_section)


class Transformation(Viewable):
    """
    The base class for Transformations

    A Transformation transforms a DataFrame into another DataFrame via applying some kind of data manipulation.
    A Transformation has a visual representation of its state (it is a Viewable).

    This class is also exposed to external users via `TransformationPlugin`.
    To see an overview of the most important methods and attributes, please check
    https://github.com/tkrabel/bamboolib/tree/master/plugins#bamboolibpluginstransformationplugin

    To see examples, please check:
    https://github.com/tkrabel/bamboolib/tree/master/plugins/examples/transformations
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.result = None

        # we use an outlet for the transformation_insight so that we can easily adjust the content later if we want
        # if we would just store the content, we could not make updates to it without rerendering the surrounding outlet
        self._bam_transformation_insight_outlet = widgets.VBox()

        self.code_preview_outlet = widgets.HTML()

        self.code_preview_update_button = Button(
            icon="refresh", on_click=lambda _: self.update_code_preview()
        )

        self.code_preview_group = widgets.VBox(
            [
                self.spacer,
                widgets.HBox(
                    [
                        self.code_preview_update_button,
                        widgets.HTML("<b>Code preview:</b>"),
                    ]
                ),
                self.code_preview_outlet,
            ]
        )

        self.new_df_name_input = Text(
            value=self.get_name_of_df(),
            description="New dataframe name",
            on_change=self._maybe_update_code_preview,
            width="lg",
            execute=self,
        )
        self.rename_df_group = widgets.VBox([self.spacer, self.new_df_name_input])

        self.new_column_name_input = Text(
            description="New column name",
            on_change=self._maybe_update_code_preview,
            width="lg",
            execute=self,
        )
        self.rename_column_group = widgets.VBox(
            [self.spacer, self.new_column_name_input]
        )

        self.execute_button = Button(
            description="Execute", style="primary", on_click=lambda _: self.execute()
        )

        self.on_did_render(lambda self: self._maybe_update_code_preview())

    def set_column(self, column):
        """
        Set the `column` attribute which is used inside the `rename_column_group`
        :param column: str - name of the column
        """
        if column is None:
            raise BamboolibError("The column value should not be None")
        else:
            self.column = column
            self.new_column_name_input.value = column

    def get_name_of_df(self):
        """
        :return str - variable name of the current DataFrame
        """
        return self._get_old_df_name()

    def _get_code_preview_value(self):
        return f"<code>{self.get_final_code()}</code>"

    def update_code_preview(self, *args, **kwargs):
        """
        Request an update do the `code_preview_group`
        """
        self.code_preview_outlet.value = self._get_code_preview_value()

    def _maybe_update_code_preview(self, *args, **kwargs):
        try:
            self.update_code_preview()
        except:
            # the update_code_preview might fail if there are any issues with the code generation
            # eg the user did not fill in all the fields or similar
            pass

    def set_content(self, *embeddables, **kwargs):
        """
        Method to set the content of the Transformation.
        In addition, the `execute_button` will be added.

        Example:
        >>> transformation.set_content(widgets.HTML("My name"), widgets.HTML("Something else"))
        """
        execute_section = [self.spacer, self.execute_button]
        content_list = list(embeddables) + execute_section
        content = widgets.VBox(content_list)

        from bamboolib.widgets.focus_box import FocusBox

        content = FocusBox([content])

        self.outlet.set_content(content)

    def execute(self, *args, **kwargs):
        """
        Execute the transformation. There will be feedback about the process in the user interface.
        There is no result value but the `result` attribute will change in place
        """
        if env.DEACTIVATE_ASYNC_CALLS:
            self._execute_internal(self, *args, **kwargs)
        else:
            self._execute_asynchronously_and_with_error_catching(self, *args, **kwargs)

    @show_loader_and_maybe_error_modal
    def _execute_asynchronously_and_with_error_catching(self, *args, **kwargs):
        # This thin wrapper provides the loading screen for the transformation AND
        # executes the transformation asynchronously via the decorator
        return self._execute_internal(*args, **kwargs)

    def _execute_internal(self, *args, **kwargs):
        if_new_df_name_is_invalid_raise_error(self._get_new_df_name())

        if not self.is_valid_transformation():
            return False  # errors should be handled within is_valid_transformation

        is_update = self._is_update()

        self.result = {
            "result_df": self.get_result_df(),
            "description": self.get_description(),
            # what is the reason against using self.get_final_code() here?
            # who is later using the code template in a different way? and why?
            "code": self.get_code(),
            "type": self._get_type(),
            "old_df_name": self._get_old_df_name(),
            "new_df_name": self._get_new_df_name(),
            "preview_columns_selection": self.get_preview_columns_selection(),
        }
        self._log_metainfos(is_update=is_update)

        self.df_manager.update_transformation(self)
        # calculating the insight needs to happen AFTER the transformation is registered with the df_manager
        # because during the calculation of the insight, we make use of the df_manager e.g. current_df and penultimate_df etc
        self._bam_transformation_insight_outlet.children = [
            self.get_transformation_insight()
        ]
        return True  # hide_modal in case there is a loader_modal

    def _log_metainfos(self, is_update=False):
        if is_update:
            action_name = "execute update"
        else:
            action_name = "execute first time"

        metainfo_kwargs = self.get_metainfos()
        metainfo_kwargs["renamed_df"] = self.df_was_renamed()

        log_databricks_funnel_event("Transformation - execute")
        log_action(
            "transformation", self.result["type"], action_name, **metainfo_kwargs
        )

    def get_metainfos(self):
        """
        CAN BE OVERRIDEN

        Return a dict with meta information about the transformation
        """
        return {}

    def _is_update(self):
        return self.result is not None

    def _get_old_df_name(self):
        if self._is_update():
            return self.df_manager.get_penultimate_df_name()
        else:
            return self.df_manager.get_current_df_name()

    def _get_new_df_name(self):
        return self.new_df_name_input.value.strip()

    def df_was_renamed(self):
        """
        :return bool if the Dataframe was renamed as part of the transformation
        """
        return self._get_old_df_name() != self._get_new_df_name()

    def is_valid_transformation(self) -> bool:
        """
        CAN BE OVERRIDEN

        This method is called before the transformation gets executed.
        The transformation is only executed if this method returns True.
        You can override this method to raise BamboolibErrors or to stop the execution process.

        :return bool if the transformation is valid and can be executed
        """
        return True

    def if_new_df_name_is_invalid_raise_error(self) -> None:
        new_df_name = self._get_new_df_name()
        if new_df_name.isidentifier():
            pass  # all good, the df_name seems to be a valid variable name
        else:
            # IMPORTANT: users who trigger this error very likely have little knowledge about Python
            # So, we need to explain this very clearly so that they accept those constraints of Python
            # because in the GUI world they often can give stuff any name they want

            # rules for writing identifiers
            # https://www.journaldev.com/13996/python-keywords-identifiers#:~:text=Rules%20for%20writing%20Identifiers,-There%20are%20some&text=That%20means%20Name%20and%20name%20are%20two%20different%20identifiers%20in%20Python.&text=Identifiers%20can%20be%20combination%20of,can%20not%20start%20with%20digit.
            raise BamboolibError(
                f"""The name of the new dataframe <b>{new_df_name}</b> is invalid because it is not a valid name for a Python variable.<br>
        <br>
        Please adjust the name and ensure the following:
        <ul>
        <li>The name contains no whitespace</li>
        <li>The name does not start with a number</li>
        <li>The name contains no special characters like !,#,@,%,$</li>
        </ul>
        <br>
        The following examples are valid names:
        <ul>
        <li>result</li>
        <li>dataframe_cleaned_2014</li>
        <li>df_IMPORTANT</li>
        </ul>
        """
            )

    def get_df(self):
        """
        :return the reference to DataFrame that is the input to this transformation
        """
        if self._is_update():
            return self.df_manager.get_penultimate_df()
        else:
            return self.df_manager.get_current_df()

    def get_final_code(self):
        """
        :return the final code that a user would have to write to create the same result
        """
        code = textwrap.dedent(self.get_code())
        code = replace_code_placeholder(
            code,
            old_df_name=self._get_old_df_name(),
            new_df_name=self._get_new_df_name(),
        )
        return code

    def eval_code(self, code):
        """
        Evaluate the given code as if the user would have written it and return the result
        :param code: str
        :return object - evaluation result
        """
        symbols = self.df_manager.symbols.copy()
        symbols["pd"] = pd
        symbols["np"] = np

        old_df_name = self._get_old_df_name()
        symbols[old_df_name] = self.get_df()

        user_code = replace_code_placeholder(code, old_df_name=old_df_name)

        return eval(user_code, symbols, symbols)

    def get_result_df(self):
        """
        :return DataFrame - result/output of the transformation
        """
        # ATTENTION: for Loader, we sometimes manipulate the user symbols
        # read the comment there and maybe streamline the behavior at one point?

        # use copy so that we dont overwrite anything for the user per default
        # live_code_export might adjust the user symbols if activated
        symbols = self.df_manager.symbols.copy()

        symbols["pd"] = pd
        symbols["np"] = np
        symbols[self._get_old_df_name()] = self.get_df().copy()
        # the copy is only needed if the code does an inplace manipulation of the df like update values

        code = self.get_final_code()
        if env.DEBUG_CODE:
            display(code)

        # use this instead of `exec(code, {}, symbols)` to fix an error in nested list comprehension
        exec(code, symbols, symbols)
        return symbols[self._get_new_df_name()]

    def get_description(self):
        """
        CAN BE OVERRIDEN

        :return str - description of what the transformation does. This is e.g. shown in the transformation history
        """
        raise NotImplementedError

    def get_code(self):
        """
        SHOULD BE OVERRIDEN

        :return str - code for the transformation which should contain placeholders like DF_OLD, DF_NEW, etc
        """
        raise NotImplementedError

    def get_transformation_insight(self):
        """
        CAN BE OVERRIDEN

        :return - embeddable which shows an insight about the transformation e.g. how many rows were dropped
        """
        return widgets.VBox()  # nothing per default

        # # example for a button that opens a tab on_click
        # from bamboolib.viz import ColumnSummary
        # return Button(
        #     description="test",
        #     on_click=lambda _: ColumnSummary(
        #         column="Pclass",
        #         df_manager=self.df_manager,
        #         parent_tabs=self.df_manager.tab_section
        #     ).render_in(self.df_manager.tab_section),
        # )

    def get_preview_columns_selection(self):
        """
        :return preview_columns_selection object

        This can be used to already select some of the preview columns in the wrangler after the transformation.
        """
        if self.reset_preview_columns_selection():
            return None
        else:
            # selection from current df view
            return self.df_manager.get_preview_columns_selection()

    def reset_preview_columns_selection(self) -> bool:
        """
        CAN BE OVERRIDEN

        :return bool if the preview columns selection in the Wrangler should be reset after the execution of the transformation
        """
        return False

    def _get_type(self):
        return type(self).__name__

    def _ipython_display_(self, *args, **kwargs):
        """
        This method is called by Jupyter when trying to display the object.
        We are setting up all the surrounding classes that are needed for the experience
        of displaying the Transformation
        """
        from bamboolib.wrangler import Wrangler  # prevent circular import

        df_manager = self.df_manager
        tab_section = TabSection(df_manager)
        wrangler = Wrangler(df_manager=df_manager, parent_tabs=tab_section)
        tab_section.add_tab(wrangler, closable=False)
        wrangler.display_transformation(self)
        display(tab_section)


class Loader(TabViewable):
    """
    The base class for Loaders

    A Loader executes code that results in a DataFrame e.g. reading a CSV file
    It has a visual representation of its state (it is a Viewable).

    This class is also exposed to external users via `LoaderPlugin`.
    To see an overview of the most important methods and attributes, please check
    https://github.com/tkrabel/bamboolib/tree/master/plugins#bamboolibpluginsloaderplugin

    To see examples, please check:
    https://github.com/tkrabel/bamboolib/tree/master/plugins/examples/loaders
    """

    new_df_name_placeholder = "data"

    def __init__(self, *args, symbols={}, parent_outlet=widgets.VBox(), **kwargs):
        super().__init__(*args, **kwargs)
        self.symbols = symbols
        self._parent_outlet = parent_outlet
        self.df_manager = None

        self.new_df_name_input = Text(
            value=self.new_df_name_placeholder,
            description="Dataframe name",
            width="lg",
            execute=self,
        )
        self.new_df_name_group = widgets.VBox([self.spacer, self.new_df_name_input])

        self.execute_button = Button(
            description="Execute", style="primary", on_click=lambda _: self.execute()
        )

    def execute(self, *args, **kwargs):
        if env.DEACTIVATE_ASYNC_CALLS:
            self._execute_internal(self, *args, **kwargs)
        else:
            self._execute_asynchronously_and_with_error_catching(self, *args, **kwargs)

    @show_loader_and_maybe_error_modal
    def _execute_asynchronously_and_with_error_catching(self, *args, **kwargs):
        # This thin wrapper provides the loading screen for the transformation AND
        # executes the transformation asynchronously
        return self._execute_internal(*args, **kwargs)

    def _execute_internal(self, *args, **kwargs):
        if_new_df_name_is_invalid_raise_error(self._get_new_df_name())

        if not self.is_valid_loader():
            return False  # errors should be handled within is_valid_loader

        if self.df_manager is None:
            # this is the first execution of the Loader
            initial_user_code = None  # we do not know the initial_user_code
        else:
            # this is a subsequent execution of Loader
            # we restore initial_user_code to overwrite potential code changes in the cell from the old DfManager
            initial_user_code = self.df_manager.get_initial_user_code()

        df_name = self._get_new_df_name()
        code = self.get_final_code()

        # ATTENTION: the Loader always manipulates the user symbols in order to add the df
        # This is currently in contrast to the Transformation which only manipulates the symbols
        # when the live_code_export is activated
        # COMPLICATION: when the live_code_export is deactivated, Loader manipulates the symbols
        # but does not show the code in Jupyter because the Wrangler/DfManager trigger the code export
        df = exec_code(
            code, symbols=self.symbols, result_name=df_name, manipulate_symbols=True, add_pandas_and_numpy=True
        )

        from bamboolib.df_manager import DfManager  # inline to prevent circular import
        from bamboolib.wrangler import Wrangler  # inline to prevent circular import

        self.df_manager = DfManager(
            df,
            self.symbols,
            setup_code=code,
            df_name=df_name,
            initial_user_code=initial_user_code,
        )
        tab_section = TabSection(self.df_manager)
        tab_section.add_tab(self, closable=False)
        tab_section.add_tab(
            Wrangler(df_manager=self.df_manager, parent_tabs=tab_section),
            closable=False,
        )
        self._parent_outlet.children = [tab_section]
        # IMPORTANT: Don't return True (like in Transformation) because then the first tab with the loader won't be shown any more

    def _get_new_df_name(self):
        return self.new_df_name_input.value.strip()

    def is_valid_loader(self) -> bool:
        """
        CAN BE OVERRIDEN

        This method is called before the loader gets executed.
        The loader is only executed if this method returns True.
        You can override this method to raise BamboolibErrors or to stop the execution process.

        :return bool if the loader is valid and can be executed
        """
        return True

    def get_final_code(self):
        """
        :return the final code that a user would have to write to create the same result
        """
        code = textwrap.dedent(self.get_code())
        code = replace_code_placeholder(code, new_df_name=self._get_new_df_name())
        return code

    def get_code(self):
        """
        SHOULD BE OVERRIDEN

        :return str - code for the loader which should contain placeholders like DF_NEW, etc
        """
        raise NotImplementedError

    def _ipython_display_(self, *args, **kwargs):
        """
        This method is called by Jupyter when trying to display the object.
        We are setting up all the surrounding classes that are needed for the experience
        of displaying the Loader
        """

        from bamboolib.setup.user_symbols import (
            get_user_symbols,
        )  # inline to prevent circular import

        self.symbols = get_user_symbols()
        parent_outlet = WindowWithLoaderAndErrorModal()
        self._parent_outlet = parent_outlet
        self.render_in(parent_outlet)
        display(parent_outlet)


class TabSection(widgets.VBox):
    """
    The base class for creating a TabSection

    A TabSection has a header with many tabs where the user can switch between tabs, and, potentially, close tabs.
    """

    def __init__(self, df_manager):
        super().__init__()
        self.add_class("bamboolib-ui")

        self.df_manager = df_manager
        self.df_manager.register_tab_section(self)

        self.tab_windows = []
        self.active_window = None

        self.header = widgets.HBox()
        self.header.add_class("bamboolib-tab-header")
        self.main_outlet = OutletManager()

        self.render()
        # Attention: the BrowserCheck implicitly handles authorization because after it gets
        # rendered, it gathers information from the browser and then triggers an auth check
        self.children = [BrowserCheck(self), self.header, self.main_outlet]

    def render(self):
        self.header.children = [tab_window.tab for tab_window in self.tab_windows]
        if len(self.tab_windows) <= 1:
            self.header.add_class("bamboolib-hidden")
        else:
            self.header.remove_class("bamboolib-hidden")

    def activate_tab(self, tab_window):
        """
        :param tab_window: TabWindow that should be activated/selected
        """
        if self.active_window:
            self.active_window.tab.remove_class("bamboolib-tab-active")
            self.active_window.outlet.add_class("bamboolib-hidden")

        tab_window.tab.add_class("bamboolib-tab-active")
        tab_window.outlet.remove_class("bamboolib-hidden")

        tab_window.tab_got_selected()
        self.active_window = tab_window

        self.render()

    def _get_new_active_tab_window(self, closed_tab_window):
        old_index = self.tab_windows.index(closed_tab_window)
        if old_index >= len(self.tab_windows) - 1:
            new_tab_window = self.tab_windows[-2]
        else:
            new_tab_window = self.tab_windows[old_index + 1]
        return new_tab_window

    def remove_tab(self, tab_window):
        """
        :param tab_window: TabWindow that should be removed/deleted
        """
        if tab_window == self.active_window:
            new_tab_window = self._get_new_active_tab_window(tab_window)
            self.activate_tab(new_tab_window)

        tab_window.outlet.children = []  # clears outlet
        try:
            self.tab_windows.remove(tab_window)
        except:
            pass  # user clicked faster than the gui thread
        self.render()

    def add_tab(self, viewable, closable=True):
        """
        :param viewable: Viewable that should be added as tab
        :param closable: bool if the user can close/delete the tab e.g. via clicking on the X icon
        """
        from bamboolib.widgets import Tab

        new_tab = Tab(closable=closable)
        outlet = self.main_outlet.get_new_outlet()
        tab_window = TabWindow(self, viewable, new_tab, outlet)
        new_tab.on_click(lambda _: self.activate_tab(tab_window))
        new_tab.on_close(lambda _: self.remove_tab(tab_window))

        viewable.render_in(tab_window)

    def register_window(self, tab_window):
        """
        :param tab_window: the TabWindow that should be registered at the TabSection
        """
        self.tab_windows.append(tab_window)

    def df_did_change(self):
        """
        Notify all tabs that the DataFrame did change
        """
        for tab_window in self.tab_windows:
            tab_window.df_did_change()

    def show_ui(self):
        """
        Show the user interface
        """
        if self.active_window:
            self.active_window.tab_got_selected()


class OutletManager(widgets.VBox):
    """
    This class provides many outlets.
    The advantage in contrast to a normal outlet is that there is no flickering when
    assigning a widget to some outlet's children.
    This is achieved via adding new, empty widgets to the children of an (already/still) empty widgets.VBox
    instead of overwriting many children of a single outlet.
    """

    def __init__(self):
        super().__init__()
        self.outlets = self._new_outlets()
        self.children = self.outlets

    def get_new_outlet(self):
        new_index = self._get_index_of_empty_outlet()

        # if all outlets are full (except the last)
        if new_index == (len(self.outlets) - 1):
            # create new outlets and append them to the last one in order to skip rerendering
            new_outlets = self._new_outlets()
            self.outlets[new_index].children = new_outlets
            # override the value of self.outlets so that we can conveniently loop over all the outlets
            # this assignment does not trigger a rerender because this only happens when children are assigned
            # This leads to an interesting data structure because self.outlets holds all outlets in a list
            # but only the initial outlets are rendered and the new outlets are added/rendered incrementally
            # to the last outlet's children. Thus, self.outlets is a flat list but the DOM structure
            # is a tree that always grows deeper on the last node
            self.outlets = self.outlets + new_outlets
            new_index += 1
        return self.outlets[new_index]

    def _new_outlets(self):
        return [widgets.VBox() for i in range(10)]

    def _get_index_of_empty_outlet(self):
        for index, outlet in enumerate(self.outlets):
            if len(outlet.children) == 0:
                return index
