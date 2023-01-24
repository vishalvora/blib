# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import pandas as pd
import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD

from bamboolib.widgets import Multiselect


class OneHotEncoderTransformation(Transformation):
    """Create a column for each unique value indicating its presence or absence."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.column = None

        self.columns_selector = Multiselect(
            options=list(self.get_df().columns),
            placeholder="Choose column(s)",
            focus_after_init=True,
        )

        self.drop_first_dummy_checkbox = widgets.Checkbox(
            value=False, description="Remove the first dummy (k-1 instead of k dummies)"
        )
        self.drop_first_dummy_checkbox.add_class("bamboolib-checkbox")

        self.create_na_dummy_checkbox = widgets.Checkbox(
            value=False, description="Create dummy for missing values"
        )
        self.create_na_dummy_checkbox.add_class("bamboolib-checkbox")

    def render(self):
        self.set_title("One Hot Encode column(s)")
        self.set_content(
            self.columns_selector,
            widgets.HTML("<br>"),
            self.drop_first_dummy_checkbox,
            self.create_na_dummy_checkbox,
        )

    def get_description(self):
        columns = self.columns_selector.value
        full_column_string = ", ".join(columns)
        return f"<b>OneHotEncode column(s)</b> {full_column_string}"

    def get_code(self):
        drop_first = self.drop_first_dummy_checkbox.value
        dummy_na = self.create_na_dummy_checkbox.value
        return f"{DF_OLD} = pd.get_dummies({DF_OLD}, columns={self.columns_selector.value}, drop_first={drop_first}, dummy_na={dummy_na})"
