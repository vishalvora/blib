# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

# A customer called it "rearrange columns"

import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, DF_NEW
from bamboolib.helper import string_to_code

from bamboolib.widgets.selectize import Multiselect, Singleselect

START_OF_DATAFRAME = "Start of dataframe"
END_OF_DATAFRAME = "End of dataframe"
BEFORE_SELECTED_COLUMN = "Before the column"
AFTER_SELECTED_COLUMN = "After the column"

CODE_TYPE_DISCRETE = "Explicit - list columns by name"
CODE_TYPE_ABSTRACT = "Abstract - use list comprehension"


class PositionSelector(widgets.VBox):
    """Handles the position of where to move column(s) in the dataframe."""

    def __init__(self, df):
        super().__init__()
        self.df = df

        self.type_dropdown = Singleselect(
            options=[
                START_OF_DATAFRAME,
                END_OF_DATAFRAME,
                AFTER_SELECTED_COLUMN,
                BEFORE_SELECTED_COLUMN,
            ],
            placeholder="Choose position",
            set_soft_value=True,
            width="md",
            on_change=self.update_layout,
        )

        self.column_box = widgets.HBox([])

        self.children = [self.type_dropdown, self.column_box]
        self.create_column_dropdown()

    def create_column_dropdown(self):
        self.column_dropdown = Singleselect(
            options=list(self.df.columns),
            placeholder="Choose column",
            focus_after_init=True,
            set_soft_value=True,
            width="md",
        )

    def update_layout(self, *args, **kwargs):
        if self.type_dropdown.value in [AFTER_SELECTED_COLUMN, BEFORE_SELECTED_COLUMN]:
            # column_dropdown is created again in order to use the focus_after_init effect
            self.create_column_dropdown()
            self.column_box.children = [self.column_dropdown]
        else:
            self.column_box.children = []

    def get_column(self):
        return self.column_dropdown.value


class MoveColumns(Transformation):
    """
    Change the order of one or multiple columns e.g. to the start/end of the dataframe or before/after
    another column.
    """

    def __init__(self, *args, column=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.columns_selector = Multiselect(
            options=list(self.get_df().columns),
            placeholder="Choose column(s)",
            value=[column],
            focus_after_init=True,
            width="lg",
        )

        if len(self.get_df().columns) < 30:
            options = [CODE_TYPE_DISCRETE, CODE_TYPE_ABSTRACT]
        else:
            # When we have a lot of columns, it makes sense to use list comprehension.
            options = [CODE_TYPE_ABSTRACT, CODE_TYPE_DISCRETE]

        self.code_type = Singleselect(
            options=options, placeholder="Choose type", set_soft_value=True, width="lg"
        )

        self.position_selector = PositionSelector(self.get_df())

    def render(self):
        self.set_title("Change column order")
        self.set_content(
            widgets.HTML("Move the columns"),
            self.columns_selector,
            widgets.HTML("to the position"),
            self.position_selector,
            self.spacer,
            widgets.HTML("Code type"),
            self.code_type,
            self.rename_df_group,
        )

    def get_description(self):
        return f"<b>Rearranged the order of the columns</b>"

    def get_discrete_code(self):
        """
        Get the discrete version of the code, i.e. listing all columns by their name
        (the ones we move AND the the rest).
        """
        type_ = self.position_selector.type_dropdown.value

        old_columns = [
            x for x in self.get_df().columns if x not in self.columns_selector.value
        ]
        if type_ == START_OF_DATAFRAME:
            code = f"{DF_NEW} = {DF_OLD}[{self.columns_selector.value} + {old_columns}]"
        elif type_ == END_OF_DATAFRAME:
            code = f"{DF_NEW} = {DF_OLD}[{old_columns} + {self.columns_selector.value}]"
        else:
            insert_column = self.position_selector.get_column()
            if type_ == BEFORE_SELECTED_COLUMN:
                index_offset = 0
            else:  # AFTER_SELECTED_COLUMN
                index_offset = 1
            insert_index = old_columns.index(insert_column) + index_offset
            code = f"{DF_NEW} = {DF_OLD}[{old_columns[:insert_index]} + {self.columns_selector.value} + {old_columns[insert_index:]}]"
        return code

    def get_abstract_code(self):
        """Get the abstract version of the code, i.e. using list comprehension."""
        type_ = self.position_selector.type_dropdown.value

        old_columns_code = (
            f"[x for x in {DF_OLD}.columns if x not in {self.columns_selector.value}]"
        )
        if type_ == START_OF_DATAFRAME:
            code = f"{DF_NEW} = {DF_OLD}[{self.columns_selector.value} + {old_columns_code}]"
        elif type_ == END_OF_DATAFRAME:
            code = f"{DF_NEW} = {DF_OLD}[{old_columns_code} + {self.columns_selector.value}]"
        else:
            if type_ == BEFORE_SELECTED_COLUMN:
                index_offset = ""  # no offset
            else:  # AFTER_SELECTED_COLUMN
                index_offset = " + 1"
            insert_column = self.position_selector.get_column()

            code = f"""old_columns = {old_columns_code}
insert_index = old_columns.index({string_to_code(insert_column)}){index_offset}
{DF_NEW} = {DF_OLD}[old_columns[:insert_index] + {self.columns_selector.value} + old_columns[insert_index:]]"""
        return code

    def get_code(self):
        if self.code_type.value == CODE_TYPE_DISCRETE:
            code = self.get_discrete_code()
        else:  # CODE_TYPE_ABSTRACT
            code = self.get_abstract_code()

        return code
