# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
import pandas as pd
from traitlets import Unicode
from bamboolib import __widgets_version__


@widgets.register()
class TableOutput(widgets.DOMWidget):
    """
    The widget displays code to the user
    """

    _view_name = Unicode("BamTableOutputView").tag(sync=True)
    _model_name = Unicode("BamTableOutputModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    _df_html = Unicode("").tag(sync=True)

    def __init__(self, df: pd.DataFrame, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.update_df(new=df)

    def update_df(self, new: pd.DataFrame) -> None:
        self._df = new
        self._df_html = new._repr_html_()
