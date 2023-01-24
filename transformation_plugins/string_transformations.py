# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

"""
Plugins for carrying out transformation on string columns. Such transformations can e.g. be:

- transform a string column to lowercase
- find and replace substrings in a column
- get the length of the strings in a column
"""

import re

from bamboolib.plugins import (
    TransformationPlugin,
    DF_OLD,
    Text,
    Singleselect,
    Multiselect,
)
from bamboolib.helper import (
    Transformation,
    safe_cast,
    notification,
    list_to_string,
    string_to_code,
    AuthorizedPlugin,
    BamboolibError,
)

import ipywidgets as widgets

STRING_TRANSFORMATION_DESCRIPTION_PREFIX = "Change text"
STRING_TRANSFORMATION_DESCRIPTION_SUFFIX = "(string transformation)"

NEW_COLUMN_NAME_SUFFIX_INPUT_DESCRIPTION = (
    "Suffix of new column name - empty for overwriting column(s)"
)
NEW_COLUMN_NAME_SUFFIX_INPUT_PLACEHOLDER = "Suffix of new column name(s)"


def get_simple_string_transformation_code(
    string_transformation_object, string_function_name
):
    """
    Produces transformation code for the simple string methods .lower(), .upper(), .len(), etc.

    :param string_transformation_object: the transformation object. It's needed because we need access
        to its input widgets' values.
    :param string_function_name: string. E.g. "lower", "upper", "titl", "len".
    """
    column_suffix = string_transformation_object.new_column_name_suffix_input.value
    code = []
    for column_name in string_transformation_object.columns_input.value:
        code.append(
            f"""{DF_OLD}[{string_to_code(f"{column_name}{column_suffix}")}] = {DF_OLD}[{string_to_code(column_name)}].str.{string_function_name}()"""
        )
    return "\n".join(code)


class StringTransformation(Transformation):
    """
    Base class for a string transformation.

    Acts like a decorator for Transformation plugins. It makes sure that the "decorated"
    Transformation plugin is only rendered if there are string columns the data.

    Attention: StringTransformation _must_ come before TransformationPlugin when
    inheriting from both.
    """

    def init_string_transformation(self):
        """TO BE OVERIDDEN by any child"""
        pass

    def render_string_transformation(self):
        """TO BE OVERIDDEN by any child"""
        pass

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.string_columns = list(
            self.get_df().select_dtypes(include=["object", "string"]).columns
        )
        if self.has_string_columns():
            self.init_string_transformation()

    def render(self):
        if self.has_string_columns():
            self.render_string_transformation()
        else:
            # LATER: allow this anyway? and implicitely convert the column to string? maybe show a warning?
            message = notification(
                "<b>Error:</b> Currently, the dataframe contains no columns with data type string.",
                type="error",
            )
            # Attention: set content on outlet because we dont want to show an execute button
            self.outlet.set_content(message)

    def has_string_columns(self):
        return len(self.string_columns) > 0


# Attention: StringTransformation has to come before TransformationPlugin
class SplitString(StringTransformation, AuthorizedPlugin, TransformationPlugin):

    name = "Split text column"
    description = f"{STRING_TRANSFORMATION_DESCRIPTION_PREFIX}: split a column based on a delimiter {STRING_TRANSFORMATION_DESCRIPTION_SUFFIX}"

    def __init__(self, *args, default_manipulation_options={}, **kwargs):
        """
        :param default_manipulation_options: dict. Contains some options with which split text is called.
            default_manipulation_options is nonempy when SplitString is called by SuggestStringManipulation
        """

        self.selected_column_name = default_manipulation_options.get(
            "selected_column_name", None
        )
        self.selected_pattern = default_manipulation_options.get("selected_pattern", "")
        self.focus_after_init = default_manipulation_options.get(
            "focus_column_input_after_init", True
        )
        super().__init__(*args, **kwargs)

    def init_string_transformation(self):
        self.column_input = Singleselect(
            options=self.string_columns,
            value=self.selected_column_name,
            placeholder="Choose column",
            focus_after_init=self.focus_after_init,
            width="lg",
        )

        self.pattern_input = Text(
            description="Separator",
            value=self.selected_pattern,
            placeholder="",
            execute=self,
            width="lg",
        )

        self.use_regular_expression = widgets.Checkbox(
            description="Use regular expression in Separator", value=False
        )
        self.use_regular_expression.add_class("bamboolib-checkbox")

        self.max_number_of_splits = Text(
            description="Max number of splits, empty for no limit",
            placeholder="Max number of splits, optional",
            execute=self,
            width="lg",
        )

    def render_string_transformation(self):
        self.set_title("Split string")
        self.set_content(
            self.column_input,
            self.pattern_input,
            self.use_regular_expression,
            self.max_number_of_splits,
        )

    def get_description(self):
        separator_string = self.pattern_input.value
        return f"<b>Manipulate strings</b> of '{self.column_input.value}' and perform a split on '{separator_string}'"

    def get_code(self):
        separator_string = self.pattern_input.value

        if not self.use_regular_expression.value:
            separator_string = re.escape(separator_string)

        max_number_of_splits = safe_cast(self.max_number_of_splits.value, int, 0)
        max_number_of_splits_code = (
            f", n={max_number_of_splits}" if max_number_of_splits > 0 else ""
        )

        code = "\n".join(
            [
                f"""split_df = {DF_OLD}[{string_to_code(self.column_input.value)}].str.split({string_to_code(separator_string)}{max_number_of_splits_code}, expand=True)""",
                f"""split_df.columns = [{string_to_code(self.column_input.value)} + f\"_{{id_}}\" for id_ in range(len(split_df.columns))]""",
                # the final merge part is a litle bit tricky because there might be columns with the same name
                # the following code fixes the problem via adding suffixes
                f"""{DF_OLD} = pd.merge({DF_OLD}, split_df, how="left", left_index=True, right_index=True)""",
                # alternative solution:
                # # df = pd.concat([df, split_df], axis=1)
                # however, this might result in columns with the same name, will raise error if verify_integrity=True is passed
            ]
        )
        return code

    """Function to programmatically set user input. Used for unit tests."""

    def test_set_split_string_input(
        self,
        column_name: str,
        separator: str,
        use_regular_expression: bool = False,
        max_number_of_splits: str = "0",
    ) -> None:
        self.column_input.value = column_name
        self.pattern_input.value = separator
        self.use_regular_expression.value = use_regular_expression
        self.max_number_of_splits.value = max_number_of_splits


# Attention: StringTransformation has to come before TransformationPlugin
class ToLowercase(StringTransformation, AuthorizedPlugin, TransformationPlugin):

    name = "Convert to lowercase"
    description = f"{STRING_TRANSFORMATION_DESCRIPTION_PREFIX}: convert text to lowercase {STRING_TRANSFORMATION_DESCRIPTION_SUFFIX}"

    def init_string_transformation(self):
        self.columns_input = Multiselect(
            options=self.string_columns,
            placeholder="Choose column(s)",
            focus_after_init=True,
            width="lg",
        )
        self.new_column_name_suffix_input = Text(
            description=NEW_COLUMN_NAME_SUFFIX_INPUT_DESCRIPTION,
            value="_lower",
            placeholder=NEW_COLUMN_NAME_SUFFIX_INPUT_PLACEHOLDER,
            execute=self,
            width="lg",
        )

    def render_string_transformation(self):
        self.set_title("To lower case")
        self.set_content(
            widgets.HTML("Convert"),
            self.columns_input,
            widgets.HTML("to lowercase"),
            self.new_column_name_suffix_input,
        )

    def get_description(self):
        return f"Convert {list_to_string(self.columns_input.value)} to <b>lowercase</b>"

    def get_code(self):
        return get_simple_string_transformation_code(self, "lower")

    def test_set_to_lowercase_input(self, column_names: list, suffix: str = "_lower"):
        self.columns_input.value = column_names
        self.new_column_name_suffix_input.value = suffix


# Attention: StringTransformation has to come before TransformationPlugin
class ToUppercase(StringTransformation, AuthorizedPlugin, TransformationPlugin):

    name = "Convert to uppercase"
    description = f"{STRING_TRANSFORMATION_DESCRIPTION_PREFIX}: convert text to uppercase {STRING_TRANSFORMATION_DESCRIPTION_SUFFIX}"

    def init_string_transformation(self):
        self.columns_input = Multiselect(
            options=self.string_columns,
            placeholder="Choose column(s)",
            focus_after_init=True,
            width="lg",
        )
        self.new_column_name_suffix_input = Text(
            description=NEW_COLUMN_NAME_SUFFIX_INPUT_DESCRIPTION,
            value="_upper",
            placeholder=NEW_COLUMN_NAME_SUFFIX_INPUT_PLACEHOLDER,
            execute=self,
            width="lg",
        )

    def render_string_transformation(self):
        self.set_title("To uppercase")
        self.set_content(
            widgets.HTML("Convert"),
            self.columns_input,
            widgets.HTML("to uppercase"),
            self.new_column_name_suffix_input,
        )

    def get_description(self):
        return f"Convert {list_to_string(self.columns_input.value)} to <b>uppercase</b>"

    def get_code(self):
        return get_simple_string_transformation_code(self, "upper")

    def test_set_to_uppercase_input(self, column_names: list):
        self.columns_input.value = column_names


# Attention: StringTransformation has to come before TransformationPlugin
class ToTitle(StringTransformation, AuthorizedPlugin, TransformationPlugin):

    name = "Capitalize every word"
    description = f"{STRING_TRANSFORMATION_DESCRIPTION_PREFIX}: put a capital letter at the beginning of each new word {STRING_TRANSFORMATION_DESCRIPTION_SUFFIX}"

    def init_string_transformation(self):
        self.columns_input = Multiselect(
            options=self.string_columns,
            placeholder="Choose column(s)",
            focus_after_init=True,
            width="lg",
        )
        self.new_column_name_suffix_input = Text(
            description=NEW_COLUMN_NAME_SUFFIX_INPUT_DESCRIPTION,
            value="_title",
            placeholder=NEW_COLUMN_NAME_SUFFIX_INPUT_PLACEHOLDER,
            execute=self,
            width="lg",
        )

    def render_string_transformation(self):
        self.set_title("Capitalize every word")
        self.set_content(
            widgets.HTML("Capitalize every word in"),
            self.columns_input,
            self.new_column_name_suffix_input,
        )

    def get_description(self):
        return f"<b>Capitalize every word</b> in {list_to_string(self.columns_input.value)}"

    def get_code(self):
        return get_simple_string_transformation_code(self, "title")

    def test_set_to_title_input(self, column_names: list):
        self.columns_input.value = column_names


# Attention: StringTransformation has to come before TransformationPlugin
class Capitalize(StringTransformation, AuthorizedPlugin, TransformationPlugin):
    """Put a capital letter at the beginning of each string in a cell."""

    name = "Capitalize"
    description = f"{STRING_TRANSFORMATION_DESCRIPTION_PREFIX}: put a capital letter at the beginning of each cell {STRING_TRANSFORMATION_DESCRIPTION_SUFFIX}"

    def init_string_transformation(self):
        self.columns_input = Multiselect(
            options=self.string_columns,
            placeholder="Choose column(s)",
            focus_after_init=True,
            width="lg",
        )
        self.new_column_name_suffix_input = Text(
            description=NEW_COLUMN_NAME_SUFFIX_INPUT_DESCRIPTION,
            value="_capitalize",
            placeholder=NEW_COLUMN_NAME_SUFFIX_INPUT_PLACEHOLDER,
            execute=self,
            width="lg",
        )

    def render_string_transformation(self):
        self.set_title("Capitalize text")
        self.set_content(
            widgets.HTML("Capitalize text in"),
            self.columns_input,
            self.new_column_name_suffix_input,
        )

    def get_description(self):
        return f"<b>Capitalize</b> text in {list_to_string(self.columns_input.value)}"

    def get_code(self):
        return get_simple_string_transformation_code(self, "capitalize")

    def test_set_capitalize_input(self, column_names: list):
        self.columns_input.value = column_names


# Attention: StringTransformation has to come before TransformationPlugin
class RemoveLeadingAndTrailingWhitespaces(
    StringTransformation, AuthorizedPlugin, TransformationPlugin
):

    name = "Remove leading and trailing whitespaces"
    description = f"{STRING_TRANSFORMATION_DESCRIPTION_PREFIX}: remove leading and trailing whitespaces in text column {STRING_TRANSFORMATION_DESCRIPTION_SUFFIX}"

    def init_string_transformation(self):
        self.columns_input = Multiselect(
            options=self.string_columns,
            placeholder="Choose column(s)",
            focus_after_init=True,
            width="lg",
        )
        self.new_column_name_suffix_input = Text(
            description=NEW_COLUMN_NAME_SUFFIX_INPUT_DESCRIPTION,
            value="_stripped",
            placeholder=NEW_COLUMN_NAME_SUFFIX_INPUT_PLACEHOLDER,
            execute=self,
            width="lg",
        )

    def render_string_transformation(self):
        self.set_title("Remove leading and trailing whitespaces")
        self.set_content(
            widgets.HTML("Remove leading and trailing whitespaces in"),
            self.columns_input,
            self.new_column_name_suffix_input,
        )

    def get_description(self):
        return f"<b>Remove leading and trailing whitespaces</b> in {list_to_string(self.columns_input.value)}"

    def get_code(self):
        return get_simple_string_transformation_code(self, "strip")

    def test_set_remove_whitespaces_input(self, column_names: list):
        self.columns_input.value = column_names


# Attention: StringTransformation has to come before TransformationPlugin
class LengthOfString(StringTransformation, AuthorizedPlugin, TransformationPlugin):

    name = "Count the characters in text"
    description = f"{STRING_TRANSFORMATION_DESCRIPTION_PREFIX}: count the characters in text (including spaces and punctuation) {STRING_TRANSFORMATION_DESCRIPTION_SUFFIX}"

    def init_string_transformation(self):
        self.columns_input = Multiselect(
            options=self.string_columns,
            placeholder="Choose column(s)",
            focus_after_init=True,
            width="lg",
        )
        self.new_column_name_suffix_input = Text(
            description=NEW_COLUMN_NAME_SUFFIX_INPUT_DESCRIPTION,
            value="_length",
            placeholder=NEW_COLUMN_NAME_SUFFIX_INPUT_PLACEHOLDER,
            execute=self,
            width="lg",
        )

    def render_string_transformation(self):
        self.set_title("Count characters")
        self.set_content(
            notification("Spaces and punctuation will also be counted"),
            widgets.HTML("Count the characters in"),
            self.columns_input,
            self.new_column_name_suffix_input,
        )

    def get_description(self):
        return f"<b>Count characters</b> in {list_to_string(self.columns_input.value)}"

    def get_code(self):
        return get_simple_string_transformation_code(self, "len")


# Attention: StringTransformation has to come before TransformationPlugin
class FindAndReplaceText(StringTransformation, AuthorizedPlugin, TransformationPlugin):
    """Find and replace a substring in a column"""

    name = "Find and replace text in column"
    description = f"{STRING_TRANSFORMATION_DESCRIPTION_PREFIX}: substitute (partial) text in a single column {STRING_TRANSFORMATION_DESCRIPTION_SUFFIX}"

    def __init__(self, *args, default_manipulation_options={}, **kwargs):
        """
        :param default_manipulation_options: dict. Contains some options with which split text is called.
            default_manipulation_options is nonempy when SplitString is called by SuggestStringManipulation
        """

        self.selected_column_name = default_manipulation_options.get(
            "selected_column_name", None
        )
        self.find = default_manipulation_options.get("find", "")
        self.focus_after_init = default_manipulation_options.get(
            "focus_column_input_after_init", True
        )
        super().__init__(*args, **kwargs)

    def user_changed_column_input(self, column):
        if column is None:
            column = ""
        self.set_column(column)

    def init_string_transformation(self):
        self.column_input = Singleselect(
            options=self.string_columns,
            placeholder="Choose column",
            value=self.selected_column_name,
            focus_after_init=self.focus_after_init,
            # Usually, we would use set_column() directly here as a callback.
            # However, when calling FindAndReplaceText from the search bar, no column is selected
            # and self.column_input.value is None, which set_column() cannot handle
            # That's why we wrote a wrapper that handles the None case
            # To be refactored when we use this more than twice
            on_change=lambda dropdown: self.user_changed_column_input(dropdown.value),
            width="lg",
        )

        self.find_input = Text(
            description="Find", value=self.find, placeholder="", execute=self
        )

        self.replace_input = Text(
            description="and replace with", value="", placeholder="", execute=self
        )

        self.use_regular_expression = widgets.Checkbox(
            description="Use regular expression in find", value=False
        )
        self.use_regular_expression.add_class("bamboolib-checkbox")

        self.user_changed_column_input(self.column_input.value)

    def render_string_transformation(self):
        self.set_title("Find and replace text")
        self.set_content(
            self.column_input,
            self.find_input,
            self.replace_input,
            self.use_regular_expression,
            self.rename_column_group,
        )

    def get_description(self):
        find_string = self.find_input.value
        replace_string = self.replace_input.value
        return f"<b>Manipulate strings</b> of '{self.column_input.value}' via Find '{find_string}' and Replace with '{replace_string}'"

    def get_code(self):
        find_string = self.find_input.value
        find_string = find_string.replace("'", "\\'")
        replace_string = self.replace_input.value
        replace_string = replace_string.replace("'", "\\'")

        return f"""{DF_OLD}["{self.new_column_name_input.value}"] = {DF_OLD}["{self.column_input.value}"].str.replace('{find_string}', '{replace_string}', regex={self.use_regular_expression.value})"""

    def is_valid_transformation(self):
        if self.column_input.value is None:
            raise BamboolibError(
                """
                You haven't specified the column in which you want to replace text.
                Please select a column.
            """
            )
        return True

    def test_set_find_replace_input(
        self,
        column_name: str,
        find_string: str,
        replace_string: str,
        use_regular_expression: bool,
    ) -> None:
        self.column_input.value = column_name
        self.find_input.value = find_string
        self.replace_input.value = replace_string
        self.use_regular_expression.value = use_regular_expression


# Attention: StringTransformation has to come before TransformationPlugin
class ExtractText(StringTransformation, AuthorizedPlugin, TransformationPlugin):
    """Extract text based on position"""

    name = "Extract text based on position"
    description = f"{STRING_TRANSFORMATION_DESCRIPTION_PREFIX}: extract a text from a column based on position of text {STRING_TRANSFORMATION_DESCRIPTION_SUFFIX}"

    def init_string_transformation(self):
        self.column_input = Singleselect(
            options=self.string_columns,
            placeholder="Choose column",
            focus_after_init=True,
            set_soft_value=True,
            on_change=lambda dropdown: self.set_column(dropdown.value),
            width="lg",
        )

        self.start_position = Text(
            description="Start position",
            placeholder="from the beginning",
            execute=self,
            width="lg",
        )

        self.stop_position = Text(
            description="Stop position",
            placeholder="until the end",
            execute=self,
            width="lg",
        )
        self.set_column(self.column_input.value)

    def render_string_transformation(self):
        self.set_title("Extract text based on position")
        self.set_content(
            self.column_input,
            self.start_position,
            self.stop_position,
            self.rename_column_group,
        )

    def _get_position_value(self, position_text_field):
        if position_text_field.value == "":
            return None
        else:
            return int(position_text_field.value)

    def _get_start_position(self):
        return self._get_position_value(self.start_position)

    def _get_stop_position(self):
        return self._get_position_value(self.stop_position)

    def get_description(self):
        start_string = self._get_start_position()
        if start_string is None:
            start_string = "beginning"
        stop_string = self._get_stop_position()
        if stop_string is None:
            stop_string = "end"

        return f"<b>Extract text</b> from '{self.column_input.value}' from the position '{start_string}' until the position '{stop_string}'"

    def get_code(self):
        return f"""{DF_OLD}[{string_to_code(self.new_column_name_input.value)}] = {DF_OLD}[{string_to_code(self.column_input.value)}].str.slice(start={self._get_start_position()}, stop={self._get_stop_position()})"""
