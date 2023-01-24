# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.transformations.base_components import SelectorGroupMixin, SelectorMixin


class _BaseDictItem(SelectorMixin, widgets.HBox):
    """
    Base class for dict items that are used within DictInput
    """

    def __init__(
        self,
        focus_after_init=True,
        key_class=object,
        key_kwargs={},
        key_is_valid=lambda value: True,
        value_class=object,
        value_kwargs={},
        value_is_valid=lambda value: True,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.add_class("bamboolib-overflow-visible")

        self.key_is_valid = key_is_valid
        self.value_is_valid = value_is_valid

        # Attention: make sure that there are no duplicate kwargs
        valid_key_kwargs = {**key_kwargs, "focus_after_init": focus_after_init}
        self.key_item = key_class(**valid_key_kwargs)
        self.value_item = value_class(**value_kwargs)

        self.render()

    def render(self):
        raise NotImplementedError

    def is_valid(self):
        return self.key_is_valid(self.key_item.value) and self.value_is_valid(
            self.value_item.value
        )

    @property
    def key(self):
        return self.key_item.value

    @property
    def value(self):
        return self.value_item.value


class SideBySideDictItem(_BaseDictItem):
    """
    Class that renders DictItems side-by-side
    """

    def render(self):
        self.children = [self.key_item, self.value_item, self.delete_selector_button]


class IndentationDictItem(_BaseDictItem):
    """
    Class that renders DictItems with indented values
    """

    def render(self):
        main_block = widgets.VBox(
            [
                self.key_item,
                widgets.HBox(
                    [
                        widgets.HTML(
                            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                        ),
                        self.value_item,
                    ]
                ),
            ]
        )
        self.children = [main_block, self.delete_selector_button]


class DictInput(SelectorGroupMixin, widgets.VBox):
    """
    An input widget that allows the user to create a dictionary with key-value-pairs.

    :param header: a widget that is shown as the header e.g. ipywidgets.HTML
    :param item_class: a class that specifies the layout of DictItems e.g. SideBySideDictItem or IndentationDictItem
    :param add_button_text: str that is shown as the description of the add button
    :param focus_after_init: bool, if the widget should acquire focus after rendering
    :param key_class: widget class for the key elements
    :param key_is_valid: callable that checks whether a key input is valid
    :param key_kwargs: kwargs for initializing new `key_class` instances
    :param value_class: widget class for the value elements
    :param value_is_valid: callable that checks whether a value input is valid
    :param value_kwargs: kwargs for initializing new `value_class` instances

    Example:
    >>> DictInput(
    >>>            header=widgets.HTML("Create color dictionary - press ENTER when done"),
    >>>            item_class=SideBySideDictItem,
    >>>            focus_after_init=True,
    >>>            key_class=Text,
    >>>            key_is_valid=lambda value: value != "",
    >>>            key_kwargs=dict(
    >>>                value="",
    >>>                placeholder="Column value",
    >>>                width="lg",
    >>>                on_submit=lambda _: print("submit key),
    >>>            ),
    >>>            value_class=Text,
    >>>            value_is_valid=lambda value: value != "",
    >>>            value_kwargs=dict(
    >>>                value="",
    >>>                placeholder="Color e.g. #228b22 or green",
    >>>                width="lg",
    >>>                on_submit=lambda _: print("submit value),
    >>>            ),
    >>>        )
    """

    def __init__(
        self,
        header=widgets.VBox(),
        item_class=SideBySideDictItem,
        add_button_text="add",
        focus_after_init=False,
        **kwargs
    ):
        super().__init__()
        self.add_class("bamboolib-overflow-visible")

        self.item_class = item_class
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
        return self.item_class(**valid_kwargs)

    def get_initial_selector(self):
        return self.create_selector(
            focus_after_init=self.focus_after_init, show_delete_button=False
        )

    @property
    def value(self):
        return {
            item.key: item.value for item in self.get_selectors() if item.is_valid()
        }
