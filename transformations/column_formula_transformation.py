# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
import re

from bamboolib.helper import (
    Transformation,
    notification,
    DF_OLD,
    VSpace,
    BamboolibError,
)
from bamboolib.helper import string_to_code

from bamboolib.widgets import Text, BamAutocompleteTextV1


def _replace_column_names(formula, column_names):
    """
    Replace columns name in formula, e.g.
    f"Age + Age2 + 'Age'"
    into
    f"{DF_OLD}['Age'] + {DF_OLD}['Age2'] + 'Age'"

    Attention:
    - This shall exclude column names that are prefixed with a single or double quotation mark, e.g. ' or "
    - This needs to work for column names that are subsets of each other. This leads to the following
      2 implementation details:
        1. We need to replace the longest column names first so that the shorter names are not
           manipulating/destroying the longer names
        2. We need to do this in 2 replacement steps so that the intermediate results of the
           replacement of the longer names do not get partially replaced by the shorter names
    """

    # That sort is necessary. Need to replace longest column names first.
    column_names.sort(key=lambda string: len(string), reverse=True)

    formula, translation_dict = _first_replacement_step(formula, column_names)
    formula = _second_replacement_step(formula, translation_dict)
    return formula


def _first_replacement_step(formula, column_names):
    """
    Replace detected variables with placeholder names.

    As an example, replace Age2 and Age in
    f"Age + Age2 + 'Age'"
    with
    f"BAM_PLACEHOLDER_1_ + BAM_PLACEHOLDER_0_ + 'Age'"
    """
    translation_dict = {}
    counter = 0
    for column_name in column_names:
        if column_name in formula:
            placeholder = "BAM_PLACEHOLDER_%s_" % counter
            formula = _replace_token_that_is_not_prefixed_with_quotation(
                formula, column_name, placeholder
            )
            translation_dict[placeholder] = f"{DF_OLD}[{string_to_code(column_name)}]"
            counter += 1
    return formula, translation_dict


def _replace_token_that_is_not_prefixed_with_quotation(string, token, replacement):
    """
    This replaces a token in the string unless they are prefixed with ' or ".
    E.g. a becomes df["a"]
    """
    pattern = re.compile(f"(^|[^'\"])({token})")
    return pattern.sub(f"\\1{replacement}", string)


def _second_replacement_step(formula, translation_dict):
    """Replace all tokens in the formula."""
    for placeholder in translation_dict.keys():
        formula = _replace_token_that_is_not_prefixed_with_quotation(
            formula, placeholder, translation_dict[placeholder]
        )
    return formula


class ColumnFormulaTransformation(Transformation):
    """Create a new column from a formula e.g. math expression."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.new_column_input = Text(
            focus_after_init=True,
            description="New column name",
            width="lg",
            execute=self,
            css_classes=["bamboolib-new-column-name"],
        )

        self.column_names = self.get_df().columns.tolist()
        self.parsed_formula = ""

        self.formula_input = BamAutocompleteTextV1(column_names=self.column_names)
        self.formula_input.on_submit(lambda _: self.execute())

    # We overwrite the execute method so that formula is parsed before the actual execution.
    def execute(self):
        self._parse_formula()
        super().execute()

    def render(self):
        self.set_title("Create new column from formula")
        self.set_content(
            self.new_column_input,
            VSpace("sm"),
            widgets.HTML("Column formula"),
            self.formula_input,
            VSpace("lg"),
            notification(
                """
    <p>Write any valid python code (including lambdas). You can call columns directly by their name.</p><br>
    <p><b>Example</b></p>
    <ul>
        <li><code>(num_col_1 + num_col_2) / (num_col_3 ** 2)</code></li>
        <li><code>bool_col_1 & ~bool_col_2 | bool_col_3</code></li>
        <li><code>str_col.apply(lambda x: x[:2])</code></li>
        <li><code>str_col_1 + "_" + str_col_2</code></li>
    </ul>
"""
            ),
        )

    def _parse_formula(self, *args):
        """Parse the formula and replace all column names."""
        self.parsed_formula = _replace_column_names(
            self.formula_input.value, self.column_names
        )

    def _transformation_code(self):
        return f"{DF_OLD}[{string_to_code(self.new_column_input.value)}] = {self.parsed_formula}"

    def get_description(self):
        return f"<b>Create new column</b> '{self.new_column_input.value}' from formula '{self.formula_input.value}'"

    def is_valid_transformation(self):
        if self.new_column_input.value == "":
            raise BamboolibError(
                "The name for the new column is empty.<br>Please enter a 'New column name'"
            )
        if self.parsed_formula == "":
            raise BamboolibError(
                "The formula is empty.<br>Please enter a 'Column formula'"
            )
        return True

    def get_code(self):
        return self._transformation_code()
