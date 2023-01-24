# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import sys
from IPython.display import display
from bamboolib.helper.utils import notification
import ipywidgets as widgets

from bamboolib import __version__
from bamboolib._authorization import auth
from bamboolib.setup.user_symbols import get_user_symbols
from bamboolib.helper import (
    exec_code,
    if_new_df_name_is_invalid_raise_error,
    show_loader_and_maybe_error_modal,
    TabSection,
    TabViewable,
    Viewable,
    VSpace,
    Window,
    WindowWithLoaderAndErrorModal,
)
from bamboolib.df_manager import DfManager
from bamboolib.wrangler import Wrangler
from bamboolib.widgets import Button
from bamboolib.views.data_loader import (
    CSVLoader,
    CSVOptions,
    ExcelLoader,
    ExcelOptions,
    CSVFromDBFSLoader,
    ParquetOptions,
    ParquetFromDBFSLoader,
)
from bamboolib.plugins import LoaderPlugin


SHOW_ABOUT_INFO = False


def setup_module_view(module_name):
    """
    Change the representation of the module (e.g. bamboolib, bam) to be an interactive widget instead of just a string to the module's file

    :param module_name: str - the name of the module e.g. usually "bamboolib"

    Attention: This method needs to be called at the end of the module's primary __init__.py
    Otherwise, it won't work as intended
    """
    original_module = sys.modules[module_name]
    sys.modules[module_name] = BamboolibModuleWrapper(original_module)


class BamboolibModuleWrapper:
    """
    A wrapper that adds an interactive representation to a module

    :param original_module: the module that should receive the representation
    """

    # the module view logic is inspired by
    # https://stackoverflow.com/questions/1725515/can-a-python-module-have-a-repr

    def __init__(self, original_module):
        super().__init__()

        # Attention: any attribute added to this class will automatically be exposed via bam
        self.__original_module__ = original_module
        self.__user_symbols__ = {}

        for attribute in dir(self.__original_module__):
            setattr(self, attribute, getattr(self.__original_module__, attribute))

    def _ipython_display_(self, *args, **kwargs):
        # getting the symbols needs to happen outside of a thread AND within Jupyter
        # We do it here because this runs within Jupyter - the init might run in a auto-startup script or so
        self.__user_symbols__ = get_user_symbols()

        # Attention: we always load a new window and don't show an existing one
        # This is important so that the user can always reset the view via calling bam again
        # Also, this enables us to maybe add a close button to the Window in the future
        display(BamboolibModuleWindow(self))


class BamboolibModuleWindow(widgets.VBox):
    """
    The main class for the bamboolib module representation that holds the output window and the modal outlet.
    """

    def __init__(self, module_wrapper):
        super().__init__()
        self.add_class("bamboolib-ui")

        self.main_window = Window(
            show_header=False, css_classes=["bamboolib-window-without-border"]
        )
        self.modal_outlet = WindowWithLoaderAndErrorModal(
            show_header=True,
            on_show=lambda: self.main_window.hide(),
            on_hide=lambda: self.main_window.show(),
        )
        self.children = [self.main_window, self.modal_outlet]

        # As of Jan 24 2022 this fixes the following bug tracked in jira as [PROD-27105]
        # by communicating the error and resolution to the user.
        # When everything works fine, the message won't be seen by the user.
        # https://databricks.atlassian.net/browse/PROD-27105?atlOrigin=eyJpIjoiODgyMDM2YzcxYmZlNDg4MDhkM2FkMDQwYzhkMGI1YzgiLCJwIjoiaiJ9
        self.main_window.children = [
            widgets.HTML("Error: Could not display the widget. Please re-run the cell.")
        ]

        Overview(module_wrapper, self).render_in(self.main_window)


class AboutInfoToggle(widgets.VBox):
    """
    This widget contains all the information about bamboolib we don't want to display to
    the user directly, but hide inside a toggle. `AboutInfoToggle` is only used inside `Overview`.
    """

    def __init__(self, module_wrapper, module_outlet):
        super().__init__()
        self._module_wrapper = module_wrapper
        self._module_outlet = module_outlet
        self.modal_outlet = module_outlet.modal_outlet

        module_string_for_html = (
            str(module_wrapper.__original_module__)
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        self.about_info = [
            self._grey_html(f"bamboolib version {__version__}"),
            self._grey_html(f"{module_string_for_html}"),
        ]

        def toggle_hide_or_show(button):
            global SHOW_ABOUT_INFO
            SHOW_ABOUT_INFO = not SHOW_ABOUT_INFO
            self.update()

        self.hide_or_show_about_info = Button(
            description="About",
            on_click=toggle_hide_or_show,
        )
        self.about_setting_outlet = widgets.VBox()
        self.update()

        self.children = [self.hide_or_show_about_info, self.about_setting_outlet]

    def update(self):
        self.hide_or_show_about_info.icon = (
            "chevron-up" if SHOW_ABOUT_INFO else "chevron-down"
        )
        content = self.about_info if SHOW_ABOUT_INFO else []
        self.about_setting_outlet.children = content

    def _grey_html(self, text):
        return widgets.HTML(f"<p style='color:#808080'>{text}</p>")


class Overview(Viewable):
    """
    This widget shows an overview of all actions that are accessible from the module view.
    In particular, it shows all LoaderPlugins
    """

    def __init__(self, module_wrapper, module_outlet, **kwargs):
        super().__init__(**kwargs)
        self._module_wrapper = module_wrapper
        self._module_outlet = module_outlet
        self.modal_outlet = module_outlet.modal_outlet
        self.about_info_toggle = AboutInfoToggle(module_wrapper, module_outlet)

    def render(self):
        self.set_content(
            widgets.VBox(
                [self._create_plugin_button(plugin) for plugin in self._get_plugins()]
            ),
            widgets.HTML("<hr>"),
            self.about_info_toggle,
        )

    def _create_plugin_button(self, plugin):
        # Attention: this code had to be moved to this separate function
        # (instead of using it inline in the list comprehension above)
        # The reason was that only in this way does the on_click lambda capture the correct `plugin` object
        return Button(
            description=plugin["name"],
            style=plugin["style"],
            on_click=lambda _: self._open_plugin(plugin["loader"]),
        )

    def _open_plugin(self, loader):
        loader(
            symbols=self._module_wrapper.__user_symbols__,
            parent_outlet=self._module_outlet,
        ).render_in(self.modal_outlet)

    def _get_plugins(self):
        base_loader_plugins = []
        if auth.is_databricks():
            base_loader_plugins += [
                {
                    "name": "Databricks: Read CSV file from DBFS",
                    "loader": ReadCSVFromDBFS,
                    "style": "primary",
                },
                {
                    "name": "Databricks: Read Parquet file from DBFS",
                    "loader": ReadParquetFromDBFS,
                    "style": "secondary",
                }
            ]
        else:
            base_loader_plugins += [
                {
                    "name": "Read CSV file",
                    "loader": ReadCSV,
                    "style": "primary",
                },
                {"name": "Read Excel file", "loader": ReadExcel, "style": "secondary"},
            ]

        return base_loader_plugins + self._get_loader_plugins()

    def _get_loader_plugins(self):
        plugin_items = []
        for plugin in LoaderPlugin.get_plugins():
            try:
                plugin_items.append(
                    {"name": plugin.name, "loader": plugin, "style": "secondary"}
                )
            except:
                pass
        return plugin_items


# To be refactored to a LoaderPlugin. See also ReadExcel.
class ReadCSV(TabViewable):
    """
    A Loader to read a CSV file
    """

    def __init__(self, symbols, parent_outlet, **kwargs):
        super().__init__(**kwargs)
        self.csv_loader = CSVLoader(CSVOptions, on_open_file=self.open_csv)
        self.symbols = symbols
        self._parent_outlet = parent_outlet

        self.df_manager = None

    def render(self):
        self.set_title("Read CSV")
        self.set_content(self.csv_loader)

    @show_loader_and_maybe_error_modal
    def open_csv(self, df_name=None, code=None):
        if_new_df_name_is_invalid_raise_error(df_name)
        if self.df_manager is None:
            # this is the first execution of the ReadCSV
            initial_user_code = None  # we do not know the initial_user_code
        else:
            # this is a subsequent execution of ReadCSV
            # we restore initial_user_code to overwrite potential code changes in the cell from the old DfManager
            initial_user_code = self.df_manager.get_initial_user_code()

        code = f"{df_name} = {code}\n"
        df = exec_code(code, symbols=self.symbols, result_name=df_name)

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


# To be refactored to a LoaderPlugin. See also ReadExcel.
class ReadCSVFromDBFS(TabViewable):
    """
    A Loader to read a CSV file from DBFS
    """

    def __init__(self, symbols, parent_outlet, **kwargs):
        super().__init__(**kwargs)
        self.csv_loader = CSVFromDBFSLoader(CSVOptions, on_open_file=self.open_csv)
        self.symbols = symbols
        self._parent_outlet = parent_outlet

        self.df_manager = None

    def render(self):
        self.set_title("Read CSV from DBFS")
        self.set_content(self.csv_loader)

    @show_loader_and_maybe_error_modal
    def open_csv(self, df_name=None, code=None):
        if_new_df_name_is_invalid_raise_error(df_name)
        if self.df_manager is None:
            # this is the first execution of the ReadCSV
            initial_user_code = None  # we do not know the initial_user_code
        else:
            # this is a subsequent execution of ReadCSV
            # we restore initial_user_code to overwrite potential code changes in the cell from the old DfManager
            initial_user_code = self.df_manager.get_initial_user_code()

        code = f"{df_name} = {code}\n"
        df = exec_code(code, symbols=self.symbols, result_name=df_name)

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

# To be refactored to a LoaderPlugin. See also ReadExcel.
class ReadParquetFromDBFS(TabViewable):
    """
    A Loader to read a Parquet file from DBFS
    """

    def __init__(self, symbols, parent_outlet, **kwargs):
        super().__init__(**kwargs)
        self.parquet_loader = ParquetFromDBFSLoader(ParquetOptions, on_open_file=self.open_parquet)
        self.symbols = symbols
        self._parent_outlet = parent_outlet

        self.df_manager = None

    def render(self):
        self.set_title("Read Parquet from DBFS")
        self.set_content(self.parquet_loader)

    @show_loader_and_maybe_error_modal
    def open_parquet(self, df_name=None, code=None):
        if_new_df_name_is_invalid_raise_error(df_name)
        if self.df_manager is None:
            # this is the first execution of the ReadParquetFromDBFS
            initial_user_code = None  # we do not know the initial_user_code
        else:
            # this is a subsequent execution of ReadParquetFromDBFS
            # we restore initial_user_code to overwrite potential code changes in the cell from the old DfManager
            initial_user_code = self.df_manager.get_initial_user_code()

        code = f"{df_name} = {code}\n"
        df = exec_code(code, symbols=self.symbols, result_name=df_name)

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

# To be refactored to a LoaderPlugin. See also ReadCSV.
class ReadExcel(TabViewable):
    """
    A Loader to read an Excel file
    """

    def __init__(self, symbols, parent_outlet, **kwargs):
        super().__init__(**kwargs)
        self.excel_loader = ExcelLoader(ExcelOptions, on_open_file=self.open_excel)
        self.symbols = symbols
        self._parent_outlet = parent_outlet

        self.df_manager = None

    def render(self):
        self.set_title("Read Excel")
        self.set_content(self.excel_loader)

    @show_loader_and_maybe_error_modal
    def open_excel(self, df_name=None, code=None):
        if_new_df_name_is_invalid_raise_error(df_name)
        if self.df_manager is None:
            # this is the first execution of the ReadExcel
            initial_user_code = None  # we do not know the initial_user_code
        else:
            # this is a subsequent execution of ReadExcel
            # we restore initial_user_code to overwrite potential code changes in the cell from the old DfManager
            initial_user_code = self.df_manager.get_initial_user_code()

        code = f"{df_name} = {code}\n"
        df = exec_code(code, symbols=self.symbols, result_name=df_name)

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
