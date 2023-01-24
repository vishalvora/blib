# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.edaviz.__modules__ import plot, get_loading_widget
from bamboolib.helper import TabViewable, execute_asynchronously, log_action


class DfVisualization(TabViewable):
    """
    A view to explore the Dataframe
    """

    def render(self):
        self.df = self.df_manager.get_current_df()
        self.set_title("Exploration")

        self.set_content(
            widgets.VBox(
                [
                    get_loading_widget(),
                    widgets.HTML("<br><br><br><br><br><br><br><br><br><br><br>"),
                ]
            )
        )

        def show_plot():
            self.set_content(
                plot(
                    self.df,
                    df_manager=self.df_manager,
                    parent_tabs=self.parent_tabs,
                    preview_columns_selection=self.df_manager.get_preview_columns_selection(),
                )
            )

        execute_asynchronously(show_plot)
