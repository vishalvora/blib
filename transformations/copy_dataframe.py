# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

from bamboolib.helper import Transformation, DF_OLD, DF_NEW


class CopyDataframe(Transformation):
    """Create a copy of the current dataframe."""

    def render(self):
        self.set_title("Copy Dataframe")
        self.set_content(self.new_df_name_input)

    def get_description(self):
        return "Copy Dataframe"

    def get_code(self):
        return f"{DF_NEW} = {DF_OLD}.copy()"
