# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode
from bamboolib import __widgets_version__

from pygments import highlight
from pygments.lexers import PythonLexer
from pygments.formatters import HtmlFormatter


@widgets.register()
class CodeOutput(widgets.DOMWidget):
    """
    The widget displays code to the user
    """

    _view_name = Unicode("BamCodeOutputView").tag(sync=True)
    _model_name = Unicode("BamCodeOutputModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    _code_html = Unicode("").tag(sync=True)

    def __init__(self, code: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._code = code
        self._code_html = self.get_python_syntax_highlighted_code_html(code)

    def get_python_syntax_highlighted_code_html(self, code):
        # ATTENTION(PROD-27053) / TODO(PROD-27053): we don't set HtmlFormatter(full=True) as this ships inline CSS that overwrites
        # the body of the iframe. Instead, we should ship our own CSS with better scoping.
        return highlight(code, lexer=PythonLexer(), formatter=HtmlFormatter(full=False))

    @property
    def code(self):
        return self._code

    @code.setter
    def code(self, value: str) -> None:
        self._code = value
        self._code_html = self.get_python_syntax_highlighted_code_html(value)
