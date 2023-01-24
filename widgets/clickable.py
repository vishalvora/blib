# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode
from bamboolib import __widgets_version__


@widgets.register()
class ClickableWidget(widgets.Box):
    """
    A wrapper widget that triggers its on_click callback whenever the user clicks anywhere within the wrapped scope.
    """

    _view_name = Unicode("BamClickableView").tag(sync=True)
    _model_name = Unicode("BamClickableModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_class("bamboolib-clickable")

        self._click_callbacks = widgets.CallbackDispatcher()
        self.on_msg(self._handle_message_from_js)

    def _handle_message_from_js(self, widget, content, buffers=None):
        type_ = content.get("type", "")
        if type_ == "on_click":
            self._click_callbacks(self)

    def on_click(self, callback, remove=False):
        """
        Add or remove an on_click callback.

        :param callback: a function that expects the widget itself as single argument
        :param remove: boolean

        Example:
        >>> clickable.on_click(lambda widget: print("The user clicked me!"))
        """
        self._click_callbacks.register_callback(callback, remove=remove)
