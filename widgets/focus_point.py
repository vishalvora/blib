# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode
from bamboolib import __widgets_version__


@widgets.register()
class FocusPoint(widgets.Box):
    """
    The FocusPoint is a widget that receives focus when being displayed the first time.
    Also, it has a method `focus` to request focus.
    This solves the problem of steering the user focus within the HTML page.

    E.g. this can be helpful to direct focus before an element that should be accessible
    via hitting the TAB key.
    """

    _view_name = Unicode("BamFocusPointView").tag(sync=True)
    _model_name = Unicode("BamFocusPointModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_class("bamboolib-focuspoint")

    def focus(self):
        """
        Request focus to the FocusPoint. Only works when FocusPoint is already displayed.
        """
        self.send({})
