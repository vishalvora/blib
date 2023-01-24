# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode
from bamboolib import __widgets_version__


@widgets.register()
class BaseButton(widgets.Button):
    """
    The bamboolib BaseButton that can trigger an on_click event and that can be passed css_classes.
    """

    _view_name = Unicode("ButtonView").tag(sync=True)
    _model_name = Unicode("ButtonModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    def __init__(self, on_click=None, css_classes=[], **kwargs):
        super().__init__(**kwargs)

        for css_class in css_classes:
            self.add_class(css_class)

        if on_click is not None:
            self.on_click(on_click)


class Button(BaseButton):
    """
    Button widget.

    :param description: str. Description text displayed inside the button
    :param icon: str, optional. A valid Font Awesome icon name. See here for a full list: https://fontawesome.com/v4.7/icons/
    :param style: str or None, optional. The styling of the button. One of ["primary", "secondary", None], default: "secondary".

    :raises ValueError: if style is not a valid style

    Examples:
    >>> greetings_button = Button(description="Hello, World!", style="primary")
    >>> greetings_button

    Call a function when a user clicks the button:

    >>> greetings_button.on_click(lambda button: print("Stop the rage clicking!"))
    >>> greetings_button
    """

    def __init__(
        self, description: str = "", icon: str = "", style: str = "secondary", **kwargs
    ):
        super().__init__(description=description, icon=icon, **kwargs)

        if (icon != "") and (description == ""):
            self.add_class("bamboolib-icon-button")

        VALID_STYLES = ["primary", "secondary"]

        if style is None:
            pass
        elif style == "primary":
            self.add_class("bamboolib-button-primary")
        elif style == "secondary":
            self.add_class("bamboolib-button-secondary")
        else:
            raise ValueError(f"The 'style' argument has to be one of {VALID_STYLES}")
