# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

from IPython.display import display
from bamboolib.widgets.table_output import TableOutput
import ipywidgets as widgets
import pandas as pd

from bamboolib.helper import (
    log_jupyter_action,
    log_action,
    log_databricks_funnel_event,
    get_dataframe_variable_names,
)
import bamboolib.config as _config
from bamboolib.widgets import Button


def pandas_display_df(df, *args, **kwargs):
    log_jupyter_action("other", "JupyterCell", "pandas display(df)")

    display_data = {"text/plain": df.__repr__(), "text/html": df._repr_html_()}
    display(display_data, raw=True)


class ToggleRow(widgets.HBox):
    """
    A widget that allows the user to switch from the static pandas.Dataframe view to the bamboolib UI and back

    :param df: the pandas.Dataframe
    :param df_outlet: the widget in which the Dataframe is displayed
    :param static_html: a widget that holds the static HTML content
    :param bamboolib_ui: the widget that holds the interactive bamboolib_ui
    :param show_bamboolib_ui: bool, whether the bamboolib UI should automatically be opened once the bamboolib UI is ready. The user will activate this behaviour once she clicks on the "Show bamboolib UI" button.

    """

    def __init__(
        self, df, df_outlet, static_html, bamboolib_ui=None, show_bamboolib_ui=False
    ):
        super().__init__()
        self.df = df

        self.show_bamboolib_ui = show_bamboolib_ui
        self.loading = True

        self.static_html = static_html

        if bamboolib_ui is None:
            bamboolib_ui = self._get_loading_widget()
        self.bamboolib_ui = bamboolib_ui
        self.bamboolib_ui_outlet = widgets.VBox([self.bamboolib_ui])

        self.render()
        df_outlet.children = [static_html, self.bamboolib_ui_outlet]

    def _get_loading_widget(self):
        return widgets.HTML("bamboolib is loading ...")

    def _get_show_static_html_button(self):
        def click(button):
            self.show_bamboolib_ui = False
            _config.SHOW_BAMBOOLIB_UI = False
            self.render()
            try:
                log_action("general", "JupyterCell", "click 'Show static HTML' button")
            except:
                pass

        return Button(
            description="Show static HTML",
            css_classes=["bamboolib-button-secondary-outline"],
            on_click=click,
        )

    def _get_show_bamboolib_button(self):
        if self.loading:
            return self._get_loading_widget()
        else:

            def click(button):
                self.show_bamboolib_ui = True
                _config.SHOW_BAMBOOLIB_UI = True
                # Only show new version notification once per session
                _config.SHOW_NEW_VERSION_NOTIFICATION = False
                self.render()
                self._maybe_notify_bamboolib_ui()
                log_databricks_funnel_event("Show bamboolib UI - click")
                log_action("general", "JupyterCell", "click 'Show bamboolib UI' button")

            return Button(
                description="Show bamboolib UI",
                style="primary",
                css_classes=["bamboolib-show-ui-button"],
                on_click=click,
            )

    def render(self):
        if self.show_bamboolib_ui:
            header = self._get_show_static_html_button()
            self.static_html.add_class("bamboolib-hidden")
            self.bamboolib_ui_outlet.remove_class("bamboolib-hidden")
        else:
            header = self._get_show_bamboolib_button()
            self.static_html.remove_class("bamboolib-hidden")
            self.bamboolib_ui_outlet.add_class("bamboolib-hidden")
        self.children = [header]

    def _maybe_notify_bamboolib_ui(self):
        try:
            self.bamboolib_ui.show_ui()
        except AttributeError:
            # in case that the ui is not a wrangler but an error we cannot call show_ui
            # ... eg when the user df is not available as a variable
            pass

    def register_ui(self, bamboolib_ui):
        self.bamboolib_ui = bamboolib_ui
        self.bamboolib_ui_outlet.children = [bamboolib_ui]
        self.loading = False

        self.render()
        self._maybe_notify_bamboolib_ui()


def display_rich_df(df, app):
    """
    Displays a rich representation of the Dataframe that supports the formats:
    text/plain, text/html, and ipywidgets.

    The frontend then decides based on its capabilities which representation to show.
    The frontend usually shows the richest representation that is supports.
    Usually, the ipywidget-representation should be considered the richest representation.

    :param df: Dataframe
    :param app: ipywidget bamboolib app
    """
    app_widget_data = {"model_id": app._model_id}
    full_widget_data = {
        "text/plain": df.__repr__(),
        # "text/html": df._repr_html_(),
        "application/vnd.jupyter.widget-view+json": app_widget_data,
    }
    display(full_widget_data, raw=True)


def bamboolib_display_df(df, *args, **kwargs):
    """
    Displays the interactive bamboolib representation of a pandas.Dataframe
    :param df: pandas.Dataframe
    """
    from bamboolib.setup.user_symbols import get_user_symbols

    show_bamboolib_ui = _config.SHOW_BAMBOOLIB_UI
    if show_bamboolib_ui:
        log_jupyter_action("other", "JupyterCell", "bamboolib display(df) - UI")
    else:
        log_jupyter_action("other", "JupyterCell", "bamboolib display(df) - static")

    df_html_output = TableOutput(df)
    df_outlet = widgets.VBox([df_html_output])

    toggle_row = ToggleRow(
        df, df_outlet, df_html_output, show_bamboolib_ui=show_bamboolib_ui
    )

    app_outlet = widgets.VBox([toggle_row, df_outlet])
    display_rich_df(df, app_outlet)

    # Attention: symbols and df_name need to be determined before thread
    # because otherwise the symbols cannot be retrieved via inspect
    # and the df identities and names might change in parallel/following code
    symbols = get_user_symbols()
    possible_df_names = get_dataframe_variable_names(df, symbols)
    df_name = None if len(possible_df_names) == 0 else possible_df_names[0]

    lazy_load_bamboolib_ui(df, toggle_row, symbols, df_name)


def lazy_load_bamboolib_ui(df, toggle_row, symbols, df_name):
    """
    Asynchronously creates and shows the bamboolib Dataframe UI

    :param df: pandas.Dataframe
    :param toggle_row: ToggleRow - the manager for toggling the representations
    :param symbols: dict - user namespace symbols
    :param df_name: str - variable name of the df
    """
    from bamboolib.wrangler import create_dataframe_ui

    def load_bamboolib_ui():
        toggle_row.register_ui(
            create_dataframe_ui(
                df, symbols=symbols, origin="ipython_display", df_name=df_name
            )
        )

    from bamboolib.helper import execute_asynchronously

    execute_asynchronously(load_bamboolib_ui)


def extend_pandas_ipython_display():
    """
    Changes the representation of all pandas.Dataframes to use the interactive bamboolib representation
    """
    pd.DataFrame._ipython_display_ = bamboolib_display_df


def reset_pandas_ipython_display():
    """
    Reset the pandas.Dataframe representation to not include the rich bamboolib UI
    """
    pd.DataFrame._ipython_display_ = pandas_display_df
