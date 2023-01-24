# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode
from bamboolib import __widgets_version__


@widgets.register()
class TracebackOutput(widgets.DOMWidget):
    """
    The widget displays error tracebacks and supporting information to the user
    """

    _view_name = Unicode("BamTracebackOutputView").tag(sync=True)
    _model_name = Unicode("BamTracebackOutputModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    content = Unicode("").tag(sync=True)
