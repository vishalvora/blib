# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode, List, Bool, Integer
from bamboolib import __widgets_version__
import json


# Improvement: maybe allow the value to contain non-hashable items, e.g. lists or other complex objects
# This might make the client code easier sometimes
# Implement this via a value lookup for the current label?
# Then, we cannot have an options_by_value dict any more


# Improvement: allow to change all attributes of Multiselect or Singleselect
# and automatically handle rerender in JS - similar to max_items
# e.g. via adding a rerender message that renders JS again with the current state
# then we just need to add setter methods for all attributes and trigger render
# Complication: on top of my head: unsure of how that should behave for set_soft_value in Singleselect


@widgets.register()
class Multiselect(widgets.DOMWidget):
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

    _view_name = Unicode("BamSelectizeView").tag(sync=True)
    _model_name = Unicode("BamSelectizeModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    placeholder = Unicode("").tag(sync=True)
    _max_items = Integer(None, allow_none=True).tag(sync=True)
    enabled = Bool(True).tag(sync=True)
    focus_after_init = Bool(False).tag(sync=True)
    # _did_focus_after_init is true after the first init
    # This information is important so that the JS does not focus again at a later render
    # Scenario: When widgets are rendered again e.g. during editing an existing transformation,
    # then the widget should not be focused again.
    _did_focus_after_init = Bool(False).tag(sync=True)
    # _is_soft_value only applies to dropdowns and changes the user behavior together with _prevent_empty_list (see below)
    # when the user (first) focuses the Singleselect, the value will be cleared and he can search
    # in the meantime, the .value attribute is set
    # this solves two problems:
    # 1) the user wants to search when he never entered a value
    # 2) when building the UI, other elements state might depend on the dropdowns value.
    #       When the value might be None, then we need massive overhead of checking for that
    #       We can mitigate this overhead via setting a soft_value and still have good user experience
    _is_soft_value = Bool(False).tag(sync=True)
    # _prevent_empty_list is tightly connected to _is_soft_value (see comment above)
    # The boolean flag enables or disables the feature of keeping the last selected value
    # when the user clears the selection
    # This is a different flag from _is_soft_value because _is_soft_value is toggled by the frontend
    # and might be set from True to False
    # However, _prevent_empty_list does not change during the lifetime of a Singleselect
    # IMPLICATION: if _prevent_empty_list is True, on_change will not trigger when the value is set to []
    _prevent_empty_list = False
    select_on_tab = Bool(False).tag(sync=True)

    _options = (
        []
    )  # list of options in the form of {label:label, value:value, description:description}
    _options_by_label = {}  # dict(label1=option1, label2=option2)
    _options_by_value = {}  # dict(value1=option1, value2=option2)
    optionsSelectize = List([]).tag(
        sync=True
    )  # list of {text: label, value: label, description:description}

    items = []  # list of hashable values e.g. [True, "test", 1]
    itemsSelectize = List([]).tag(sync=True)  # list of string labels
    itemsSelectizeOldJSON = ""

    def __init__(
        self,
        options=[],
        value=[],
        placeholder="Choose value(s)",
        max_items=None,
        enabled=True,
        focus_after_init=False,
        _is_soft_value=False,
        _prevent_empty_list=False,
        select_on_tab=False,
        width="md",
        on_change=None,
        css_classes=[],
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._change_callbacks = widgets.CallbackDispatcher()
        self.on_msg(self.handle_message_from_js)

        self.add_class("bamboolib-overflow-visible")
        if width is not None:
            self.add_class(f"selectize-{width}")

        if on_change is not None:
            self.on_change(on_change)

        self.placeholder = placeholder
        self._max_items = max_items
        self.enabled = enabled
        self.focus_after_init = focus_after_init
        self._did_focus_after_init = False
        self._is_soft_value = _is_soft_value
        self._prevent_empty_list = _prevent_empty_list
        self.select_on_tab = select_on_tab

        for css_class in css_classes:
            self.add_class(css_class)

        # this should happen last because the functions need the state that was setup before
        self._set_options(options)
        self.maybe_set_items(value, trigger_on_change=False)

    def _normalize_options(self, iterable):
        """
        Maybe convert a list of option elements to {label: label, value: value, description: description}
        convertable input formats:
            - list of strings
            - list of (label, value) tuples
        If iterable is already a list of dicts, we make sure it is in the form {label: label, value: value, description: description}. In the latter case, if description is missing, we fill with ""
        """
        if len(iterable) > 0:
            if isinstance(iterable[0], tuple):
                iterable = [
                    {"label": item[0], "value": item[1], "description": ""}
                    for item in iterable
                ]
            elif isinstance(iterable[0], str):
                iterable = [
                    {"label": item, "value": item, "description": ""}
                    for item in iterable
                ]
            elif isinstance(iterable[0], dict):
                iterable = [
                    {
                        "label": item["label"],
                        "value": item["value"],
                        "description": item.get("description", ""),
                    }
                    for item in iterable
                ]
        return iterable

    def _set_options(self, options):
        options = self._normalize_options(options)
        self._options = options
        # Need to change the mapping to the format of selectize.js
        self.optionsSelectize = [
            # Attention: "text": option["label"], "value": option["label"] is NOT a typo!
            {
                "text": option["label"],
                "value": option["label"],
                "description": option["description"],
            }
            for option in options
        ]
        try:
            element_that_should_be_set = "label"
            self._options_by_label = {option["label"]: option for option in options}
            element_that_should_be_set = "value"
            self._options_by_value = {option["value"]: option for option in options}
        except Exception as exception:
            if isinstance(exception, TypeError) and (
                "unhashable type" in str(exception)
            ):
                raise TypeError(
                    f"You did pass invalid options. The {element_that_should_be_set} of each option item needs to be hashable. Some examples for hashable types are string, int, float, boolean or tuple. Some examples for unhashable types are list or dict. Please adjust your options"
                )
            else:
                raise exception

    def _get_max_items_of(self, list_):
        if self._max_items is None:
            return list_
        else:
            if len(list_) > self._max_items:
                return list_[: self._max_items]
            else:
                return list_

    def deduplicate_items(self, list_):
        deduplicated = []
        for item in list_:
            if item in deduplicated:
                pass
            else:
                deduplicated.append(item)
        return deduplicated

    def maybe_set_items(self, items, trigger_on_change=True):
        if (len(items) == 0) and self._prevent_empty_list:
            return  # don't set the new items and, thus, keep the old items

        items_in_options = [
            item for item in items if item in self._options_by_value.keys()
        ]
        unique_items = self.deduplicate_items(items_in_options)
        valid_items = self._get_max_items_of(unique_items)
        if self.items == valid_items:
            return  # do nothing in order not to trigger the on_change callback
        self.items = valid_items
        self.itemsSelectize = [
            self._options_by_value[item]["label"] for item in self.items
        ]
        self._save_JSON_dump(self.itemsSelectize)

        if trigger_on_change:
            self._change_callbacks(self)

    def handle_message_from_js(self, widget, content, buffers=None):
        type_ = content.get("type", "")
        if type_ == "on_change":
            itemsSelectize = content.get("itemsSelectize", [])
            # syncing the value AND triggering an event did not work
            # because the model value was not yet set at the time of the event
            # maybe because model updates takes more time and cannot be used in parallel to a message
            # just syncing the value from js works for _did_focus_after_init
            if self._selectize_items_changed(itemsSelectize):
                new_items = [
                    self._options_by_label[label]["value"] for label in itemsSelectize
                ]
                self.maybe_set_items(new_items)

    def _save_JSON_dump(self, itemsSelectize):
        self.itemsSelectizeOldJSON = json.dumps(itemsSelectize)

    def _selectize_items_changed(self, itemsSelectize):
        return self.itemsSelectizeOldJSON != json.dumps(itemsSelectize)

    def on_change(self, callback, remove=False):
        """
        Add or remove an on_change callback that is triggered when the `value` changes.

        :param callback: a function that expects the widget itself as single argument
        :param remove: boolean

        Example:
        >>> widget.on_change(lambda widget: print("The value changed!"))
        """
        self._change_callbacks.register_callback(callback, remove=remove)

    # Attention: this attribute shall not be set. Thus, we omitted the setter
    @property
    def label(self):
        """
        Get the label. Important: the label can not be set. If you want to set the label, set the value instead.
        """
        return [self._options_by_value[item]["label"] for item in self.items]

    @property
    def value(self):
        return self.items

    @value.setter
    def value(self, value):
        self.maybe_set_items(value)

    @property
    def options(self):
        return self._options

    @options.setter
    def options(self, options):
        self._set_options(options)
        self.maybe_set_items(self.value, trigger_on_change=False)

    @property
    def max_items(self):
        return self._max_items

    @max_items.setter
    def max_items(self, max_items):
        self._max_items = max_items
        self.maybe_set_items(self.value, trigger_on_change=False)
        self.send({"type": "rerender"})

    def focus(self):
        """
        The widget acquires focus in the browser.
        Only works if the widget is already rendered
        if you are unsure if it is rendered, use focus_after_init
        """
        self.send({"type": "focus"})


class Singleselect(Multiselect):
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

    def __init__(
        self,
        options=[],
        value=None,
        placeholder="Choose",
        set_soft_value=False,
        **kwargs,
    ):
        self.set_soft_value = set_soft_value

        super().__init__(
            max_items=1,
            options=options,
            placeholder=placeholder,
            _is_soft_value=set_soft_value,
            _prevent_empty_list=set_soft_value,
            **kwargs,
        )

        self._ensure_compatibility_between_set_soft_value_and_options()

        self._maybe_set_value(value, trigger_on_change=False)
        if self.set_soft_value and self.value is None:
            self._maybe_set_value(self.options[0]["value"], trigger_on_change=False)

    def _ensure_compatibility_between_set_soft_value_and_options(self):
        if self.set_soft_value and len(self.options) == 0:
            raise ValueError(
                "You did not pass any options but set_soft_value to True. This is not possible because set_soft_value requires at least 1 option. Please change set_soft_value to False or pass some options"
            )

    @property
    def value(self):
        if len(self.items) == 0:
            return None
        else:
            return self.items[0]

    @value.setter
    def value(self, value):
        self._maybe_set_value(value, trigger_on_change=True)

    def _maybe_set_value(self, value, trigger_on_change=True):
        if value is None:
            self.maybe_set_items([], trigger_on_change=trigger_on_change)
        elif value in self._options_by_value.keys():
            self.maybe_set_items([value], trigger_on_change=trigger_on_change)
        else:
            return  # do not set invalid values

    # Attention: this attribute shall not be set. Thus, we omitted the setter
    @property
    def label(self):
        """
        Get the label. Important: the label can not be set. If you want to set the label, set the value instead.
        """
        if len(self.items) == 0:
            return None
        else:
            return self._options_by_value[self.value]["label"]

    @property
    def options(self):
        return self._options

    @options.setter
    def options(self, options):
        self._set_options(options)
        self._ensure_compatibility_between_set_soft_value_and_options()

        self._maybe_set_value(self.value, trigger_on_change=False)
        if self.value not in self._options_by_value.keys():
            if self.set_soft_value:
                self._maybe_set_value(self.options[0]["value"], trigger_on_change=False)
            else:
                self._maybe_set_value(None, trigger_on_change=False)

    # Attention: this attribute shall not be set. Thus, we omitted the setter
    @property
    def max_items(self):
        raise AttributeError(
            "'Singleselect' object has no attribute 'max_items' - only 'Multiselect' has this attribute"
        )
