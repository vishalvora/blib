# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

"""
This file is based on the ipyfilechooser package (MIT license).
See: https://github.com/crahan/ipyfilechooser/tree/master/ipyfilechooser
"""

import os
import sys
import string
import textwrap

import ipywidgets as widgets

from bamboolib._path import DBFS_BASE_PATH
from bamboolib.helper import notification, VSpace, safe_cast
from bamboolib.widgets import Text, Button


DATA_LOADER_ROW_LIMIT = 100_000


def get_subpaths(path):
    """Walk a path and return a list of subpaths."""
    if os.path.isfile(path):
        path = os.path.dirname(path)

    paths = [path]
    path, tail = os.path.split(path)

    while tail:
        paths.append(path)
        path, tail = os.path.split(path)

    try:
        # Add Windows drive letters, but remove the current drive
        drives = get_drive_letters()
        drives.remove(paths[-1])
        paths.extend(drives)
    except ValueError:
        pass
    return paths


def has_parent(path):
    """Check if a path has a parent folder."""
    return os.path.basename(path) != ""


def get_dir_contents(path, file_formats=[], prepend_icons=False):
    """
    Get directory contents.

    :param path: path to the directory
    :param file_formats_to_show: list of str with file endings e.g. ['.csv', '.pdf']
    :param prepend_icons: bool, show icons before names of folders
    """
    files = list()
    dirs = list()

    def is_file_of_right_format(path, file_formats=file_formats):
        """
        path: the full path to a file, e.g. "~/Desktop/test.csv"
        """
        return any([path.endswith(file_format) for file_format in file_formats])

    if os.path.isdir(path):
        for item in os.listdir(path):
            if item.startswith("."):
                continue

            full_item_path = os.path.join(path, item)
            if os.path.isdir(full_item_path):
                dirs.append(item)
            elif is_file_of_right_format(full_item_path, file_formats):
                files.append(item)

        if has_parent(path):
            # the ".." value stands for "[go to parent folder]""
            # but we cannot easily change it to ".. [go to parent folder]" because
            # the value is used verbatim at another point in the code below
            dirs.insert(0, "..")

    if prepend_icons:
        return prepend_dir_icons(sorted(dirs)) + sorted(files)
    else:
        return sorted(dirs) + sorted(files)


def prepend_dir_icons(dir_list):
    """Prepend unicode folder icon to directory names."""
    return ["\U0001F4C1 " + dirname for dirname in dir_list]


def get_drive_letters():
    """Get drive letters."""
    if sys.platform == "win32":
        # Windows has drive letters
        return [
            "%s:\\" % d for d in string.ascii_uppercase if os.path.exists("%s:" % d)
        ]
    else:
        # Unix does not have drive letters
        return []


NO_FILE_SELECTED = ""


class FileChooser(widgets.VBox):
    """
    A widget for choosing a file or path

    :param on_update_selected_path: callback when the selected path changes
    :param path: path to start from
    :param file_formats_to_show: list of str with file endings e.g. ['.csv', '.pdf']
    """

    def __init__(
        self,
        on_update_selected_path=None,
        path=os.getcwd(),
        file_formats_to_show=[],
        **kwargs,
    ):
        super().__init__()
        self.on_update_selected_path = on_update_selected_path

        self._path_dropdown = widgets.Dropdown(description="").add_class(
            "bamboolib-width-auto"
        )
        self._folder_item_selector = widgets.Select(rows=10).add_class(
            "bamboolib-width-auto"
        )
        self.file_formats_to_show = file_formats_to_show

        default_path = path.rstrip(os.path.sep)  # maybe remove trailing characters
        default_filename = NO_FILE_SELECTED
        self._update_components(default_path, default_filename, first_update=True)

        self.children = [self._path_dropdown, self._folder_item_selector]

    def _update_components(self, path, filename, first_update=False):
        # Central update loop for change events because the component uses 2-way-value-syncing
        # Without this central update loop, we would run into an infinite loop
        # because updates would always trigger each other

        if first_update:
            pass  # don't remove trigger because they are not set yet
        else:
            # Disable triggers because of two-way syncing of the values
            # Otherwise, the value updates will trigger an infinite loop of events
            self._path_dropdown.unobserve(
                self._selected_path_in_dropdown, names="value"
            )
            self._folder_item_selector.unobserve(
                self._selected_folder_item, names="value"
            )

        # calculate helpers
        dircontent_real_names = get_dir_contents(
            path, file_formats=self.file_formats_to_show, prepend_icons=False
        )
        dircontent_display_names = get_dir_contents(
            path, file_formats=self.file_formats_to_show, prepend_icons=True
        )

        self._real_name_to_display_name_dict = {
            real_name: display_name
            for real_name, display_name in zip(
                dircontent_real_names, dircontent_display_names
            )
        }
        self._display_name_to_real_name_dict = dict(
            reversed(item) for item in self._real_name_to_display_name_dict.items()
        )

        self._update_path_dropdown(path)

        # update _folder_item_selector
        full_path = os.path.join(path, filename)
        self._folder_item_selector.options = dircontent_display_names
        if os.path.isfile(full_path) and (
            filename in self._folder_item_selector.options
        ):
            self._folder_item_selector.value = filename
        else:
            self._folder_item_selector.value = None

        # maybe trigger on_update_selected_path callback
        if self.on_update_selected_path:
            self.on_update_selected_path(path=full_path)

        # Reenable triggers again
        self._path_dropdown.observe(self._selected_path_in_dropdown, names="value")
        self._folder_item_selector.observe(self._selected_folder_item, names="value")

    def _update_path_dropdown(self, path):
        self._path_dropdown.options = get_subpaths(path)
        self._path_dropdown.value = path

    def _selected_path_in_dropdown(self, change):
        new_path = change["new"]
        self._update_components(new_path, NO_FILE_SELECTED)

    def _selected_folder_item(self, change):
        new_path = os.path.realpath(
            os.path.join(
                self._path_dropdown.value,
                self._display_name_to_real_name_dict[change["new"]],
            )
        )

        if os.path.isdir(new_path):  # is folder
            path = new_path
            filename = NO_FILE_SELECTED
            self._update_components(path, filename)
        elif os.path.isfile(new_path):  # is file
            path = self._path_dropdown.value
            filename = self._display_name_to_real_name_dict[change["new"]]
            self._update_components(path, filename)
        else:
            # If new_path is an invalid directory/file path
            pass


class LoaderOptionsSection(widgets.VBox):
    """
    Widget that shows the options when a user selected a file

    :param file_format_options_embeddable: widget for the specific file
    :param on_open_file: callback that is called when the user wants to open the file
    """

    def __init__(self, file_format_options_embeddable, on_open_file):
        super().__init__()
        self.on_open_file = on_open_file
        self.file_format_options_embeddable = file_format_options_embeddable
        self._render()

    def _render(self, path=None):
        if (path is None) or os.path.isdir(path):
            # path is None or a folder
            result = notification("Please click on a file to select it.")
        elif os.path.isfile(path):
            file_is_readable = os.access(path, os.R_OK)
            if file_is_readable:
                result = self.file_format_options_embeddable(path, self.on_open_file)
            else:
                result = notification(
                    "<b>Access Denied:</b> File cannot be read. Please choose a different file",
                    type="error",
                )
        else:
            result = notification(
                "<b>Error:</b> The selected path seems to be neither a folder nor a file",
                type="error",
            )
        self.children = [result]

    def path_changed(self, path):
        self._render(path=path)


class CSVOptions(widgets.VBox):
    """
    Widget that shows options and generates the code for opening a CSV file.
    """

    def __init__(self, path, on_open_file, **kwargs):
        super().__init__()
        self.path = path
        self.on_open_file = on_open_file

        df_name = "df"
        self.df_name_input = Text(
            description="Dataframe name",
            placeholder="df_new or similar",
            value=df_name,
            width="xl",
            on_submit=self._open_csv_file,
        )

        self.column_separator_input = Text(
            description="CSV value separator",
            placeholder="E.g. comma (,), semicolon (;) or others",
            value=",",
            width="xl",
            on_submit=self._open_csv_file,
        )

        self.decimal_separator_input = Text(
            description="Decimal separator",
            placeholder="E.g. point (.) in 103.54",
            value=".",
            width="xl",
            on_submit=self._open_csv_file,
        )

        self.row_limit_input = Text(
            description="Row limit: read the first N rows - leave empty for no limit",
            placeholder="E.g. 1000",
            value=str(DATA_LOADER_ROW_LIMIT),
            width="xl",
            on_submit=self._open_csv_file,
        )

        self.open_csv_button = Button(
            description="Open CSV file", style="primary", on_click=self._open_csv_file
        )

        self.children = [
            self.df_name_input,
            VSpace("xl"),
            self.column_separator_input,
            self.decimal_separator_input,
            self.row_limit_input,
            VSpace("xl"),
            self.open_csv_button,
        ]

    def _open_csv_file(self, _):
        df_name = self.df_name_input.value.strip()

        sep = self.column_separator_input.value
        decimal = self.decimal_separator_input.value
        if self.row_limit_input.value == "":
            row_limit_code = ""
        else:
            row_limit_int = safe_cast(self.row_limit_input.value, int, DATA_LOADER_ROW_LIMIT)
            if row_limit_int <= 0:
                row_limit_code = ""
            else:
                row_limit_code = f", nrows={row_limit_int}"

        code = f"pd.read_csv(r'{self.path}', sep='{sep}', decimal='{decimal}'{row_limit_code})"

        self.on_open_file(df_name=df_name, code=code)


class ParquetOptions(widgets.VBox):
    """
    Widget that shows options and generates the code for opening a Parquet file.
    """

    def __init__(self, path, on_open_file, **kwargs):
        super().__init__()
        self.path = path
        self.on_open_file = on_open_file

        df_name = "df"
        self.df_name_input = Text(
            description="Dataframe name",
            placeholder="df_new or similar",
            value=df_name,
            width="xl",
            on_submit=self._open_parquet_file,
        )

        self.row_limit_input = Text(
            description="Row limit: read the first N rows",
            placeholder="E.g. 1000",
            value=str(DATA_LOADER_ROW_LIMIT),
            width="xl",
            on_submit=self._open_parquet_file,
        )

        self.open_button = Button(
            description="Open Parquet file", style="primary", on_click=self._open_parquet_file
        )

        self.children = [
            self.df_name_input,
            VSpace("xl"),
            self.row_limit_input,
            VSpace("xl"),
            self.open_button,
        ]

    def _open_parquet_file(self, _):
        df_name = self.df_name_input.value.strip()
        row_limit_int = safe_cast(self.row_limit_input.value, int, DATA_LOADER_ROW_LIMIT)

        code = f"spark.read.parquet(r'{self.path}').limit({row_limit_int}).toPandas()"

        self.on_open_file(df_name=df_name, code=code)


class CSVLoader(widgets.HBox):
    """
    A Loader for loading a CSV file.
    """

    def __init__(self, csv_options_embeddable, on_open_file):
        super().__init__()

        self.options_section = LoaderOptionsSection(
            csv_options_embeddable, on_open_file
        )
        self.file_chooser = FileChooser(
            on_update_selected_path=self.options_section.path_changed,
            file_formats_to_show=["csv"],
        ).add_class("bamboolib-file-chooser")

        self.children = [self.file_chooser, self.options_section]


# Attention(Jan 11, 2022): Even though this class shares a lot of logic with CSVLoader,
# we don't inherit from it because pure CSV support may be dropped and we will then
# only focus on DBFS I/O
class CSVFromDBFSLoader(widgets.HBox):
    """
    A Loader for loading a CSV file from DBFS.
    """

    def __init__(self, csv_options_embeddable, on_open_file):
        super().__init__()

        self.options_section = LoaderOptionsSection(
            csv_options_embeddable, on_open_file
        )
        self.file_chooser = FileChooser(
            path=str(DBFS_BASE_PATH),
            on_update_selected_path=self.options_section.path_changed,
            file_formats_to_show=["csv"],
        ).add_class("bamboolib-file-chooser")

        self.children = [self.file_chooser, self.options_section]


class ParquetFromDBFSLoader(widgets.HBox):
    """
    A Loader for loading a Parquet file from DBFS.
    """

    def __init__(self, parquet_options_embeddable, on_open_file):
        super().__init__()

        self.options_section = LoaderOptionsSection(
            parquet_options_embeddable, on_open_file
        )
        self.file_chooser = FileChooser(
            path=str(DBFS_BASE_PATH),
            on_update_selected_path=self.options_section.path_changed,
            file_formats_to_show=["parquet"],
        ).add_class("bamboolib-file-chooser")

        self.children = [self.file_chooser, self.options_section]


class ExcelOptions(widgets.VBox):
    """
    Widget that shows options and generates the code for opening an Excel file.
    """

    def __init__(self, path, on_open_file, **kwargs):
        super().__init__()
        self.path = path
        self.on_open_file = on_open_file

        self.user_notification = notification(
            textwrap.dedent(
                """
            This feature expects the data you want to read to be stored like this:
            <ul>
                <li>the data is stored in the first Excel sheet</li>
                <li>the data table starts in cell A1</li>
                <li>the data contains column names in the first row</li>
            </ul>
            If your data is stored differently in your Excel file, please manually adjust the file.

            If you need more flexibility, please reach out to us via <a href="mailto:bamboolib-feedback+read_excel@databricks.com?subject=bamboolib - Read Excel feature">email</a>.
            """
            ),
            type="warning",
        )
        df_name = "df"
        self.df_name_input = Text(
            description="Dataframe name",
            placeholder="df_new or similar",
            value=df_name,
            width="lg",
            on_submit=self._open_excel_file,
        )

        self.open_excel_button = Button(
            description="Open Excel file",
            style="primary",
            on_click=self._open_excel_file,
        )

        self.children = [
            self.user_notification,
            self.df_name_input,
            VSpace("xl"),
            self.open_excel_button,
        ]

    def _open_excel_file(self, _):
        df_name = self.df_name_input.value.strip()

        code = f"pd.read_excel(r'{self.path}')"

        self.on_open_file(df_name=df_name, code=code)


class ExcelLoader(widgets.HBox):
    """
    A Loader for loading an Excel file.
    """

    def __init__(self, excel_options_embeddable, on_open_file):
        super().__init__()

        self.options_section = LoaderOptionsSection(
            excel_options_embeddable, on_open_file
        ).add_class("bamboolib-loader-options-section")

        self.file_chooser = FileChooser(
            on_update_selected_path=self.options_section.path_changed,
            # https://support.microsoft.com/en-us/office/file-formats-that-are-supported-in-excel-0943ff2c-6014-4e8d-aaea-b83d51d46247
            file_formats_to_show=[
                "xlsx",
                "xlsm",
                "xlsb",
                "xltx",
                "xltm",
                "xls",
                "xlt",
                "xml",
            ],
        ).add_class("bamboolib-file-chooser")

        self.children = [self.file_chooser, self.options_section]
