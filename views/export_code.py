# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.helper import Viewable, log_action
from bamboolib.widgets import CopyButton


class ExportCodeView(Viewable):
    """
    A view to export the current transformations code
    """

    def render(self):
        self.code = self.df_manager.get_setup_and_transformations_code()

        self.copy_button = CopyButton(
            copy_string=self.code,
            style="primary",
            on_click=lambda _: log_action("export", self, "click copy code"),
        )

        self.textarea = widgets.Textarea(value=self.code).add_class(
            "bamboolib-width-auto"
        )
        self.textarea.add_class("bamboolib-code-export")

        self.set_title("Export code")

        if self.code == "":
            self.set_content(
                widgets.HTML(
                    "Currently, there is no code to export. Please add some transformations"
                )
            )
        else:
            self.set_content(self.copy_button, self.textarea)
