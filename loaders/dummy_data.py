# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.plugins import LoaderPlugin, DF_NEW, Singleselect
from bamboolib.helper import AuthorizedPlugin


class DummyData(AuthorizedPlugin, LoaderPlugin):
    """
    Allows the user to select bamboolib's exposed dummy datasets, e.g. titanic and sales dataset.
    """

    name = "Load dummy data"
    new_df_name_placeholder = "df"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        data_options = [
            {
                "label": "Titanic passengers dataset",
                "value": "pd.read_csv(bam.titanic_csv)",
                "description": "Each row is a passenger on the Titanic - often used for classifications",
            },
            {
                "label": "Titanic ports dataset",
                "value": """pd.DataFrame(data={"Embarked": ["S", "C", "Q"], "PortName": ["Southampton", "Cherbourg", "Queenstown"]})""",
                "description": "Each row is a port of the Titanic's voyage - often used to join to the Titanic passengers dataset",
            },
            {
                "label": "Sales dataset",
                "value": "pd.read_csv(bam.sales_csv)",
                "description": "Timeseries dataset - each row is a monthly sales figure for various products",
            },
        ]
        self.dataset = Singleselect(
            options=data_options, value=data_options[0]["value"], width="xl"
        )

    def render(self):
        self.set_title("Load dummy data")
        self.set_content(
            widgets.HTML("Load a dummy data set for testing bamboolib"),
            self.dataset,
            self.new_df_name_group,
            self.execute_button,
        )

    def get_code(self):
        return f"""
                    {DF_NEW} = {self.dataset.value}
                """
