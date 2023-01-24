# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode, Bool
from bamboolib import __widgets_version__


@widgets.register()
class TextBaseWidget(widgets.DOMWidget):
    """
    A basic text widget.

    In comparison to ipywidgets.Text:
    - there is no description
    - the focus can be influenced with `focus_after_init`

    :param value: str, value of the text field
    :param placeholder: str, placeholder text in the input
    :param focus_after_init: bool, if the widget should acquire focus after rendering
    """

    _view_name = Unicode("BamTextView").tag(sync=True)
    _model_name = Unicode("BamTextModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)
    value = Unicode("").tag(sync=True)
    placeholder = Unicode("").tag(sync=True)

    focus_after_init = Bool(False).tag(sync=True)

    # _did_focus_after_init is true after the first init
    # This information is important so that the JS does not focus again at a later render
    # Scenario: When widgets are rendered again e.g. during editing an existing transformation,
    # then the widget should not be focused again.
    _did_focus_after_init = Bool(False).tag(sync=True)

    def __init__(self, value="", placeholder="", focus_after_init=False, **kwargs):
        super().__init__(**kwargs)
        self._submission_callbacks = widgets.CallbackDispatcher()
        self.on_msg(self._handle_message_from_js)

        self.value = value
        self.placeholder = placeholder
        self.focus_after_init = focus_after_init
        self._did_focus_after_init = False

        self.add_class("jupyter-widgets")
        self.add_class("widget-inline-hbox")
        self.add_class("widget-text")

    def _handle_message_from_js(self, widget, content, buffers=None):
        type_ = content.get("type", "")
        if type_ == "on_press_enter":
            self._submission_callbacks(self)

    def on_submit(self, callback, remove=False):
        """
        Add or remove an on_submit callback that is triggered when the user presses enter.

        :param callback: a function that expects the widget itself as single argument
        :param remove: boolean

        Example:
        >>> widget.on_submit(lambda widget: print("The user pressed enter!"))
        """
        self._submission_callbacks.register_callback(callback, remove=remove)


class Text(widgets.VBox):
    """
    Text widget.

    This widget has an `on_submit` method that allows you to listen for the user hitting enter
    while focusing the widget (see the example below).

    :param description: str or None, optional, default: "". Description displayed above the Text widgets. If None then no description is displayed.
    :param placeholder: str or None, optional, default: None. Placeholder displayed inside the text widget.
    :param value: str, optional, default: "". Value of the text widget that can be retrieved via `Text.value`.
    :param width: str, optional, one of ["xxs", "xs", "sm", "md", "lg", "xl"]. Width of the text widget.
    :param on_change: callback that is called when the `value` changes
    :param on_submit: callback that is called when the user hits enter
    :param execute: object that has an execute method. Method will be called when user submits
    :param css_classes: list of str with names of CSS classes

    Examples:

    >>> name_input = Text(description="Name", value="", placeholder="Add name ...", width="md")

    Get widget's value:
    >>> name_input.value

    You can also set the value of the text widget via the `value` attribute:
    >>> name_input.value = "John Doe"

    Call a function when a user hits enter inside the text widget.
    >>> name_input.on_submit(lambda name_input: print("Thank you for hitting enter so smoothly ..."))
    """

    def __init__(
        self,
        description=None,
        placeholder=None,
        execute=None,
        on_change=None,
        on_submit=None,
        width=None,
        css_classes=[],
        **kwargs,
    ):
        super().__init__()
        self._on_change_callbacks = widgets.CallbackDispatcher()
        if on_change is not None:
            self.on_change(on_change)

        if placeholder is None:
            placeholder = "" if description is None else description

        self._input = TextBaseWidget(placeholder=placeholder, **kwargs)
        self._input.observe(lambda _: self._on_change_callbacks(self), names="value")

        self._input.add_class("bamboolib-input")

        if width is not None:
            self._input.add_class(f"bamboolib-width-{width}")

        if on_submit is not None:
            self._input.on_submit(on_submit)

        self._maybe_add_execute_on_submit_callback(execute)

        output = [self._input]

        if description is not None:
            self._description = widgets.HTML(description)
            self._description.add_class("bamboolib-text-label")
            output = [self._description] + output

        for css_class in css_classes:
            self._input.add_class(css_class)

        self.children = output

    def _maybe_add_execute_on_submit_callback(self, execute_target):
        if execute_target is not None:
            if hasattr(execute_target, "execute"):
                self._input.on_submit(lambda _: execute_target.execute())

    @property
    def on_submit(self):
        """
        Add or remove an on_submit callback that is triggered when the user presses enter.

        :param callback: a function that expects the widget itself as single argument
        :param remove: boolean

        Example:
        >>> widget.on_submit(lambda widget: print("The user pressed enter!"))
        """
        return self._input.on_submit

    def on_change(self, callback, remove=False):
        """
        Add or remove an on_change callback that is triggered when the `value` changes.

        :param callback: a function that expects the widget itself as single argument
        :param remove: boolean

        Example:
        >>> widget.on_change(lambda widget: print("The value changed!"))
        """
        self._on_change_callbacks.register_callback(callback, remove=remove)

    @property
    def value(self):
        return self._input.value

    @value.setter
    def value(self, value):
        self._input.value = value

    @property
    def description(self):
        return self._description.value

    @description.setter
    def description(self, value):
        self._description.value = value
