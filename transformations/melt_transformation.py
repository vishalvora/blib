# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import pandas as pd
import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, DF_NEW
from bamboolib._path import BAMBOOLIB_LIBRARY_ROOT_PATH

from bamboolib.widgets.selectize import Multiselect


class MeltTransformation(Transformation):
    """Reshape the dataframe from wide to long format."""

    def __init__(self, *args, column=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.columns_selector = Multiselect(
            options=list(self.get_df().columns),
            placeholder="Choose column(s)",
            value=[column],
            focus_after_init=True,
        )

        self.explanation_image = widgets.Image(
            value=open(
                BAMBOOLIB_LIBRARY_ROOT_PATH / "assets" / "img" / "wide_to_long.png",
                "rb",
            ).read(),
            format="png",
        )
        self.explanation_image.add_class("bamboolib-hint-img")

    def render(self):
        self.set_title("Unpivot / Melt wide to long format")
        self.set_content(
            self.explanation_image,
            widgets.HTML("Melts all columns except the id column(s)."),
            widgets.HTML("<h4>Select id column(s):</h4>"),
            self.columns_selector,
            self.rename_df_group,
        )

    def get_description(self):
        columns = self.columns_selector.value
        full_column_string = ", ".join(columns)
        return f"<b>Melt columns</b> based on the id columns {full_column_string}"

    def get_code(self):
        return f"{DF_NEW} = {DF_OLD}.melt(id_vars={self.columns_selector.value})"
