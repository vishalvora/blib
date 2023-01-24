# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode
from bamboolib import __widgets_version__


@widgets.register()
class BrowserCheck(widgets.DOMWidget):
    """
    The BrowserCheck requests information from it's JS widget about the user's browser.
    The received information might be used to perform auth checks.
    """

    _view_name = Unicode("BamBrowserCheckView").tag(sync=True)
    _model_name = Unicode("BamBrowserCheckModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    def __init__(self, protected_viewable=None):
        """
        :param protected_viewable: if a viewable is given, an auth check is performed after receiving the information
        """
        super().__init__()
        self.on_msg(self._handle_message_from_js)
        self.protected_viewable = protected_viewable

    def _handle_message_from_js(self, widget, content, buffers=None):
        from bamboolib._authorization import auth

        auth.set_browser_info(content)

        if self.protected_viewable is not None:
            error = auth.get_authorization_error()
            if error is None:
                pass
            else:
                self.protected_viewable.children = [error]
