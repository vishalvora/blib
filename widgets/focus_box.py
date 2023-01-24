# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode
from bamboolib import __widgets_version__


@widgets.register()
class FocusBox(widgets.Box):
    """
    The FocusBox solves the problem that the user is typing within our UI
    and some of the keyboard commands do suddenly interact with Jupyter
    (because the events were propagated).
    Thus, the FocusBox stops the propagation of keyboard events when the focus
    lies on elements within its scope (It is a box view, similar to an VBox.).
    It is possible to change the focus e.g. via "tabbing" out of its scope.
    """

    _view_name = Unicode("BamFocusBoxView").tag(sync=True)
    _model_name = Unicode("BamFocusBoxModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_class("bamboolib-focusbox")
