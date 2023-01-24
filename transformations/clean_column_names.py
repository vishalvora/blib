# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from bamboolib.helper import Transformation, DF_OLD, notification, VSpace


class CleanColumnNames(Transformation):
    """Cleans the column names (make them lower case / snake_case, remove punctuation, etc.)"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def render(self):
        self.set_title("Clean column names")
        self.set_content(
            widgets.HTML(
                """Remove leading and trailing whitespaces, convert to
                <code>snake_case</code>, and remove any punctuation."""
            ),
            VSpace("xl"),
            notification(
                """<b>Like this feature?</b>
                <p>If you like this feature and want us to add more options, please
                <a href="mailto:bamboolib-feedback+bamboolib_clean_column_names@databricks.com">
                send us a message</a>.</p>""",
                type="info",
            ),
        )

    def get_description(self):
        return "<b>Clean column names</b>"

    def get_code(self):
        # .str.replace('((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))', r'_\1')  # MeanAge -> Mean_Age
        # .str.replace('[}}{{)(><.!?\\\\\\\\:;,-]', ''))  # remove punctuation
        # "}}" is just the f-string way of escaping "}" - same with "{{"
        # "\\\\\\\\" boils down to "\\\\" in the exported code
        return f"""
cleaned_column_names = ({DF_OLD}.columns
                        .str.strip()
                        .str.replace('((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))', r'_\\1')
                        .str.lower()
                        .str.replace('[ _-]+', '_')
                        .str.replace('[}}{{)(><.!?\\\\\\\\:;,-]', ''))
{DF_OLD}.columns = cleaned_column_names
        """.strip()
