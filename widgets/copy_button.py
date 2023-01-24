# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode
import time
from bamboolib import __widgets_version__
from bamboolib.widgets.button import Button


@widgets.register()
class BaseCopyButton(Button):
    """
    A special button that copies the `copy_string` to the clipboard of the user via the help of the browser.
    It also has all the behavior of a bamboolib.widgets.Button.
    The BaseCopyButton is unopinionated. Usually, you might want to use the CopyButton.

    Example:
    >>> BaseCopyButton(
            copy_string="to be copied",
            description="my description",
            style="primary",
            on_click=lambda _: print("I was clicked"),
        )
    """

    _view_name = Unicode("BamCopyButtonView").tag(sync=True)
    _model_name = Unicode("BamCopyButtonModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    copy_string = Unicode("").tag(sync=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_class("bamboolib-copy-button")


class CopyButton(BaseCopyButton):
    """
    A special, opinionated button that copies the `copy_string` to the clipboard of the user via the help of the browser.
    It also has all the behavior of a bamboolib.widgets.Button.
    The CopyButton is opinionated because it already has a default description and changes its description after a click in order to give more feedback to the user. If you only want the base functionality of copying the string to clipboard, please use BaseCopyButton.

    Example:
    >>> CopyButton(
            copy_string="to be copied",
            style="primary",
            on_click=lambda _: print("I was clicked"),
        )
    """

    def __init__(self, description="Copy code", icon="clipboard", **kwargs):
        super().__init__(description=description, icon=icon, **kwargs)
        self.on_click(lambda button: self._on_click())

    def _on_click(self):
        old_description = self.description
        self.description = "Copied!"
        time.sleep(1)
        self.description = old_description
