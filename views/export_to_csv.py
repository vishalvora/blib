# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.helper import (
    Viewable,
    show_loader_and_maybe_error_modal,
    log_action,
    notification,
)

from bamboolib._path import DBFS_BASE_PATH
from bamboolib.widgets import Text, Button


class ExportToCSVInLocalFilesystemView(Viewable):
    """
    A view to export the current Dataframe to CSV on a user's local file system
    """

    def render(self):
        header = widgets.HTML("Export to CSV file in local directory")

        self.file_name_input = Text(value="my_data.csv", execute=self)

        self.warning = widgets.VBox()

        self.execute_button = Button(
            description="Execute",
            style="primary",
            on_click=lambda button: self.execute(),
        )

        self.set_title("Export to CSV")
        self.set_content(
            header,
            self.file_name_input,
            self.warning,
            widgets.HTML("<br>"),
            self.execute_button,
        )

    @show_loader_and_maybe_error_modal
    def execute(self):
        if self.file_name_input.value == "":
            self.warning.children = [
                notification("The file/path name cannot be empty", type="error")
            ]
            return False
        else:
            self._export_to_csv()
            return True

    def _export_to_csv(self):
        df = self.df_manager.get_current_df()
        df.to_csv(self.file_name_input.value, index=False)


class ExportToCSVInDBFSView(Viewable):
    """
    A view to export the current Dataframe to CSV on DBFS
    """

    def render(self):
        header = widgets.HTML("Export to CSV file in DBFS")

        self.file_name_input = Text(value="my_data.csv", execute=self)

        self.warning = widgets.VBox()

        self.execute_button = Button(
            description="Execute",
            style="primary",
            on_click=lambda button: self.execute(),
        )

        self.set_title("Export to CSV")
        self.set_content(
            header,
            widgets.HBox(
                [
                    widgets.HTML("/dbfs/FileStore/"),
                    self.file_name_input,
                ]
            ),
            self.warning,
            widgets.HTML("<br>"),
            self.execute_button,
        )

    @show_loader_and_maybe_error_modal
    def execute(self):
        if self.file_name_input.value == "":
            self.warning.children = [
                notification("The file/path name cannot be empty", type="error")
            ]
            return False
        else:
            self._export_to_csv()
            return True

    def _export_to_csv(self):
        df = self.df_manager.get_current_df()
        df.to_csv(DBFS_BASE_PATH / self.file_name_input.value, index=False)
