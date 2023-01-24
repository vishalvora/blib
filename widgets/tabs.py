# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode, Bool
from bamboolib import __widgets_version__


@widgets.register()
class Tab(widgets.Box):
    """
    A tab (header) widget.

    :param title: str for the title
    :param closable: boolean if the tab shows a close button that can be clicked

    You can register callbacks for the on_click and on_close events.
    """

    _view_name = Unicode("BamTabView").tag(sync=True)
    _model_name = Unicode("BamTabModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)
    title = Unicode("").tag(sync=True)
    closable = Bool(True).tag(sync=True)

    def __init__(self, title="", closable=True, **kwargs):
        super().__init__(**kwargs)
        self.add_class("bamboolib-tab")

        self.title = title
        self.closable = closable

        self._click_callbacks = widgets.CallbackDispatcher()
        self._close_callbacks = widgets.CallbackDispatcher()
        self.on_msg(self._handle_message_from_js)

    def _handle_message_from_js(self, widget, content, buffers=None):
        type_ = content.get("type", "")
        if type_ == "on_click":
            self._click_callbacks(self)
        if type_ == "on_close":
            self._close_callbacks(self)

    def on_click(self, callback, remove=False):
        """
        Add or remove an on_click callback which is triggered when the user clicks the tab but not the close button.

        :param callback: a function that expects the widget itself as single argument
        :param remove: boolean

        Example:
        >>> tab.on_click(lambda widget: print("The user clicked me!"))
        """
        self._click_callbacks.register_callback(callback, remove=remove)

    def on_close(self, callback, remove=False):
        """
        Add or remove an on_close callback which is triggered when the user clicks the close button.

        :param callback: a function that expects the widget itself as single argument
        :param remove: boolean

        Example:
        >>> tab.on_close(lambda widget: print("The user closed me!"))
        """
        self._close_callbacks.register_callback(callback, remove=remove)
