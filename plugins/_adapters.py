# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

from bamboolib.widgets import (
    Button as _Button,
    CloseButton as _CloseButton,
    Multiselect as _Multiselect,
    Singleselect as _Singleselect,
    Text as _Text,
)


class Button(_Button):
    """
    Button widget.

    :param description: str. Description text displayed inside the button
    :param icon: str, optional. A valid Font Awesome icon name. See here for a full list: https://fontawesome.com/v4.7/icons/
    :param style: str or None, optional. The styling of the button. One of {"primary", "secondary", None}, default: "secondary".

    :raises ValueError: if style is not a valid style

    Examples:
    >>> greetings_button = Button(description="Hello, World!", style="primary")
    >>> greetings_button

    Call a function when a user clicks the button:

    >>> greetings_button.on_click(lambda button: print("Stop the rage clicking!"))
    >>> greetings_button
    """

    # Attention: currently, the same docstring as _Button.

    def __init__(self, style: str = "secondary", **kwargs):
        super().__init__(style=style, **kwargs)


class CloseButton(_CloseButton):
    """
    Close button widget.

    Examples:
    >>> button = CloseButton()
    >>> button

    Call a function when a user clicks the button:

    >>> button.on_click(lambda button: print("Stop the rage clicking!"))
    >>> button
    """

    pass


class Multiselect(_Multiselect):
    """
    A widget to select none, one, or multiple values.

    :param options: either list of [str, (label, value) tuples OR {"label": ..., "value": ...} dictionaries]. The value can be any hashable object. Options that can be selected
    :param value: list of value objects. Values need to be hashable. The values that are preselected. Values that are not in `options` will be ignored.
    :param placeholder: str, text that is shown when no element is selected
    :param max_items: int or None. Maximum number of items. If 1, the layout changes to Singleselect.
    :param enabled: bool, if the user can select something
    :param focus_after_init: bool, if the widget should get focus after rendering
    :param select_on_tab: bool, if pressing tab selects an item
    :param width: str or None, optional, one of ["xs", "sm", "md", "lg", "xl"], default: None. If None the widget will take 100% of its parent's width.
    :param on_change: callback that is called when the selected values change
    :param css_classes: list of str, names of CSS classes that should be added

    The widget exposes the following attributes that can be read and set:
    `value`, `options`, `max_items`.

    The `label` attribute can only be read. If you want to set the label, please set the value that has the label that you want to set.

    Examples:
    >>> letter_input = Multiselect(options=["A", "B", "C"], placeholder="Choose a letter ...")

    The most flexible way to set (a) default value(s) is this:

    >>> option_list = [("Apple", "a"), ("Banana", "b"), ("Peach", "p")]
    >>> fruit_input = Multiselect(options=option_list, value=["a", "b"])
    >>> fruit_input.value  # ["a", "b"]

    You can also set values programmatically like this:

    >>> fruit_input.value = ["b", "p"]
    """

    def __init__(
        self, options=[], value=[], placeholder="", max_items=None, width=None, **kwargs
    ):
        super().__init__(
            options=options,
            value=value,
            placeholder=placeholder,
            max_items=max_items,
            width=width,
            **kwargs,
        )


class Singleselect(_Singleselect):
    """
    Single-select dropdown

    :param options: either list of [str, (label, value) tuples OR {"label": ..., "value": ...} dictionaries]. The value can be any hashable object. Options that can be selected
    :param value: hashable object - value that is preselected. If the value is not in `options` it will be ignored.
    :param placeholder: str, text that is shown when no element is selected
    :param set_soft_value: bool, if the widget should make sure that there is always a value selected
    :param enabled: bool, if the user can select something
    :param focus_after_init: bool, if the widget should get focus after rendering
    :param width: str or None, optional, one of ["xs", "sm", "md", "lg", "xl"], default: None. If None the widget will take 100% of its parent's width.
    :param on_change: callback that is called when the selected values change
    :param css_classes: list of str, names of CSS classes that should be added

    Example
    -------
    >>> letter_input = Singleselect(options=["A", "B", "C"], placeholder="Choose a letter ...")

    The most flexible way to set a default value is this:

    >>> option_list = [("Apple", "a"), ("Banana", "b")]
    >>> fruit_input = Singleselect(options=option_list, value="a")
    >>> fruit_input.value  # "a"

    You can also set the value programmatically like this:
    >>> fruit_input.value = "b"
    """

    def __init__(self, options=[], value=None, placeholder="", width=None, **kwargs):
        super().__init__(
            options=options, value=value, placeholder=placeholder, width=width, **kwargs
        )


class Text(_Text):
    """
    Text widget.

    This widget has an `on_submit` method that allows you to listen for the user hitting enter
    while focusing the widget (see the example below).

    :param description: str or None, optional, default: "". Description displayed above the Text widgets. If None then no description is displayed.
    :param placeholder: str or None, optional, default: None. Placeholder displayed inside the text widget.
    :param value: str, optional, default: "". Value of the text widget that can be retrieved via `Text.value`.
    :param width: str, optional, one of ["xxs", "xs", "sm", "md", "lg", "xl"]. Width of the text widget.

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
        self, description="", value="", placeholder=None, width=None, **kwargs
    ):
        super().__init__(
            description=description,
            placeholder=placeholder,
            value=value,
            width=width,
            **kwargs,
        )
