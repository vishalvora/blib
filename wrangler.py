# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import time

import pandas as pd
import ipywidgets as widgets

from bamboolib._authorization import auth
from bamboolib.helper import (
    QUALTRICS_SURVEY_LINK_HREF,
    notification,
    collapsible_notification,
    FullParentModal,
    SideWindow,
    Window,
    Viewable,
    TabViewable,
    TabSection,
    log_action,
    log_databricks_funnel_event,
    VSpace,
    get_dataframe_variable_names,
)
from bamboolib.config import get_option
from bamboolib.grid import show_grid

from bamboolib.df_manager import DfManager


from bamboolib.transformations import (
    BinColumn,
    CleanColumnNames,
    Concat,
    ColumnFormulaTransformation,
    DatetimeAttributesTransformer,
    DropNaTransformation,
    DropDuplicatesTransformer,
    DtypeTransformer,
    ToIntegerTransformer,
    ToInteger32Transformer,
    ToInteger16Transformer,
    ToInteger8Transformer,
    ToUnsignedIntegerTransformer,
    ToUnsignedInteger32Transformer,
    ToUnsignedInteger16Transformer,
    ToUnsignedInteger8Transformer,
    ToFloatTransformer,
    ToFloat32Transformer,
    ToFloat16Transformer,
    ToBoolTransformer,
    ToCategoryTransformer,
    ToStringTransformer,
    ToObjectTransformer,
    ToDatetimeTransformer,
    ToTimedeltaTransformer,
    FilterTransformer,
    GroupbyWithMultiselect,
    GroupbyWithRename,
    JoinTransformation,
    LabelEncoder,
    CopyDataframe,
    CopyColumn,
    MeltTransformation,
    MoveColumns,
    OneHotEncoderTransformation,
    PivotTransformation,
    RenameMultipleColumnsTransformation,
    ReplaceMissingValues,
    ReplaceValueTransformation,
    ChangeDatetimeFrequency,
    SelectColumns,
    SetValuesTransformation,
    SortTransformer,
)

from bamboolib.widget_combinations import TempColumnsSelector

from bamboolib.views.df_visualization import DfVisualization
from bamboolib.views import PivotTable, RequestFeature
from bamboolib.views.suggest_string_manipulation import SuggestStringManipulation

from bamboolib.views.plot_creator import PlotCreator

from bamboolib.plugins import TransformationPlugin, ViewPlugin
import bamboolib.transformation_plugins  # implicitly adds plugins to search

from bamboolib.widgets import Multiselect, FocusPoint, Button, CopyButton, CodeOutput

from bamboolib.viz import ColumnSummary

from bamboolib.version import maybe_show_new_version_notification

from bamboolib.config import set_option


MAX_PREVIEW_COLUMNS = 100

SHOW_CODE = True


class Wrangler(TabViewable):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.df_manager.register_wrangler(self)

    def render(self):
        self.grid = show_grid()
        self.grid.set_bamboo_callback_handler(self.create_bamboo_callback_handler())

        self.shape_label = widgets.Label()
        self.shape_label.add_class("bamboolib-element-next-to-selectize")
        self.shape_label.add_class("bamboolib-wrangler-shape-label")

        self.wrangle_window = Window(
            show_header=False, css_classes=["bamboolib-window-without-border"]
        )
        self.full_parent_modal_outlet = FullParentModal()
        self.side_window_outlet = SideWindow(on_hide=self.tab_got_selected)

        def on_hide_visualization_window():
            self.wrangle_window.show()
            self.grid.refresh_grid()
            self._focus_the_focus_point()

        self.visualization_window = Window(
            on_show=lambda: self.wrangle_window.hide(),
            on_hide=on_hide_visualization_window,
        )

        self.search_options = self.get_search_options()

        self.action_error_outlet = widgets.HBox()

        def show_search_result(search_widget):
            try:
                if len(search_widget.value) > 0:
                    viewable = search_widget.value[0]
                    outlet = [
                        option.get("outlet", self.side_window_outlet)
                        for option in self.search_options
                        if option["value"] == viewable
                    ][0]
                    viewable(
                        df_manager=self.df_manager, parent_tabs=self.parent_tabs
                    ).render_in(outlet)
                    search_widget.value = []
                    log_databricks_funnel_event("Search result - click")
            except:
                import traceback
                output = collapsible_notification("Error", body=traceback.format_exc(), collapsed=True, type="error")
                self.action_error_outlet.children = [output]

        self.search = Multiselect(
            options=[
                {
                    "label": item["label"],
                    "value": item["value"],
                    "description": item["description"],
                }
                for item in self.search_options
            ],
            placeholder="Search actions",
            select_on_tab=False,  # otherwise, the user cannot tab to the other buttons
            width="xl",
            on_change=show_search_result,
        )

        self.explore_df_button = self.make_button(
            "Explore DataFrame",
            DfVisualization,
            icon="map-o",
            outlet=self.parent_tabs,
        )

        self.plot_button = self.make_button(
            "Create plot", PlotCreator, icon="bar-chart", outlet=self.parent_tabs
        )

        self.focus_point = FocusPoint()

        buttons = widgets.HBox(
            [
                widgets.HTML(" or "),
                self.plot_button,
                widgets.HTML(" or "),
                self.explore_df_button,
            ]
        )
        buttons.add_class("bamboolib-element-next-to-selectize")
        self.action_line = widgets.HBox([self.focus_point, self.search, buttons])
        self.action_line.add_class("bamboolib-overflow-visible")

        self.history_line = HistoryLine(self)
        self.code_export = CodeExport(self)

        # Good for testing a new feature quickly.
        # self.test = Button(
        #     description="test",
        #     on_click=lambda _: ColumnSummary(
        #         column="Pclass",
        #         df_manager=self.df_manager,
        #         parent_tabs=self.parent_tabs,
        #     ).render_in(self.parent_tabs),
        # )

        self.insight_outlet = widgets.VBox()

        self.dimensions_line = widgets.HBox([])
        self.dimensions_line.add_class("bamboolib-overflow-visible")

        self.wrangle_window.set_content(
            widgets.HBox(
                [
                    widgets.VBox(
                        [
                            auth.get_license_user_info(),
                            maybe_show_new_version_notification(),
                            self.history_line,
                            self.insight_outlet,
                            VSpace("xxxl"),
                            # self.test,
                            self.action_line,
                            self.action_error_outlet,
                            VSpace("xxl"),
                            self.dimensions_line,
                            self.grid,
                            VSpace("xxl"),
                            self.code_export,
                            self.full_parent_modal_outlet,  # full screen
                        ]
                    ).add_class("bamboolib-width-100pct"),
                    self.side_window_outlet,  # half screen
                ]
            )
        )
        self.wrangle_window.show()

        self.df_did_change()
        self.set_title("Data")
        self.set_content(self.wrangle_window, self.visualization_window)

    def get_search_options(self):
        """Get all options that are displayed in the main search input field."""
        options = (
            [
                {
                    "label": "Select or drop columns",
                    "description": "Select/delete one or multiple columns",
                    "value": SelectColumns,
                },
                {
                    "label": "Filter rows",
                    "description": "Select/delete rows based on a condition",
                    "value": FilterTransformer,
                },
                {
                    "label": "Sort rows",
                    "description": "Sort rows beased on values in one or more columns",
                    "value": SortTransformer,
                },
                {
                    "label": "Group by and aggregate (default)",
                    "description": "Group rows by columns and calculate MULTIPLE aggregations (no renaming possible)",
                    "value": GroupbyWithMultiselect,
                },
                {
                    "label": "Group by and aggregate (with renaming)",
                    "description": "Group rows by columns and calculate a SINGLE aggregation that can be named",
                    "value": GroupbyWithRename,
                },
                {
                    "label": "Join / Merge dataframes",
                    "description": "Add columns from another dataframe based on keys",
                    "value": JoinTransformation,
                },
                {
                    "label": "Change column data type",
                    "description": "Change the data type of a single column",
                    "value": DtypeTransformer,
                },
                {
                    "label": "Clean column names",
                    "description": "Cleans the column names (make them lower case / snake_case, remove punctuation, etc.)",
                    "value": CleanColumnNames,
                },
                {
                    "label": ToIntegerTransformer.modal_title,
                    "description": "Change the data type of a single colum to integer",
                    "value": ToIntegerTransformer,
                },
                {
                    "label": ToUnsignedIntegerTransformer.modal_title,
                    "description": "Change the data type of a single colum to unsigned integer",
                    "value": ToUnsignedIntegerTransformer,
                },
                {
                    "label": ToFloatTransformer.modal_title,
                    "description": "Change the data type of a single colum to float",
                    "value": ToFloatTransformer,
                },
                {
                    "label": ToStringTransformer.modal_title,
                    "description": "Change the data type of a single colum to text/string",
                    "value": ToStringTransformer,
                },
                {
                    "label": ToObjectTransformer.modal_title,
                    "description": "Change the data type of a single colum to dtype Object",
                    "value": ToObjectTransformer,
                },
                {
                    "label": ToDatetimeTransformer.modal_title,
                    "description": "Change the data type of a single colum to datetime",
                    "value": ToDatetimeTransformer,
                },
                {
                    "label": ToTimedeltaTransformer.modal_title,
                    "description": "Change the data type of a single colum to timedelta",
                    "value": ToTimedeltaTransformer,
                },
                {
                    "label": ToCategoryTransformer.modal_title,
                    "description": "Change the data type of a single colum to category",
                    "value": ToCategoryTransformer,
                },
                {
                    "label": ToBoolTransformer.modal_title,
                    "description": "Change the data type of a single colum to boolean",
                    "value": ToBoolTransformer,
                },
                {
                    "label": "Rename columns",
                    "description": "Rename one or more columns",
                    "value": RenameMultipleColumnsTransformation,
                },
                {
                    "label": "Find and replace (global)",
                    "description": "Substitute *exact* cell values in one or all columns",
                    "value": ReplaceValueTransformation,
                },
                {
                    "label": "Conditional replace (if else logic)",
                    "value": SetValuesTransformation,
                    "description": "Update column values based on boolean condition",
                },
                {
                    "label": "Change datetime frequency",
                    "value": ChangeDatetimeFrequency,
                    "description": "EITHER expand timeseries column and fill it with values OR group by and calculate aggregations (also known as: resample or expand grid). E.g. based on year, quarter, month, week, weekday, day, hour, minute, second calculate forward fill, backward fill, interpolation and more.",
                },
                {
                    "label": "Extract datetime property",
                    "value": DatetimeAttributesTransformer,
                    "description": "Create new column and get properties like year, quarter, month, week, weekday, day, hour, minute, second or timestamp from a datetime column",
                },
                {
                    "label": "Move column(s)",
                    "value": MoveColumns,
                    "description": "Change the order of one or multiple columns e.g. to the start/end of the dataframe or before/after another column.",
                },
                {
                    "label": "Bin column",
                    "value": BinColumn,
                    "description": "Form discrete categories from a numeric column e.g. fixed number of bins, fixed intervals, named intervals or quantile binning",
                },
                {
                    "label": "Concatenate",
                    "value": Concat,
                    "description": "Concatenate (union / stack) multiple dataframes vertically or horizontally",
                },
                {
                    "label": "Pivot/Spread",
                    "value": PivotTransformation,
                    "description": "Reshape the dataframe from long to wide format",
                },
                {
                    "label": "Unpivot/Melt",
                    "value": MeltTransformation,
                    "description": "Reshape the dataframe from wide to long format",
                },
                {
                    "label": "OneHotEncoder",
                    "value": OneHotEncoderTransformation,
                    "description": "Create a column for each unique value indicating its presence or absence",
                },
                {
                    "label": "LabelEncoder",
                    "value": LabelEncoder,
                    "description": "Turn a categoric column into numeric integer codes (factorize)",
                },
                {
                    "label": "Copy Dataframe",
                    "value": CopyDataframe,
                    "description": "Create a copy of an existing dataframe",
                },
                {
                    "label": "Copy Column",
                    "value": CopyColumn,
                    "description": "Create a copy of an existing column",
                },
                {
                    "label": "Drop missing values",
                    "value": DropNaTransformation,
                    "description": "Remove rows with missing values (NAs) in one or more columns",
                },
                {
                    "label": "Drop/Remove duplicates",
                    "value": DropDuplicatesTransformer,
                    "description": "Remove duplicated rows in a dataframe, i.e. only keep distinct rows",
                },
                {
                    "label": "Find and replace missing values",
                    "value": ReplaceMissingValues,
                    "description": "Fill / Impute missing values (NAs) in one or more columns",
                },
                {
                    "label": "New column formula",
                    "value": ColumnFormulaTransformation,
                    "description": "Create a new column from a formula e.g. math expression",
                },
            ]
            + self.get_plugins()
            + [
                {
                    "label": "Explore DataFrame",
                    "value": DfVisualization,
                    "description": "Best practice analyses for data exploration and visualization",
                    "outlet": self.parent_tabs,
                },
                {
                    "label": "Plot creator",
                    "value": PlotCreator,
                    "description": "Visualize your data by creating custom plotly figures",
                    "outlet": self.parent_tabs,
                },
                {
                    "label": "Pivot table",
                    "value": PivotTable,
                    "description": "Nothing more to say...",
                    "outlet": self.parent_tabs,
                },
                {
                    # Important: if you change this label, then you also need to adjust the Javascript code
                    # because the label is used to dynamically adjust the search results
                    "label": "Not found what you're looking for?",
                    "value": RequestFeature,
                    "description": "Let us know so that we can build it for you!",
                    # always open in side_window_outlet regardless if the class is a ViewPlugin or TransformationPlugin or so
                    "outlet": self.side_window_outlet,
                },
            ]
        )
        hidden_options = get_option("plugins.hide_search_options")
        filtered_options = [
            item for item in options if item["value"].__name__ not in hidden_options
        ]
        return filtered_options

    def get_plugins(self):
        """Get the plugins to add them to the search bar options."""
        plugin_options = []

        for plugin in TransformationPlugin.get_plugins():
            try:
                plugin_options.append(
                    {
                        "label": plugin.name,
                        "value": plugin,
                        "description": plugin.description,
                    }
                )
            except:
                pass

        for plugin in ViewPlugin.get_plugins():
            try:
                plugin_options.append(
                    {
                        "label": plugin.name,
                        "value": plugin,
                        "description": plugin.description,
                        "outlet": self.parent_tabs,
                    }
                )
            except:
                pass
        return plugin_options

    def make_button(
        self, description, viewable, icon="", outlet=None, style="secondary"
    ):
        """Helper functions to create a Button whose `viewable` will be rendered in `outlet`."""
        if outlet is None:
            outlet = self.side_window_outlet

        def on_click(button):
            viewable(
                df_manager=self.df_manager, parent_tabs=self.parent_tabs
            ).render_in(outlet),
            log_databricks_funnel_event(
                f"{description} - click"
            )  # Create plot and Explore DataFrame

        return Button(
            description=description,
            style=style,
            icon=icon,
            on_click=on_click,
        )

    def create_bamboo_callback_handler(self):
        """Create bamboolib specific callbacks."""

        def bamboo_callback_handler(message):
            if message["type"] == "bam_grid_rendered":
                pass
                self.df_manager.update_live_code_export()

            if message["type"] == "bam_send_command_guid":
                self.df_manager.set_command_guid(message["command_guid"])
                self.grid.send(
                    {
                        "type": "bam_request_initial_user_code",
                        "command_guid": message["command_guid"],
                    }
                )

            if message["type"] == "bam_initial_user_code":
                self.df_manager.set_initial_user_code(message["initial_user_code"])

            if message["type"] == "bam_rename_column":
                log_action("general", "DfGrid", "click column name")
                column = message["field"]

                ColumnSummary(
                    column=column,
                    df_manager=self.df_manager,
                    parent_tabs=self.parent_tabs,
                ).render_in(self.parent_tabs)
                log_databricks_funnel_event("Column name - click")

            if message["type"] == "bam_change_dtype":
                log_action("general", "DfGrid", "click column dtype")
                column = message["field"]
                DtypeTransformer(df_manager=self.df_manager, column=column).add_to(
                    self.side_window_outlet
                )
                log_databricks_funnel_event("Column dtype - click")

            if message["type"] == "bam_cell_text_selection":
                # we need to subtract the index
                column_index = int(message["column_index"]) - 1
                selected_text = message["selected_text"]

                df = self.df_manager.get_current_df()
                column_name = df.columns[column_index]
                column_is_dtype_object = df[column_name].dtype.kind == "O"

                if column_is_dtype_object:
                    # log_action("general", "DfGrid", "select text")
                    SuggestStringManipulation(
                        self.side_window_outlet,
                        column_name,
                        selected_text,
                        df_manager=self.df_manager,
                    ).add_to(self.side_window_outlet)
                    log_databricks_funnel_event("Grid cell - select text")

        return bamboo_callback_handler

    def _rerender_dimensions_line(self):
        """Re-render the line displaying our dataframes dimensions."""
        rows, columns = self.df_manager.get_current_df().shape
        self.shape_label.value = f"{rows:,} rows × {columns:,} columns - preview"

        df = self.df_manager.get_current_df()
        too_many_columns = len(df.columns) > MAX_PREVIEW_COLUMNS
        selection = self.df_manager.get_preview_columns_selection()
        self.preview_columns = TempColumnsSelector(
            df=df,
            selection=selection,
            show_all_columns=not too_many_columns,
            show_first_and_last=too_many_columns,
            width="sm",
            multi_select_width="xl",
        )
        update_button = Button(
            icon="refresh",
            on_click=lambda _: self._update_preview_columns_selection(),
        )
        update_button.add_class("bamboolib-element-next-to-selectize")

        self.dimensions_line.children = [
            self.shape_label,
            self.preview_columns,
            update_button,
        ]

    def _update_preview_columns_selection(self):
        self.df_manager.set_preview_columns_selection(
            self.preview_columns.get_selection()
        )
        self._rerender_grid()

    def _rerender_grid(self):
        """Re-render bamboolib grid widget."""
        self.grid.update_df(
            df=self.df_manager.get_current_df(),
            df_column_indices=self.preview_columns.value,
        )

    def _rerender_insight(self):
        """Re-render transformation insight."""
        if len(self.df_manager.transformations) >= 1:
            insight = self.df_manager.transformations[
                -1
            ]._bam_transformation_insight_outlet
            self.insight_outlet.children = [insight]
        else:
            self.insight_outlet.children = []

    def df_did_change(self):
        self.history_line.render()
        self.code_export.update()

        # _rerender_dimensions_line needs to happen before _rerender_grid
        self._rerender_dimensions_line()
        self._rerender_grid()
        self._rerender_insight()
        self.focus_point.focus()

    def tab_got_selected(self):
        """
        Does something when this tab got selected. Note that Wrangler is a TabViewable,
        so when the user e.g. reads in data from within bamboolib, the wrangler view will be
        rendered in a new tab.
        """
        self.grid.refresh_grid()
        self._focus_the_focus_point()

    def _focus_the_focus_point(self):
        """
        This focuses the bamboolib UI so that e.g. a user can enter the search field via hitting the
        tab key.
        """
        # The sleep makes sure that the focus_point gets focused
        # ... in the case when the ui is shown directly after executing a cell and
        #     rendering is a bit slow.
        time.sleep(0.2)
        self.focus_point.focus()

    def display_transformation(self, transformation):
        """Display a transformation when the user calls it from the search input."""
        transformation.render_in(self.side_window_outlet)


class CodeExport(widgets.VBox):
    def __init__(self, wrangler):
        super().__init__()
        self.wrangler = wrangler
        self.df_manager = wrangler.df_manager

        self.copy_button = CopyButton(copy_string="", style="primary")

        def toggle_hide_or_show(button):
            global SHOW_CODE
            SHOW_CODE = not SHOW_CODE
            self.update()

        self.hide_or_show_button = Button(
            description="",
            on_click=toggle_hide_or_show,
        )

        self.buttons = widgets.HBox([self.copy_button, self.hide_or_show_button])
        self.code_outlet = widgets.VBox()
        self.children = [self.buttons, self.code_outlet]

        self.update()

    def update(self):
        self.hide_or_show_button.description = "Hide code" if SHOW_CODE else "Show code"
        self.hide_or_show_button.icon = "chevron-up" if SHOW_CODE else "chevron-down"

        if SHOW_CODE:
            code_string = self.df_manager.get_setup_and_transformations_code()
            if code_string == "":
                hint = "Currently, there is no code to export. Please add some transformations"
                to_be_copied = hint
                content = widgets.HTML(hint)
            else:
                to_be_copied = code_string
                content = CodeOutput(code=code_string)
            self.copy_button.copy_string = to_be_copied
        else:
            content = widgets.HTML()  # show nothing

        self.code_outlet.children = [content]


class HistoryLine(widgets.VBox):
    """Manages all elements above the search bar (undo, redo, history button)."""

    def __init__(self, wrangler):
        super().__init__()
        self.wrangler = wrangler
        self.df_manager = wrangler.df_manager

        self.grid = wrangler.grid

        self.history_view = HistoryView(df_manager=self.df_manager)

        self.qualtrics_survey_link = widgets.HTML(
            # Databricks adds margins to <p> tags
            f"""<p style='text-align:right; margin:0'>
                    <a 
                        href='{QUALTRICS_SURVEY_LINK_HREF}' 
                        target='_blank' rel='noreferrer' 
                        style='color:#08c; text-decoration:none;'
                    >
                        Give feedback
                    </a>
                </p>""",
            layout=widgets.Layout(width="100%"),
        )

        self._setup_layout_elements()
        self.render()
        self.children = [self.header]

    def _setup_layout_elements(self):
        self.show_steps_button = Button(
            description="History", icon="list", layout=widgets.Layout(min_width="100px")
        )
        self.show_steps_button.on_click(
            lambda _: log_action("general", "Wrangler", "click history button")
        )
        self.show_steps_button.on_click(
            lambda button: self.history_view.render_in(self.wrangler.side_window_outlet)
        )
        # import here because otherwise circular dependency
        from bamboolib.views.export_options import ExportOptionsView

        self.export_button = Button(
            description="Export",
            icon="sign-out",
            layout=widgets.Layout(min_width="100px"),
        )
        self.export_button.on_click(
            lambda _: log_action("general", "Wrangler", "click export button")
        )
        self.export_button.on_click(
            lambda button: ExportOptionsView(
                self.wrangler.full_parent_modal_outlet,
                self.wrangler.side_window_outlet,
                df_manager=self.df_manager,
            ).render_in(self.wrangler.side_window_outlet)
        )

        self.live_code_export_checkbox = widgets.Checkbox(
            value=self.df_manager.show_live_code_export, description="Live Code Export"
        )
        self.live_code_export_checkbox.add_class("bamboolib-checkbox")

        self.live_code_export_checkbox.observe(
            lambda _: self._toggle_live_code_export_checkbox(), names="value"
        )

        self.undo_button = Button(
            description="Undo last step",
            icon="undo",
            disabled=True,
            on_click=lambda button: self.df_manager.undo(),
        )
        self.undo_button.on_click(
            lambda _: log_action("general", "HistoryView", "click undo button")
        )

        self.undo_icon_button = Button(
            icon="undo", disabled=True, on_click=lambda button: self.df_manager.undo()
        )
        self.undo_icon_button.on_click(
            lambda _: log_action("general", "Wrangler", "click undo button")
        )

        self.redo_button = Button(
            description="Recover last step",
            icon="repeat",
            disabled=True,
            on_click=lambda button: self.df_manager.redo(),
        )
        self.redo_button.on_click(
            lambda _: log_action("general", "HistoryView", "click redo button")
        )

        self.redo_icon_button = Button(
            icon="repeat", disabled=True, on_click=lambda button: self.df_manager.redo()
        )
        self.redo_icon_button.on_click(
            lambda _: log_action("general", "Wrangler", "click redo button")
        )

        self.edit_icon_button = Button(
            icon="pencil", disabled=True, on_click=self._open_edit_last_transformation
        )
        self.edit_icon_button.on_click(
            lambda _: log_action("general", "Wrangler", "click edit button")
        )

        self.header = widgets.HBox([])

    def _open_edit_last_transformation(self, *args, **kwargs):
        LAST_LIST_ITEM = -1
        self.df_manager.transformations[LAST_LIST_ITEM].add_to(
            self.wrangler.side_window_outlet
        )

    def _toggle_live_code_export_checkbox(self):
        if self.live_code_export_checkbox.value:
            message = "disable live code export"
        else:
            message = "enable live code export"
        log_action("general", "Wrangler", message)

        set_option("global.show_live_code_export", self.live_code_export_checkbox.value)
        self.df_manager.show_live_code_export = self.live_code_export_checkbox.value
        self.df_manager.update_live_code_export()

    def _update_undo_redo_buttons(self):
        """Either disables or enables the undo/redo button."""
        self.update_undo_buttons()
        self.update_redo_buttons()

    def update_redo_buttons(self):
        if self.df_manager.redo_is_possible():
            self.redo_button.disabled = False
            self.redo_icon_button.disabled = False
        else:
            self.redo_button.disabled = True
            self.redo_icon_button.disabled = True

    def update_undo_buttons(self):
        if self.df_manager.undo_is_possible():
            self.undo_button.disabled = False
            self.undo_icon_button.disabled = False
            self.edit_icon_button.disabled = False
        else:
            self.undo_button.disabled = True
            self.undo_icon_button.disabled = True
            self.edit_icon_button.disabled = True

    def _render_header(self):
        self.header.children = [
            self.edit_icon_button,
            self.undo_icon_button,
            self.redo_icon_button,
            self.show_steps_button,
            self.export_button,
            self.qualtrics_survey_link if auth.is_databricks() else widgets.HTML(),
            # self.live_code_export_checkbox,
        ]

    def render(self):
        self._update_undo_redo_buttons()
        self._render_header()

        self.history_view.update()


class HistoryView(Viewable):
    """Manages the Transformation history view."""

    def render(self):
        history_line = self.df_manager.wrangler.history_line

        buttons = widgets.HBox([history_line.undo_button, history_line.redo_button])
        steps = self.df_manager.render_steps()

        self.set_title(f"Transformations history")
        self.set_content(steps, buttons)


def create_dataframe_ui(df, origin, symbols, df_name):
    """
    Create a Wrangler instance if the user displays a dataframe that has been assigned to a variable.

    If the user does something like:
    df.head()

    We let her know that that doesn't work.
    """
    if df_name is None:
        if origin == "bam.show":
            message = """
<p>bamboolib does not work if the dataframe is not assigned to a variable. <b>Please assign the dataframe to a variable.</b></p>
<br>
<p>For example, maybe you typed something like:</p>
<pre><code>    bam.show(pd.read_csv("titanic.csv"))</code></pre>
<br>
<p>Please write it as follows:</p>
<pre><code>    df = pd.read_csv("titanic.csv")
    bam.show(df)</code></pre>
            """
        elif origin == "ipython_display":
            message = """
<p>bamboolib does not work if the dataframe is not assigned to a variable. <b>Please assign the dataframe to a variable.</b></p>
<br>
<p>For example, maybe you typed something like:</p>
<pre><code>    pd.read_csv("titanic.csv")</code></pre>
<br>
<p>Please write it as follows:</p>
<pre><code>    df = pd.read_csv("titanic.csv")
    df</code></pre>
            """
        return notification(message, type="error")

    df_manager = DfManager(df, symbols=symbols, df_name=df_name)
    tab_section = TabSection(df_manager)
    tab_section.add_tab(
        Wrangler(df_manager=df_manager, parent_tabs=tab_section), closable=False
    )
    return tab_section


def show(df, symbols={}):
    """Show the Wrangler UI to the user."""
    from bamboolib.setup.user_symbols import get_user_symbols

    log_action(category="other", view="JupyterCell", action="bam.show(df)")

    symbols = get_user_symbols()
    possible_df_names = get_dataframe_variable_names(df, symbols)
    df_name = None if len(possible_df_names) == 0 else possible_df_names[0]

    wrangler = create_dataframe_ui(
        df, origin="bam.show", symbols=symbols, df_name=df_name
    )
    bam_enable_nudge = notification(
        "<b>Pro Tip:</b> save the time writing <code>bam.show(df)</code> and just write <code>df</code>. Enable this feature via <code>bam.enable()</code> and disable via <code>bam.disable()</code>"
    )
    return widgets.VBox([bam_enable_nudge, wrangler])
