# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode
from bamboolib.widgets.button import BaseButton
from bamboolib import __widgets_version__


@widgets.register()
class SVGButton(BaseButton):
    """
    A button that contains a SVG.

    :param svg_size: str of the size of the SVG in pixels e.g. "12"
    :param view_box: str for viewBox of the SVG e.g. "-255 340 100 100"
    :param path: str for the path of the SVG

    SVGButton is a BaseButton and inherits all its arguments, attributes, and methods.
    """

    _view_name = Unicode("SVGButtonView").tag(sync=True)
    _model_name = Unicode("SVGButtonModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    svg_size = Unicode("12", help="Size of the SVG in pixels. e.g. '12'").tag(sync=True)
    view_box = Unicode(help="").tag(sync=True)
    path = Unicode(help="").tag(sync=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_class("bamboolib-svg-button")


class CloseButton(SVGButton):
    """
    Close button widget.
    """

    def __init__(self, **kwargs):
        super().__init__(
            svg_size="12",
            path="M-160.4 434.2l-37.2-37.2 37.1-37.1-7-7-37.1 37.1-37.1-37.1-7 7 37.1 37.1-37.2 37.2 7.1 7 37.1-37.2 37.2 37.2",
            view_box="-255 340 100 100",
            **kwargs
        )


class BackButton(SVGButton):
    """
    Back button widget.
    """

    def __init__(self, **kwargs):
        super().__init__(
            svg_size="20",
            path="M30.83 32.67l-9.17-9.17 9.17-9.17L28 11.5l-12 12 12 12z",
            view_box="0 -8 48 48",
            **kwargs
        )
