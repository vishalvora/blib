# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

from bamboolib.helper import Transformation, DF_OLD, string_to_code, BamboolibError

from bamboolib.widgets import Singleselect


class CopyColumn(Transformation):
    """Copy a Dataframe column."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.column_to_copy = Singleselect(
            options=self.get_options(),
            placeholder="Choose column",
            set_soft_value=True,
            width="xl",
            focus_after_init=True,
        )

    def get_options(self):
        return list(self.df_manager.get_current_df().columns)

    def render(self):
        self.set_title("Copy Column")
        self.set_content(self.column_to_copy, self.new_column_name_input)

    def is_valid_transformation(self):
        if self.new_column_name_input.value == "":
            raise BamboolibError("New column name cannot be blank")

        return True

    def get_description(self):
        return "Copy a dataframe column"

    def get_code(self):
        new_name = string_to_code(self.new_column_name_input.value)
        old_name = string_to_code(self.column_to_copy.value)
        return f"{DF_OLD}[{new_name}] = {DF_OLD}[{old_name}]"
