# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


import ipywidgets as widgets

from bamboolib import __widgets_version__
from traitlets import Unicode, Bool, Integer


@widgets.register()
class BamAutocompleteTextV0(widgets.DOMWidget):
    """The bamboolib text input with autocompletion on column names."""

    _view_name = Unicode("BamAutocompleteTextView").tag(sync=True)
    _model_name = Unicode("BamAutocompleteTextModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    value = Unicode("").tag(sync=True)
    placeholder = Unicode("", help="The value placeholder").tag(sync=True)
    margin_top = Integer(0, help="css margin-top in px.").tag(sync=True)
    nrows = Integer(2, help="The height in number of text rows.").tag(sync=True)
    focus_after_init = Bool(False).tag(sync=True)

    def __init__(
        self,
        value: str = "",
        placeholder: str = "",
        margin_top: int = 0,
        nrows: int = 2,
        focus_after_init: bool = False,
        # Attention: We don't add a dict type to symbols to make sure patching it to be a custom type
        # won't break the code.
        symbols={},
        column_names: list = [],
        show_symbol_completions: bool = False,
        css_classes=[],
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._submission_callbacks = widgets.CallbackDispatcher()
        self._completion_id = 0

        self.on_msg(self.handle_message_from_js)

        self.value = value
        self.placeholder = placeholder
        self.margin_top = margin_top
        self.nrows = nrows
        self.focus_after_init = focus_after_init

        self.symbols = symbols
        self.column_names = column_names
        self.show_symbol_completions = show_symbol_completions
        # this import takes a while - therefore we trigger it when a new complete widget is built
        # the alternative would be to always import it at the top
        import jedi

        for css_class in css_classes:
            self.add_class(css_class)

    def _completion_is_not_outdated(self, completion_id):
        return self._completion_id == completion_id

    def create_completions(self, input_, cursor_position, completion_id):
        # completions = [
        #         {
        #             "label": "df2",
        #             "completion": "f2",
        #         },
        #         {
        #             "label": "df3",
        #             "completion": "f3",
        #         },
        #     ];
        def calculate_completions():
            try:
                if self._last_character_is_quotation(input_, cursor_position):
                    completions = []
                else:
                    completions = self.column_name_completions(input_, cursor_position)
                    if self.show_symbol_completions:
                        completions += self.interpreter_completions(
                            input_, cursor_position
                        )
                    completions = completions[:10]  # first 10 completions or less

                if self._completion_is_not_outdated(completion_id):
                    self.send_completions(completions)
            except:
                pass  # silently will catch errors eg jedi ValueError: Please provide a position that exists within this node.
                # this happens when the user already continued typing and jedi was too slow and then there is a mismatch between the content of the input_ and what jedi expects

        from bamboolib.helper import execute_asynchronously

        execute_asynchronously(calculate_completions)
        # TODO: now we should also pass in an completion request ID so that the frontend does not show completions that just took longer to compute

    def send_completions(self, completions):
        self.send({"type": "completion", "completions": completions})

    def maybe_reduce_string_to_last_variable_name(self, string: str) -> str:
        import re

        # https://regex101.com
        # test strings:
        # df"Su
        # df'Su
        any_string_after_quotation = """.*["']([^\n]*)$"""
        matcher = re.search(any_string_after_quotation, string)
        if matcher is not None:
            string = matcher.groups()[0]
        return string

    def _last_character_is_quotation(self, input_: str, cursor_position: int) -> bool:
        before_cursor = input_[:cursor_position]

        if len(before_cursor) < 1:
            return False
        else:
            last_character = before_cursor[-1]
            return last_character in "\"'"

    def column_name_completions(self, input_: str, cursor_position: int) -> list:
        before_cursor = input_[:cursor_position]
        after_cursor = input_[cursor_position:]

        input_ = self.maybe_reduce_string_to_last_variable_name(before_cursor)

        completions = []
        for column in self.column_names:
            if column.startswith(input_):
                completion = column[len(input_) :]  # all characters after position
                completions.append({"label": column, "completion": completion})
        return completions

    def interpreter_completions(self, input_: str, cursor_position: int = None) -> list:
        import jedi  # just make symbol available - already imported during init

        interpreter = jedi.Interpreter(input_, [self.symbols], column=cursor_position)

        completions = []
        for completion in interpreter.completions():
            if len(completions) < 10:
                completions.append(
                    {"label": completion.name, "completion": completion.complete}
                )
        return completions

    def handle_message_from_js(self, widget, content, buffers=None):
        type_ = content.get("type", "")
        if type_ == "completion_request":
            self._completion_id += 1
            self.create_completions(
                content.get("input", ""),
                content.get("cursor_position", None),
                self._completion_id,
            )
        if type_ == "on_press_enter":
            self._submission_callbacks(self)

    def on_submit(self, callback, remove: bool = False) -> None:
        self._submission_callbacks.register_callback(callback, remove=remove)


@widgets.register()
class BamAutocompleteTextV1(BamAutocompleteTextV0):
    """Version 1 of the bamboolib text input with column autocompletion."""

    def maybe_reduce_string_to_last_variable_name(self, string):
        import re

        pattern = """.*[(,+-/*]\\s*([^\n]*)$"""
        matcher = re.search(pattern, string)
        if matcher is not None:
            string = matcher.groups()[0]
        return string
