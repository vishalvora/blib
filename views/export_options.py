# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

import time

from bamboolib._authorization import auth
from bamboolib.helper import Viewable
from bamboolib.widgets import Button

from bamboolib.views.export_code import ExportCodeView
from bamboolib.views.export_to_variable import ExportToVariableView
from bamboolib.views.export_to_csv import (
    ExportToCSVInLocalFilesystemView,
    ExportToCSVInDBFSView,
)


class ExportOptionsView(Viewable):
    """
    A view that shows different export options
    """

    def __init__(self, full_parent_modal_outlet, side_window_outlet, **kwargs):
        super().__init__(**kwargs)
        self.full_parent_modal_outlet = full_parent_modal_outlet
        self.side_window_outlet = side_window_outlet

    def render(self, column=None):
        self.buttons = []
        self.buttons.append(self._make_button("Export code", ExportCodeView))
        self.buttons.append(
            self._make_button("Export to variable", ExportToVariableView)
        )

        if auth.is_databricks():
            self.buttons.append(
                self._make_button(
                    "Databricks: Export to CSV in DBFS", ExportToCSVInDBFSView
                )
            )
        else:
            self.buttons.append(
                self._make_button("Export to CSV", ExportToCSVInLocalFilesystemView)
            )

        self.set_title(f"Export options")
        self.set_content(widgets.VBox(self.buttons))

    def _make_button(self, description, view):
        new_outlet = self.side_window_outlet

        def render_new_view_and_maybe_close_current_view(button):
            view(df_manager=self.df_manager).add_to(new_outlet)
            if self.outlet == new_outlet:
                pass
            else:
                time.sleep(1)
                self.outlet.hide()

        return Button(
            description=description,
            on_click=render_new_view_and_maybe_close_current_view,
        )
