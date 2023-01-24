# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.transformations.base_components import SelectorGroupMixin, SelectorMixin


class ListItem(SelectorMixin, widgets.HBox):
    """
    Base class for list items that are used within ListInput
    """

    def __init__(
        self,
        focus_after_init=True,
        item_class=object,
        item_kwargs={},
        item_is_valid=lambda value: True,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.add_class("bamboolib-overflow-visible")

        self.item_is_valid = item_is_valid

        # Attention: make sure that there are no duplicate kwargs
        valid_kwargs = {**item_kwargs, "focus_after_init": focus_after_init}
        self.item_input = item_class(**valid_kwargs)

        self.render()

    def render(self):
        self.children = [self.item_input, self.delete_selector_button]

    def is_valid(self):
        return self.item_is_valid(self.item_input.value)

    @property
    def value(self):
        return self.item_input.value


class ListInput(SelectorGroupMixin, widgets.VBox):
    """
    An input widget that allows the user to create a list of values.

    :param header: a widget that is shown as the header e.g. ipywidgets.HTML
    :param add_button_text: str that is shown as the description of the add button
    :param focus_after_init: bool, if the widget should acquire focus after rendering
    :param item_class: widget class for the items
    :param item_is_valid: callable that checks whether an item input is valid
    :param item_kwargs: kwargs for initializing new `item_class` instances

    Example:
    >>> ListInput(
    >>>     header=widgets.HTML("Create color theme - press ENTER when done"),
    >>>     item_class=Text,
    >>>     item_is_valid=lambda value: value != "",
    >>>     item_kwargs=dict(
    >>>         value="",
    >>>         placeholder="Color e.g. #228b22 or green",
    >>>         width="lg",
    >>>         on_submit=lambda _: print("add item"),
    >>>     ),
    >>> )
    """

    def __init__(
        self,
        header=widgets.VBox(),
        add_button_text="add",
        focus_after_init=False,
        **kwargs,
    ):
        super().__init__()
        self.add_class("bamboolib-overflow-visible")

        self.kwargs = kwargs
        self.focus_after_init = focus_after_init

        self.init_selector_group(add_button_text=add_button_text)

        self.children = [header, self.selector_group, self.add_selector_button]

    def create_selector(self, focus_after_init=True, show_delete_button=None, **kwargs):
        # Attention: make sure that there are no duplicate kwargs
        valid_kwargs = {
            **self.kwargs,
            **kwargs,
            "focus_after_init": focus_after_init,
            "selector_group": self,
            "show_delete_button": show_delete_button,
        }
        return ListItem(**valid_kwargs)

    def get_initial_selector(self):
        return self.create_selector(
            focus_after_init=self.focus_after_init, show_delete_button=False
        )

    @property
    def value(self):
        return [item.value for item in self.get_selectors() if item.is_valid()]
