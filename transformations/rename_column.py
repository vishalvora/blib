# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from bamboolib.helper import Transformation, DF_OLD

import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, DF_NEW

from bamboolib.transformations.base_components import (
    SelectorGroupMixin,
    SelectorMixin,
    SingleColumnSelector,
)
from bamboolib.widgets import Text, Button


class RenameColumnTransformation(Transformation):
    """Rename a single column."""

    def __init__(self, *args, column=None, new_name=None, **kwargs):
        super().__init__(*args, **kwargs)
        if new_name is None:
            new_name = column

        self.column_dropdown = SingleColumnSelector(
            options=list(self.get_df().columns), value=column, width="md"
        )

        # Currently, this is only used from the column menu, so we can focus on the input.
        self.new_name_input = Text(value=new_name, focus_after_init=True, execute=self)

    def render(self):
        self.set_title("Rename column")
        self.set_content(
            widgets.HTML("Rename"),
            self.column_dropdown,
            widgets.HTML("To"),
            self.new_name_input,
        )

    def get_description(self):
        old_name = self.column_dropdown.value
        new_name = self.new_name_input.value
        return f"<b>Rename column</b> '{old_name}' to '{new_name}'"

    def get_code(self):
        old_name = self.column_dropdown.value
        new_name = self.new_name_input.value
        return f"{DF_OLD} = {DF_OLD}.rename(columns={{'{old_name}': '{new_name}'}})"


class RenameColumnQuickAccess(widgets.HBox):
    """An inline rename column widget."""

    def __init__(self, df_manager, column, parent_view):
        super().__init__()
        self.df_manager = df_manager
        self.column = column
        self.parent_view = parent_view

        self.new_name_input = Text(value=column, focus_after_init=True)
        # the on_submit method is specified after the definition of the rename_column

        def rename_column(widget):
            # maybe show error if the column name already exists (in another column OR if the column name is an empty string)
            # maybe this error can be shown by the Transformation?
            if self.new_name_input.value != column:
                rename = RenameColumnTransformation(
                    self.df_manager, column=column, new_name=self.new_name_input.value
                )
                rename.outlet = self.parent_view.outlet
                rename.execute()

        self.new_name_input.on_submit(rename_column)

        button = Button(description="Rename", on_click=rename_column)

        self.children = [self.new_name_input, button]


class RenameEntry(SelectorMixin, widgets.HBox):
    """Manages a (<old_column_name>, <new_column_name>) pair."""

    def __init__(self, column_options, **kwargs):
        super().__init__(**kwargs)

        self.column_dropdown = SingleColumnSelector(
            options=column_options,
            set_soft_value=True,
            focus_after_init=True,
            width="sm",
        )

        self.new_name = Text(
            value=self.column_dropdown.value, execute=self.selector_group.transformation
        )

        def adjust_new_name(dropdown):
            self.new_name.value = dropdown.value

        self.column_dropdown.on_change(adjust_new_name)

        self.children = [
            self.column_dropdown,
            widgets.HTML("&nbsp;to&nbsp;"),
            self.new_name,
            self.delete_selector_button,
        ]

    def test_set_rename(self, old_column_name, new_column_name):
        self.column_dropdown.value = old_column_name
        self.new_name.value = new_column_name


class RenameSection(SelectorGroupMixin, widgets.VBox):
    """Manages a group of `RenameEntry`s."""

    def __init__(self, transformation, df):
        super().__init__()
        self.df = df
        self.transformation = transformation

        self.init_selector_group("add column")

        self.children = [self.selector_group, self.add_selector_button]

    def create_selector(self, show_delete_button=None, **kwargs):
        return RenameEntry(
            list(self.df.columns),
            selector_group=self,
            show_delete_button=show_delete_button,
        )

    def get_rename_dict(self):
        return {
            selector.column_dropdown.value: selector.new_name.value
            for selector in self.get_selectors()
        }


class RenameMultipleColumnsTransformation(Transformation):
    """Rename one or more columns."""

    def __init__(self, *args, column=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.rename_section = RenameSection(self, self.get_df())

    def render(self):
        self.set_title("Rename column(s)")
        self.set_content(self.rename_section, self.rename_df_group)

    def get_description(self):
        rename_dict = self.rename_section.get_rename_dict()
        return (
            "<b>Rename column</b>"
            if len(rename_dict) <= 1
            else "<b>Rename multiple columns</b>"
        )

    def get_code(self):
        return f"{DF_NEW} = {DF_OLD}.rename(columns={self.rename_section.get_rename_dict()})"

    def test_set_rename(self, old_column_name, new_column_name):
        self.rename_section.get_selectors()[-1].test_set_rename(
            old_column_name, new_column_name
        )
