# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


import ipywidgets as widgets
import ipyslickgrid

import numpy as np
import pandas as pd
import ppscore as pps
import plotly.graph_objs as go

from ipywidgets import interactive
from pandas.api.types import is_numeric_dtype, is_bool_dtype, is_datetime64_any_dtype

from bamboolib.edaviz.base import *
from bamboolib.edaviz.constants import *
from bamboolib.edaviz.plots import *

from bamboolib.helper import (
    return_styled_df_as_widget,
    DF_OLD,
    notification,
    VSpace,
    string_to_code,
)
from bamboolib.config import get_option

from bamboolib.widgets import (
    GlimpseRow,
    GlimpseHeader,
    Singleselect,
    Button,
    TableOutput,
)

from bamboolib.edaviz.interactive_histogram import InteractiveHistogram
from bamboolib.edaviz.timeseries_plot import (
    UnivariateTimeseriesPlot,
    BivariateTimeseriesPlot,
)

# _underscore_functions are not exposed when running from ... import *
from bamboolib.edaviz.utils import (
    _get_bin_settings,
    _user_info_when_one_column_is_id,
    _update_count_figure_data,
    _update_heatmap_figure_data,
    create_bin_slider,
    create_marginal_density_bar_chart,
    create_numeric_heatmap_layout_with_marginal_densities,
    compute_numeric_to_cat_heatmap_data,
    compute_numeric_to_numeric_heatmap_data,
    get_lower_bounds_of_bins,
    heatmap_hovertext,
    link,
    set_zero_to_nan,
    value_counts,
)

from bamboolib.edaviz.data_types import (
    is_dtype_timedelta,
    is_binary,
    is_numeric,
    is_object,
)


SAMPLE_FOR_SCORES = 5000

PREDICTIVE_POWER_ERROR_SCORE = 0  # set to -1 for debugging

EXCLUDE_ID_TYPE = False


def lazy_collection(collection_object, contents, render_first_content, **kwargs):
    """
    Use an ipywidgets collection_object (e.g. Accordion, Tabs) and extend it so that it lazy loads
    its contents.
    """

    initial_contents = []
    loaded_contents = []
    callbacks = []

    for content in contents:
        initial_contents.append(content["content"][0])
        callbacks.append(content["content"][1])
        loaded_contents.append(None)

    def maybe_load_content(index):
        if loaded_contents[index] is None:
            callbacks[index]()
            loaded_contents[index] = True

    collection = collection_object()
    collection.selected_index = None

    def selected_index_change(change):
        maybe_load_content(change["new"])

    collection.observe(selected_index_change, names="selected_index")

    collection.children = initial_contents
    for i, content in enumerate(contents):
        collection.set_title(i, content["title"])
    if render_first_content:
        collection.selected_index = 0
    return collection


def lazy_accordion(contents, **kwargs):
    return lazy_collection(
        widgets.Accordion, contents, render_first_content=False, **kwargs
    )


def lazy_tabs(contents, render_first_content=True, **kwargs):
    return lazy_collection(
        widgets.Tab, contents, render_first_content=render_first_content, **kwargs
    )


@high_level_function
@embeddable_plain_blocking
def overview(df, with_preview=False, target=None, **kwargs):
    """
    Create an overview over a dataset, containing e.g. a glimpse on the data.

    :return: a lazy-loaded version of ipywidgets.Tab
    """

    function_hint_ = get_function_hint(f"bam.plot({DF_OLD})", **kwargs)

    contents = [
        {
            "title": "Glimpse",
            "content": new_lazy_widget_decorator(glimpse, df, **kwargs),
        },
        {
            "title": "Predictor patterns",
            "content": new_lazy_widget_decorator(patterns, df, **kwargs),
        },
        {
            "title": "Correlation Matrix",
            "content": new_lazy_widget_decorator(correlations, df, target, **kwargs),
        },
    ]

    return function_hint_, lazy_tabs(contents, **kwargs)


def missing_values_count(df, series_name, **kwargs):
    """Count the number of missing values for a column in df."""

    valid_values_count = df[series_name].count()
    total_length = df.shape[0]
    n_missing = total_length - valid_values_count
    return n_missing


def percent_of_max(value_list, max_value, **kwargs):
    max_count = max(value_list)
    max_ratio = max_count / max_value
    return int(max_ratio * 100)


def open_univariate_summary_callback(column, df_manager, parent_tabs):
    """
    Create a column summary of column and display it in a new tab in the UI.

    :param df_manager: Our data frame manager.
    :param parent_tabs: object managing the tabs in the UI.
    """

    from bamboolib.viz import ColumnSummary

    # the purpose is to bind the value of column
    # if we just define the lambda inline, the value of column will be resolved to be the last column
    return lambda _: ColumnSummary(
        column=column, df_manager=df_manager, parent_tabs=parent_tabs
    ).render_in(parent_tabs)


class GlimpseTable(AsyncEmbeddable):
    """
    Create a glimpse on a dataset, typically containin column names, data types, number of missings
    and number of unique values.
    """

    def missings(self, df, column):
        total_count = df.shape[0]
        count = df[column].isna().sum()
        percent = (count / total_count) * 100
        return count, percent

    def uniques(self, df, column):
        total_count = df.shape[0]
        count = (
            df[column].nunique()
            if df[column].dtype != "object"
            else df[column].astype(str).nunique()
        )
        percent = (count / total_count) * 100
        return count, percent

    def init_embeddable(
        self, df, df_column_indices, df_manager=None, parent_tabs=None, **kwargs
    ):
        self.add_class("bamboolib-glimpse-table")
        output = []
        rows_dict = {}
        SAMPLE_SIZE = 10_000

        output.append(GlimpseHeader())

        asymptotic_loading = df.shape[0] > SAMPLE_SIZE
        if asymptotic_loading:
            # ~50% faster sampling than pd.DataFrame.sample()
            indices = np.random.RandomState(get_option("global.random_seed")).choice(
                df.shape[0], size=SAMPLE_SIZE
            )
            init_df = df.take(indices)
        else:
            init_df = df

        for column in df_column_indices:
            kwargs = {}
            kwargs["name"] = str(column)
            kwargs["dtype"] = str(init_df[column].dtype)
            kwargs["unique_count"], kwargs["unique_percent"] = self.uniques(
                init_df, column
            )
            kwargs["missings_count"], kwargs["missings_percent"] = self.missings(
                init_df, column
            )
            kwargs["sample_size"] = SAMPLE_SIZE
            kwargs["loading"] = asymptotic_loading
            row = GlimpseRow(**kwargs)
            row.on_click(
                open_univariate_summary_callback(str(column), df_manager, parent_tabs)
            )
            output.append(row)
            rows_dict[str(column)] = row
            self.set_content(*output)

        if asymptotic_loading:
            for column in df_column_indices:
                row = rows_dict[str(column)]
                kwargs = {}
                kwargs["unique_count"], kwargs["unique_percent"] = self.uniques(
                    df, column
                )
                kwargs["missings_count"], kwargs["missings_percent"] = self.missings(
                    df, column
                )
                row.set_unique_and_missings(**kwargs)
                row.loading = False


@high_level_function
@user_exposed_function
@catch_empty_df
@embeddable_with_outlet_async
def glimpse(df, outlet=None, loading=None, **kwargs):
    """
    Top-level function for displaying a glimpse table to the user. Lets user select columns for which she
    wants to see the glimpse table.

    """
    function_hint_ = get_function_hint(f"bam.glimpse({DF_OLD})", **kwargs)

    spacer = VSpace("md")
    shape_ = widgets.HTML(f"<h4>{df.shape[0]:,} rows and {df.shape[1]:,} columns</h4>")
    glimpse_table = ColumnsReducer(
        df=df,
        max_columns=100,
        on_render=lambda df_column_indices: GlimpseTable(
            df, df_column_indices=df_column_indices, **kwargs
        ),
        **kwargs,
    )
    notification_to_user = notification(
        "Click on a row for column details.", type="info"
    )

    outlet.children = [
        function_hint_,
        shape_,
        spacer,
        glimpse_table,
        spacer,
        notification_to_user,
    ]
    return outlet


@high_level_function
@embeddable_plain_async
def preview(df, **kwargs):
    return qgrid_widget(df)


def qgrid_widget(df, show_rows=None, **kwargs):
    """
    Render any given dataset df as a Qgrid widget.
    """
    # set the number of shown rows
    if show_rows is None:
        max_show_rows_ = min(10, len(df))
    else:
        max_show_rows_ = show_rows

    # adjust the show_rows to fix a qgrid bug
    minVisibleRows = max_show_rows_ + 2
    maxVisibleRows = max_show_rows_ + 2

    grid_options = {
        "forceFitColumns": False,
        "editable": True,
        "enableColumnReorder": True,
        "minVisibleRows": minVisibleRows,
        "maxVisibleRows": maxVisibleRows,
    }
    qgrid_widget = ipyslickgrid.show_grid(
        df, show_toolbar=False, grid_options=grid_options
    )
    return qgrid_widget


@high_level_function
@embeddable_with_outlet_async
def missing_values(df, series_name, outlet=None, loading=None, **kwargs):
    """
    Show the subset of df to the user where values in column df[series_name] are missing values.
    """

    # TODO: if all columns have missing values in the same rows, then the subset view will break
    # because it does not show anything eg airquality data set
    # how to fix this:
    # 1) either the subset view can show missing values
    # 2) the subset view is not shown and highlights this problem?

    progress_ = widgets.FloatProgress(value=0.0, min=0.0, max=1.0)
    outlet.children = [progress_, loading]

    rows = missing_values_rows(df, series_name, **kwargs)
    outlet.children = [rows]
    return outlet


def missing_values_rows(df, series_name, **kwargs):
    def percent_string(ratio, **kwargs):
        ratio = ratio * 100.0
        return "{:2.2f}%".format(ratio)  # 0.446789 to 44.68%

    def has_missing_values(df_or_series, series_name=None):
        if series_name is None:
            series = df_or_series
        else:
            series = df_or_series[series_name]
        missing_values = series.isnull().sum()
        return missing_values > 0

    def has_no_missing_values(df_or_series, series_name=None):
        return not has_missing_values(df_or_series, series_name)

    valid_values_count = df[series_name].count()
    total_length = len(df[series_name])
    n_missing = total_length - valid_values_count
    p_missing = n_missing * 1.0 / total_length

    if has_no_missing_values(df[series_name]):
        details = widgets.HTML(f"{series_name} has no missing values!")
    else:
        count = widgets.HTML(
            f"<b>{n_missing}</b> missing values - {percent_string(p_missing)} of all rows are missing"
        )
        preview_df = df[df[series_name].isnull()]
        preview_df = change_df_column_order(preview_df, [series_name])
        preview_widget = preview(preview_df)
        details = widgets.VBox([count, preview_widget])
    return widgets.VBox([details])


@embeddable_with_outlet_blocking
def column_numeric_distribution(
    df, series_name, target=None, outlet=None, loading=None, **kwargs
):
    """Summary statistics and univariate plot for numeric column series_name."""

    final_output = []

    stats_ = numeric_stats_dense(df, series_name)
    hist_ = InteractiveHistogram(df, series_name, **kwargs)

    side_by_side = widgets.HBox([hist_, stats_])
    final_output = [side_by_side]

    outlet.children = final_output
    return outlet


@embeddable_with_outlet_blocking
def column_object_distribution(
    df, series_name, target=None, outlet=None, loading=None, **kwargs
):
    """Categorical univariate summary of column series_name."""

    final_output = []

    categories_count_ = category_count(df[series_name])
    if categories_count_ > 10:
        shown_categories = 10
        header = f"Top {shown_categories} values of column"
    else:
        shown_categories = categories_count_
        header = f"All value counts of column"

    count = df[series_name].count()
    values_df = df[series_name].value_counts(dropna=True).to_frame()
    values_df = values_df.rename(columns={series_name: "Count"})
    values_df = values_df.reset_index().rename(columns={"index": header})
    values_df["%"] = values_df["Count"] * 100.0 / count
    values_df["Cum. count"] = values_df["Count"].cumsum()
    values_df["Cum. %"] = values_df["%"].cumsum()
    styled_values_df = values_df.head(10).style.bar(
        subset=["Count"], color=COLOR_BLUE_LIGHT, align="mid"
    )

    max_count_cumsum_count_width = values_df.iloc[shown_categories - 1, :]["Cum. %"]
    styled_values_df = (
        styled_values_df.bar(
            subset=["Cum. %"],
            width=max_count_cumsum_count_width,
            color=COLOR_BLUE_LIGHT,
            align="mid",
        )
        .format({"%": "{:.1f}", "Cum. %": "{:.1f}"})
        .set_properties(**{"background-color": "white"})
        .hide_index()
    )
    output = return_styled_df_as_widget(styled_values_df)

    final_output = [output]

    if categories_count_ > 10:
        full_preview_outlet = widgets.VBox(
            create_toggle_output(
                f"all value counts",
                new_lazy_widget_decorator(preview, values_df, **kwargs),
            )
        )
        final_output.append(full_preview_outlet)

    outlet.children = final_output
    return outlet


@embeddable_with_outlet_blocking
def generic_column_summary_tabbed(
    df, series_name, summary_function, target=None, outlet=None, loading=None, **kwargs
):
    """Creates extensive summary information of column series_name."""

    tab_contents = []

    is_numeric_column = is_numeric(df[series_name]) and not is_binary(df[series_name])
    is_datetime_column = is_datetime64_any_dtype(df[series_name])
    show_categoric_overview = is_numeric_column or is_datetime_column

    tab_contents.append(
        {
            "title": "Overview",
            "content": new_lazy_widget_decorator(
                summary_function, df, series_name, target=target, **kwargs
            ),
        }
    )

    if show_categoric_overview:
        # add additionally the categoric overview because numeric or datetime data often is also interpreted categorically
        categoric_summary_function = generic_summary(
            column_object_distribution, **kwargs
        )
        tab_contents.append(
            {
                "title": "Categoric overview",
                "content": new_lazy_widget_decorator(
                    categoric_summary_function, df, series_name, target=target, **kwargs
                ),
            }
        )

    if missing_values_count(df, series_name) > 0:
        tab_contents.append(
            {
                "title": "Missing values",
                "content": new_lazy_widget_decorator(
                    missing_values, df, series_name, **kwargs
                ),
            }
        )

    if target and (target != series_name):
        tab_contents.append(
            {
                "title": f"vs Target",
                "content": new_lazy_widget_decorator(
                    compare, df, series_name, target, **kwargs
                ),
            }
        )

    def has_any_datetime_columns(df):
        return number_of_datetime_columns(df) > 0

    def number_of_datetime_columns(df):
        dtypes = df.dtypes.to_frame().reset_index()
        dtypes.columns = ["column", "type"]
        # Don't use .astype("string") below because this might fail sometimes
        dtypes["type"] = dtypes["type"].astype(str)
        dtypes = dtypes.loc[dtypes["type"].str.startswith("datetime", na=False)]
        return dtypes.shape[0]

    if has_any_datetime_columns(df) and not is_datetime_column:
        tab_contents.append(
            {
                "title": "Over time",
                "content": new_lazy_widget_decorator(
                    over_time, df, series_name, **kwargs
                ),
            }
        )

    tab_contents.append(
        {
            "title": "Bivariate plots",
            "content": new_lazy_widget_decorator(
                bivariate_plot, df, series_name, **kwargs
            ),
        }
    )

    if not is_datetime_column:
        tab_contents.append(
            {
                "title": "Predictors",
                "content": new_lazy_widget_decorator(
                    predictors, df, series_name, **kwargs
                ),
            }
        )

    tabs_widget = lazy_tabs(tab_contents)
    outlet.children = [tabs_widget]
    return outlet


@embeddable_with_outlet_blocking
def column_small_summary(df, series_name, outlet=None, loading=None, **kwargs):
    """
    Create a small summary of a column, containing its data type, number of missings, and number of
    unique values.
    """

    def fill_background(data, color="yellow", **kwargs):
        styling = f"background-color: {color}"
        return [styling for cell in range(data.shape[0])]

    final_output = []
    header = widgets.HTML(f'<h4>"{series_name}"</h4>')

    missing_values_column_name = "Missing values"
    uniques_column_name = "Uniques"

    dtype = df[series_name].dtype
    unique_n = len(df[series_name].value_counts(dropna=True))
    missing_count = missing_values_count(df, series_name)
    valid_count = df.shape[0] - missing_count
    summary = (
        pd.Series(
            [dtype, valid_count, unique_n, missing_count],
            ["Pandas dtype", "Valid", uniques_column_name, missing_values_column_name],
        )
        .to_frame()
        .rename(columns={0: f"{series_name}"})
        .T
    )

    styled_summary = (
        summary.style.hide_index()
        .bar(
            subset=[missing_values_column_name],
            color=COLOR_GREEN,
            align="mid",
            width=(100 - percent_of_max([missing_count], df.shape[0])),
        )
        .set_properties(**{"background-color": "white"})
    )
    if missing_count == 0:
        styled_summary.apply(
            fill_background,
            color=COLOR_GREEN,
            axis=1,
            subset=[missing_values_column_name],
        )
    else:
        styled_summary.apply(
            fill_background,
            color=COLOR_RED,
            axis=1,
            subset=[missing_values_column_name],
        )
    styled_summary.bar(
        subset=[uniques_column_name],
        color=COLOR_BLUE_LIGHT,
        align="mid",
        width=(unique_n / valid_count) * 100,
    )
    output = return_styled_df_as_widget(styled_summary)

    final_output = [header, VSpace("sm"), output]

    if missing_count > 0:
        missing_container = widgets.VBox(
            create_toggle_output(
                "missing values",
                new_lazy_widget_decorator(missing_values, df, series_name, **kwargs),
            )
        )
        final_output.append(missing_container)

    outlet.children = final_output
    return outlet


@embeddable_with_outlet_blocking
def column_boolean_distribution(
    df, series_name, target=None, outlet=None, loading=None, **kwargs
):
    """Column distribution for a boolean column."""

    count = df[series_name].count()
    values_df = df[series_name].value_counts(dropna=True).to_frame()
    values_df = values_df.rename(columns={series_name: "Count"})
    values_df = values_df.reset_index().rename(
        columns={"index": f"'{series_name}' value"}
    )
    values_df["%"] = values_df["Count"] * 100.0 / count
    styled_values_df = (
        values_df.style.bar(subset=["Count"], color=COLOR_BLUE_LIGHT, align="mid")
        .set_properties(**{"background-color": "white"})
        .hide_index()
    )
    output = return_styled_df_as_widget(styled_values_df)

    outlet.children = [output]
    return outlet


@embeddable_with_outlet_blocking
def unsupported_dtype_distribution(
    df, series_name, target=None, outlet=None, loading=None, **kwargs
):
    """Captures any data type for which we don't provide a univariate summary yet."""

    data_type = df[series_name].dtype
    final_output = [
        notification(
            f"""Column <b>{series_name}</b> is of data type <b>{data_type}</b>.
            We currently don't support the data type <b>{data_type}</b>. If you'd
            like us to support it, please
            <a href="mailto:bamboolib-feedback+unsupported_dtype_distribution@databricks.com?subject=Support of {data_type}&body=Please add support for {data_type}. For data type {data_type}, I'd like to see [what would you like to see?]">
                send us an email
            </a>.""",
            type="error",
        )
    ]

    outlet.children = final_output
    return outlet


def generic_summary(column_distribution_function, **kwargs):
    """
    Determine what column summary to display, given column_distribution_function and the values in
    a column.

    This function avoids that the user is shown useless information.
    For example, when the column is a constant, it doesn't make sense to show summary statistics.
    A simple prompt like "your column has one single value X" is enough.
    """

    @embeddable_with_outlet_blocking
    def generic_summary(
        df, series_name, target=None, outlet=None, loading=None, **kwargs
    ):
        summary = column_small_summary(df, series_name, **kwargs)
        spacer = VSpace("xxxl")

        class_ = semantic_column_class(df[series_name])

        if class_ == "empty":
            distribution = widgets.HTML(
                "The column is empty - there are no values<br><br>"
            )
        elif class_ == "only_nans":
            distribution = widgets.HTML("There are only missing values<br><br>")
        elif class_ == "constant":
            value = df[series_name].dropna().iloc[0]
            distribution = widgets.HTML(
                f"The column only contains a single, constant value:<br><code>{value}</code><br><br>"
            )
        else:
            distribution = column_distribution_function(
                df, series_name, target=target, **kwargs
            )

        outlet.children = [summary, spacer, distribution]
        return outlet

    return generic_summary


@embeddable_with_outlet_blocking
def numeric_stats_dense(df, series_name, outlet=None, loading=None, **kwargs):
    """Combines summary stats and stats on positive/negative/zero values."""

    dist_stats = TableOutput(numeric_dist_stats_df(df, series_name))
    pos_neg_stats = TableOutput(numeric_pos_neg_stats_df(df, series_name))
    outlet.children = [dist_stats, pos_neg_stats]
    return outlet


def numeric_dist_stats_df(df, series_name, **kwargs):
    """Create a styled table containing summary statistics for column series_name in df."""

    names = ["Min", "Q1", "Median", "Q3", "Max", "Mean", "StdDev"]
    values = [
        df[series_name].min(),
        df[series_name].quantile(0.25),
        df[series_name].median(),
        df[series_name].quantile(0.75),
        df[series_name].max(),
        df[series_name].mean(),
        df[series_name].std(),
    ]
    result_df = (
        pd.Series(values, names)
        .to_frame()
        .reset_index()
        .rename(columns={"index": "", 0: f"Statistics"})
    )
    styled_df = (
        result_df.style.bar(subset=["Statistics"], color=COLOR_BLUE_LIGHT, align="mid")
        .format({"": "<b>{}</b>"})
        .set_properties(**{"background-color": "white"})
        .hide_index()
    )
    return styled_df


def numeric_pos_neg_stats_df(df, series_name, **kwargs):
    """Create a styled table with number of positive, negative, and zero values"""

    zero_count = df[series_name].loc[df[series_name] == 0].count()
    negative_count = df[series_name].loc[df[series_name] < 0].count()
    positive_count = df[series_name].loc[df[series_name] > 0].count()

    names = [f"Positive values", f"Zero values", f"Negative values"]
    values = [positive_count, zero_count, negative_count]
    result_df = (
        pd.Series(values, names)
        .to_frame()
        .reset_index()
        .rename(columns={"index": "", 0: f"Value counts"})
    )
    styled_df = (
        result_df.style.bar(
            subset=["Value counts"], color=COLOR_BLUE_LIGHT, align="mid"
        )
        .format({"": "<b>{}</b>"})
        .set_properties(**{"background-color": "white"})
        .hide_index()
    )
    return styled_df


def category_count(series, **kwargs):
    return series.value_counts().count()


# TODO: do we need this function and all its helpers?
@embeddable_plain_blocking
def column_summary(*args, **kwargs):
    return _column_summary(*args, **kwargs)


@high_level_function
@embeddable_plain_blocking
def _column_summary(*args, **kwargs):
    if isinstance(args[0], pd.DataFrame):
        return df_column_summary(*args, **kwargs)
    if isinstance(args[0], pd.Series):
        return series_column_summary(*args, **kwargs)


@embeddable_plain_blocking
def df_column_summary(*args, **kwargs):
    return column_summary_with_tabs(*args, **kwargs)


def series_column_summary(series, **kwargs):
    df = series.to_frame()
    column = df.columns[0]
    return df_column_summary(df, column, **kwargs)


def columns_do_not_exist(df, columns_list):
    try:
        df[columns_list]
        return False
    except KeyError:
        return True


def columns_missing_error(df, columns_list, context="Error:"):
    for column in columns_list:
        try:
            df[[column]]
        except KeyError as error:
            message = f"<b>{context}</b><br>The column '{column}' does not exist in the dataframe (anymore)."
            return notification(message, type="error")

    raise Exception("Could not create the columns_missing_error")


class column_summary_with_tabs(Embeddable):
    def init_embeddable(self, df, column, target=None, **kwargs):
        if target:
            target_function_hint = f", target='{target}'"
        else:
            target_function_hint = ""
        function_hint_ = get_function_hint(
            f"bam.plot({DF_OLD}, {string_to_code(column)}{target_function_hint})",
            **kwargs,
        )

        if columns_do_not_exist(df, [column]):
            error = columns_missing_error(
                df, [column], "Error when trying to show the Column Summary:"
            )
            self.set_content(error)
            return

        series = df[column]

        if is_binary(series) or is_bool_dtype(series):
            summary_function = generic_summary(column_boolean_distribution, **kwargs)
        elif is_datetime64_any_dtype(series):
            summary_function = generic_summary(datetime_column_distribution, **kwargs)
        elif is_numeric(series):
            summary_function = generic_summary(column_numeric_distribution, **kwargs)
        elif is_object(series) or is_dtype_timedelta(series):
            summary_function = generic_summary(column_object_distribution, **kwargs)
        else:
            summary_function = generic_summary(unsupported_dtype_distribution, **kwargs)

        tabbed_layout = generic_column_summary_tabbed(
            df, column, summary_function, target, **kwargs
        )

        self.set_content(function_hint_, tabbed_layout)


@embeddable_plain_blocking
def datetime_column_distribution(df, series_name, **kwargs):
    def content(df):
        plot = UnivariateTimeseriesPlot(df, series_name, **kwargs)
        return plot

    return RowsSampler(
        df=df, on_render=lambda df: content(df)
    )


@high_level_function
@user_exposed_function
@catch_empty_df
@embeddable_with_outlet_async
def columns(df, target=None, outlet=None, loading=None, **kwargs):
    """
    Top-level function for our entry point into univariate column summaries. Lets the user choose
    which columns he wants to have listed in a list. When clicking on a column name, a univariate
    summary of that column opens.
    """

    if target:
        function_hint_ = get_function_hint(
            f"bam.columns({DF_OLD}, target={string_to_code(target)})", **kwargs
        )
    else:
        function_hint_ = get_function_hint(f"bam.columns({DF_OLD})", **kwargs)

    if target and (target not in df.columns):
        raise Exception(
            f"Target column {target} is not included in the dataframe columns {df.columns}"
        )

    columns_list = ColumnsReducer(
        df=df,
        max_columns=100,
        on_render=lambda df_column_indices: ColumnsList(
            df, df_column_indices=df_column_indices, **kwargs
        ),
        **kwargs,
    )

    outlet.children = [function_hint_, columns_list]
    return outlet


class ColumnsList(AsyncEmbeddable):
    """
    Create a list of buttons, one button for each column. With a click on a button, a summary
    for that column opens up.
    """

    def init_embeddable(
        self,
        df=None,
        df_column_indices=None,
        df_manager=None,
        parent_tabs=None,
        **kwargs,
    ):
        progress_ = widgets.FloatProgress(value=0.0, min=0.0, max=1.0)
        self.set_content(progress_, self.loading)

        column_buttons = []
        for index, column in enumerate(df_column_indices):
            button = Button(
                description=f"show '{column}'",
                icon="external-link",
                on_click=open_univariate_summary_callback(
                    column, df_manager, parent_tabs
                ),
            ).add_class("bamboolib-width-200px")

            column_buttons.append(button)
            progress_.value = index / len(df_column_indices)
            if index % 10 == 9:  # only render every 10 items
                self.set_content(progress_, widgets.VBox(column_buttons))
        self.set_content(widgets.VBox(column_buttons))


@high_level_function
@embeddable_plain_async
def over_time(df, x, **kwargs):
    """
    Display values in column x over time (i.e. create a bivariate plot with column x on the yaxis
    and values of a datetime column on the x-axis) for each datetime column that exists in df.
    """

    if x not in df.columns:
        raise Exception(
            f"Column {x} is not included in the dataframe columns {df.columns}"
        )

    datetime_columns = [
        column for column in df.columns if is_datetime64_any_dtype(df[column])
    ]

    if len(datetime_columns) == 1:
        return plot(df, datetime_columns[0], x, border=False, **kwargs)
    else:
        column_buttons = []
        for column in datetime_columns:
            column_buttons.append(
                widgets.VBox(
                    create_toggle_output(
                        f"{column}",
                        new_lazy_widget_decorator(
                            plot, df, column, x, border=False, **kwargs
                        ),
                    )
                )
            )
        function_hint_ = get_function_hint(
            f"bam.over_time({DF_OLD}, {string_to_code(x)})", **kwargs
        )
        return function_hint_, widgets.VBox(column_buttons)


### RELATIONS START #####################

# This section contains the logic for our plot functions, handling all potential
# "How to plot column A vs B?" cases.
# Examples:
# - when A is numeric, and B is numeric, then we show a scatter and binned heatmap ("hexbin")
# - when A is an ID, then tell the user that no plot makes sense and show the two columns in a table

#################
### special relations  # each only 2 cases because they are handled explicitly
#################

# We still have a weird get_compare_functions logic. If x is "numeric" and y is "id",
# then this will be treated as "id_to_id". For now, I will catch this and we will
# refactor the whole logic later.
@embeddable_plain_blocking
def relation_id_to_id(df, x, y, **kwargs):
    return _relation_any_to_id(df, x, y, **kwargs)


@embeddable_plain_blocking
def relation_id_to_any(df, x, y, **kwargs):
    return _relation_id_to_any(df, x, y, **kwargs)


@embeddable_plain_blocking
def relation_any_to_id(df, x, y, **kwargs):
    return _relation_id_to_any(df, y, x, **kwargs)  # Attention: x and y are swapped


@embeddable_plain_blocking
def relation_constant_to_any(df, x, y, **kwargs):
    return _relation_constant_to_any(df, x, y, **kwargs)


# E.g. bam.plot(df_titanic, "constant", "Age") leads to this case.
@embeddable_plain_blocking
def relation_constant_to_id(df, x, y, **kwargs):
    return _relation_constant_to_any(
        df, y, x, **kwargs
    )  # Attention: x and y are swapped


@embeddable_plain_blocking
def relation_any_to_constant(df, x, y, **kwargs):
    return _relation_constant_to_any(
        df, y, x, **kwargs
    )  # Attention: x and y are swapped


@embeddable_plain_blocking
def relation_empty_to_any(df, x, y, **kwargs):
    return _relation_empty_to_any(df, x, y, **kwargs)


@embeddable_plain_blocking
def relation_any_to_empty(df, x, y, **kwargs):
    return _relation_empty_to_any(df, y, x, **kwargs)  # Attention: x and y are swapped


@embeddable_plain_blocking
def relation_only_nans_to_any(df, x, y, **kwargs):
    return _relation_only_nans_to_any(df, x, y, **kwargs)


@embeddable_plain_blocking
def relation_any_to_only_nans(df, x, y, **kwargs):
    return _relation_only_nans_to_any(
        df, y, x, **kwargs
    )  # Attention: x and y are swapped


#################
### numeric relations
#################
@embeddable_with_outlet_blocking
def relation_numeric_to_numeric(
    df, numeric_a, numeric_b, outlet=None, loading=None, **kwargs
):
    # score variables are in reverse order (target, feature) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, numeric_b, feature=numeric_a)
    outlet.children = [
        header,
        _relation_numeric_to_numeric(df, numeric_a, numeric_b, **kwargs),
    ]
    return outlet


@embeddable_with_outlet_blocking
def relation_numeric_to_cat2(df, numeric, cat2, outlet=None, loading=None, **kwargs):
    # score variables are in reverse order (target, feat) which is opposite to compare order (
    # feat, target)
    header = _model_score_html_statement(df, cat2, feature=numeric)
    outlet.children = [header, _relation_numeric_to_cat2(df, numeric, cat2, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_numeric_to_cat10(df, numeric, cat10, outlet=None, loading=None, **kwargs):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, cat10, feature=numeric)
    outlet.children = [header, _relation_numeric_to_cat10(df, numeric, cat10, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_numeric_to_cat300(
    df, numeric, cat300, outlet=None, loading=None, **kwargs
):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, cat300, feature=numeric)
    outlet.children = [
        header,
        _relation_numeric_to_cat300(df, numeric, cat300, **kwargs),
    ]
    return outlet


@embeddable_plain_blocking
def relation_numeric_to_datetime(df, x, y, **kwargs):
    return _relation_id_to_any(df, x, y, **kwargs)


#################
### cat2 relations
#################
@embeddable_with_outlet_blocking
def relation_cat2_to_numeric(df, cat2, numeric, outlet=None, loading=None, **kwargs):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, numeric, feature=cat2)
    outlet.children = [header, _relation_cat2_to_numeric(df, cat2, numeric, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_cat2_to_cat2(df, cat2_a, cat2_b, outlet=None, loading=None, **kwargs):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, cat2_b, feature=cat2_a)
    outlet.children = [header, _relation_cat2_to_cat2(df, cat2_a, cat2_b, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_cat2_to_cat10(df, cat2, cat10, outlet=None, loading=None, **kwargs):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, cat10, feature=cat2)
    outlet.children = [header, _relation_cat2_to_cat10(df, cat2, cat10, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_cat2_to_cat300(df, cat2, cat300, outlet=None, loading=None, **kwargs):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, cat300, feature=cat2)
    outlet.children = [header, _relation_cat2_to_cat300(df, cat2, cat300, **kwargs)]
    return outlet


@embeddable_plain_blocking
def relation_cat2_to_datetime(df, x, y, **kwargs):
    return _relation_has_no_visualization_yet(df, x, y, **kwargs)


#################
### cat10 relations
#################
@embeddable_with_outlet_blocking
def relation_cat10_to_numeric(df, cat10, numeric, outlet=None, loading=None, **kwargs):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, numeric, feature=cat10)
    outlet.children = [header, _relation_cat10_to_numeric(df, cat10, numeric, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_cat10_to_cat2(df, cat10, cat2, outlet=None, loading=None, **kwargs):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, cat2, feature=cat10)
    outlet.children = [header, _relation_cat10_to_cat2(df, cat10, cat2, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_cat10_to_cat10(df, cat10_a, cat10_b, outlet=None, loading=None, **kwargs):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, cat10_b, feature=cat10_a)
    outlet.children = [header, _relation_cat10_to_cat10(df, cat10_a, cat10_b, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_cat10_to_cat300(df, cat10, cat300, outlet=None, loading=None, **kwargs):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, cat300, feature=cat10)
    outlet.children = [header, _relation_cat10_to_cat300(df, cat10, cat300, **kwargs)]
    return outlet


@embeddable_plain_blocking
def relation_cat10_to_datetime(df, x, y, **kwargs):
    return _relation_has_no_visualization_yet(df, x, y, **kwargs)


#################
### cat300 relations  # Note: cat300 is our label for "a column with too many categories"
#################
@embeddable_with_outlet_blocking
def relation_cat300_to_numeric(
    df, cat300, numeric, outlet=None, loading=None, **kwargs
):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, numeric, feature=cat300)
    outlet.children = [
        header,
        _relation_cat300_to_numeric(df, cat300, numeric, **kwargs),
    ]
    return outlet


@embeddable_with_outlet_blocking
def relation_cat300_to_cat2(df, cat300, cat2, outlet=None, loading=None, **kwargs):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, cat2, feature=cat300)
    outlet.children = [header, _relation_cat300_to_cat2(df, cat300, cat2, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_cat300_to_cat10(df, cat300, cat10, outlet=None, loading=None, **kwargs):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, cat10, feature=cat300)
    outlet.children = [header, _relation_cat300_to_cat10(df, cat300, cat10, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_cat300_to_cat300(
    df, cat300_a, cat300_b, outlet=None, loading=None, **kwargs
):
    # score variables are in reverse order (target, feat) which is opposite to compare order
    # (feat, target)
    header = _model_score_html_statement(df, cat300_b, feature=cat300_a)
    outlet.children = [
        header,
        _relation_cat300_to_cat300(df, cat300_a, cat300_b, **kwargs),
    ]
    return outlet


@embeddable_plain_blocking
def relation_cat300_to_datetime(df, x, y, **kwargs):
    return _relation_has_no_visualization_yet(df, x, y, **kwargs)


######################
### datetime relations
#####################
@embeddable_with_outlet_blocking
def relation_datetime_to_numeric(df, x, y, outlet=None, loading=None, **kwargs):
    outlet.children = [BivariateTimeseriesPlot(df, x, y, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_datetime_to_cat2(df, x, y, outlet=None, loading=None, **kwargs):
    outlet.children = [BivariateTimeseriesPlot(df, x, y, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_datetime_to_cat10(df, x, y, outlet=None, loading=None, **kwargs):
    outlet.children = [BivariateTimeseriesPlot(df, x, y, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_datetime_to_cat300(df, x, y, outlet=None, loading=None, **kwargs):
    outlet.children = [BivariateTimeseriesPlot(df, x, y, **kwargs)]
    return outlet


@embeddable_with_outlet_blocking
def relation_datetime_to_datetime(df, x, y, outlet=None, loading=None, **kwargs):
    outlet.children = [BivariateTimeseriesPlot(df, x, y, **kwargs)]
    return outlet


#################
### relations utilities
#################
@embeddable_with_outlet_blocking
def _relation_id_to_any(df, id_col, any_col, outlet=None, loading=None, **kwargs):
    title = _user_info_when_one_column_is_id(id_col)
    df = change_df_column_order(df, [id_col, any_col])
    outlet.children = [title, preview(df)]
    return outlet


@embeddable_with_outlet_blocking
def _relation_any_to_id(df, any_col, id_col, outlet=None, loading=None, **kwargs):
    title = _user_info_when_one_column_is_id(id_col)
    df = change_df_column_order(df, [id_col, any_col])
    outlet.children = [title, preview(df)]
    return outlet


@embeddable_with_outlet_blocking
def _relation_constant_to_any(
    df, constant_col, any_col, outlet=None, loading=None, **kwargs
):
    title = widgets.HTML(
        f"There are no reasonable visualizations because the column '{constant_col}' only has a single, constant value:<br>{df[constant_col].iloc[0]}<br>"
    )
    outlet.children = [title]
    return outlet


@embeddable_with_outlet_blocking
def _relation_empty_to_any(df, empty_col, any_col, outlet=None, loading=None, **kwargs):
    title = widgets.HTML(
        f"There are no reasonable visualizations because the column '{empty_col}' is empty. It contains no values."
    )
    outlet.children = [title]
    return outlet


@embeddable_with_outlet_blocking
def _relation_only_nans_to_any(
    df, only_nans_col, any_col, outlet=None, loading=None, **kwargs
):
    title = widgets.HTML(
        f"There are no reasonable visualizations because the column '{only_nans_col}' only contains missing values."
    )
    outlet.children = [title]
    return outlet


@embeddable_plain_blocking
def _relation_numeric_to_numeric(df, x, y, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": f"Density plot",
            "content": new_lazy_widget_decorator(
                hexbin, df, x, y, kind="hex", **kwargs
            ),
        }
    )
    tab_contents.append(
        {
            "title": f"Predictive Power Plot",
            "content": new_lazy_widget_decorator(
                numeric_to_numeric_ppplot, df, x, y, **kwargs
            ),
        }
    )
    tab_contents.append(
        {
            "title": f"Scatter",
            "content": new_lazy_widget_decorator(scatter, df, x, y, **kwargs),
        }
    )
    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def _relation_has_no_visualization_yet(df, x, y, **kwargs):
    message = (
        f"So far, we don't provide a visualization of '{x}' and '{y}' yet. "
        "If you need this kind of visualization, please contact us via bamboolib-feedback@databricks.com"
    )
    return notification(message, type="info")


@embeddable_plain_blocking
def _relation_cat2_to_numeric(df, x, y, **kwargs):
    # Don't add violin plot here as it's slow on large datasets
    tab_contents = []
    tab_contents.append(
        {
            "title": f"Box Plot",
            "content": new_lazy_widget_decorator(boxplot, df, x, y, **kwargs),
        }
    )
    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def _relation_numeric_to_cat10(df, x, y, **kwargs):
    tab_contents = []
    # We removed ppplot as it's too complex for the user to understand
    tab_contents.append(
        {
            "title": f"Stacked Histogram",
            "content": new_lazy_widget_decorator(stacked_histogram, df, x, y, **kwargs),
        }
    )
    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def _relation_numeric_to_cat2(df, x, y, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": f"Stacked Histogram",
            "content": new_lazy_widget_decorator(stacked_histogram, df, x, y, **kwargs),
        }
    )
    tab_contents.append(
        {
            "title": f"Predictive Power Plot",
            "content": new_lazy_widget_decorator(
                numeric_to_cat2_ppplot, df, x, y, **kwargs
            ),
        }
    )
    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def _relation_cat10_to_numeric(df, x, y, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": f"Boxplot",
            "content": new_lazy_widget_decorator(boxplot, df, x, y, **kwargs),
        }
    )
    return lazy_tabs(tab_contents)


### RELATIONS END #####################


@embeddable_plain_blocking
def hexbin(df, x, y, **kwargs):
    """
    Create kind of an interactive hexbin plot widget with marginal densities, where bins for x and y
    can be changed by the user.
    """

    Z_HOVER_LABEL = "Count"

    df_notnull = df[[x, y]].dropna()

    n_bins = DEFAULT_N_BINS
    (
        x_bins,
        x_counts,
        y_bins,
        y_counts,
        heatmap_matrix,
    ) = compute_numeric_to_numeric_heatmap_data(
        df_notnull, x, y, [n_bins, n_bins], frequencies=False
    )
    x_heatmap, y_heatmap = (
        get_lower_bounds_of_bins(x_bins),
        get_lower_bounds_of_bins(y_bins),
    )
    z_heatmap = heatmap_matrix

    hovertext = heatmap_hovertext(x_bins, y_bins, z_heatmap, x, y, Z_HOVER_LABEL)
    z_heatmap = set_zero_to_nan(z_heatmap)

    heatmap = go.Heatmap(
        z=z_heatmap,
        x=x_heatmap,
        y=y_heatmap,
        xgap=HEATMAP_TILE_PADDING,
        ygap=HEATMAP_TILE_PADDING,
        hovertext=hovertext,
        hoverinfo="text",
        colorscale="Reds",
        showscale=False,
    )

    top_counts = create_marginal_density_bar_chart(
        x_heatmap, x_counts, "v", x, "x2", "y2"
    )
    right_counts = create_marginal_density_bar_chart(
        y_counts, y_heatmap, "h", y, "x3", "y3"
    )

    data = [heatmap, top_counts, right_counts]
    layout = create_numeric_heatmap_layout_with_marginal_densities(x, y)
    fig_widget = go.FigureWidget(data=data, layout=layout)

    # data
    heatmap_data = fig_widget.data[0]
    top_counts_data = fig_widget.data[1]
    right_counts_data = fig_widget.data[2]

    x_bin_slider = create_bin_slider(
        n_bins=n_bins,
        n_min_bins=MIN_N_BINS,
        n_max_bins=MAX_N_BINS,
        orientation="horizontal",
    )
    y_bin_slider = create_bin_slider(
        n_bins=n_bins,
        n_min_bins=MIN_N_BINS,
        n_max_bins=MAX_N_BINS,
        orientation="vertical",
    )

    def set_x_bin_size(change):
        (
            x_bins,
            x_counts,
            y_bins,
            y_counts,
            heatmap_matrix,
        ) = compute_numeric_to_numeric_heatmap_data(
            df_notnull, x, y, [change.new, y_bin_slider.value], frequencies=False
        )
        z_heatmap = heatmap_matrix
        with fig_widget.batch_update():
            _update_heatmap_figure_data(
                heatmap_data,
                x=get_lower_bounds_of_bins(x_bins),
                y=get_lower_bounds_of_bins(y_bins),
                z=set_zero_to_nan(z_heatmap),
                hovertext=heatmap_hovertext(
                    x_bins, y_bins, z_heatmap, x, y, Z_HOVER_LABEL
                ),
            )
            _update_count_figure_data(
                top_counts_data, get_lower_bounds_of_bins(x_bins), x_counts
            )

    x_bin_slider.observe(set_x_bin_size, names="value")

    def set_y_bin_size(change):
        (
            x_bins,
            x_counts,
            y_bins,
            y_counts,
            heatmap_matrix,
        ) = compute_numeric_to_numeric_heatmap_data(
            df_notnull, x, y, [x_bin_slider.value, change.new], frequencies=False
        )
        z_heatmap = heatmap_matrix
        with fig_widget.batch_update():
            _update_heatmap_figure_data(
                heatmap_data,
                x=get_lower_bounds_of_bins(x_bins),
                y=get_lower_bounds_of_bins(y_bins),
                z=set_zero_to_nan(z_heatmap),
                hovertext=heatmap_hovertext(
                    x_bins, y_bins, z_heatmap, x, y, Z_HOVER_LABEL
                ),
            )
            _update_count_figure_data(
                right_counts_data, y_counts, get_lower_bounds_of_bins(y_bins)
            )

    y_bin_slider.observe(set_y_bin_size, names="value")

    output = widgets.VBox([])
    slider_with_plot = widgets.HBox([y_bin_slider, fig_widget])
    output.children = [slider_with_plot, x_bin_slider]
    return output


@embeddable_plain_blocking
def numeric_to_numeric_ppplot(df, x, y, **kwargs):
    """
    Display an interactive predictive power plot.
    """

    ROUND_DIGITS = 2
    Z_HOVER_LABEL = "Col. Freq."

    df_notnull = df[[x, y]].dropna()

    n_bins = DEFAULT_N_BINS
    (
        x_bins,
        x_counts,
        y_bins,
        y_counts,
        heatmap_matrix,
    ) = compute_numeric_to_numeric_heatmap_data(df_notnull, x, y, [n_bins, n_bins])

    x_heatmap, y_heatmap = (
        get_lower_bounds_of_bins(x_bins),
        get_lower_bounds_of_bins(y_bins),
    )
    z_heatmap = np.round(heatmap_matrix, ROUND_DIGITS)

    hovertext = heatmap_hovertext(x_bins, y_bins, z_heatmap, x, y, Z_HOVER_LABEL)
    z_heatmap = set_zero_to_nan(z_heatmap)

    heatmap = go.Heatmap(
        z=z_heatmap,
        x=x_heatmap,
        y=y_heatmap,
        xgap=HEATMAP_TILE_PADDING,
        ygap=HEATMAP_TILE_PADDING,
        hovertext=hovertext,
        hoverinfo="text",
        colorscale="Reds",
        showscale=False,
    )

    top_counts = create_marginal_density_bar_chart(
        x_heatmap, x_counts, "v", x, "x2", "y2"
    )
    right_counts = create_marginal_density_bar_chart(
        y_counts, y_heatmap, "h", y, "x3", "y3"
    )

    data = [heatmap, top_counts, right_counts]
    layout = create_numeric_heatmap_layout_with_marginal_densities(x, y)
    fig_widget = go.FigureWidget(data=data, layout=layout)

    heatmap_data = fig_widget.data[0]
    top_counts_data = fig_widget.data[1]
    right_counts_data = fig_widget.data[2]

    x_bin_slider = create_bin_slider(
        n_bins=n_bins,
        n_min_bins=MIN_N_BINS,
        n_max_bins=MAX_N_BINS,
        orientation="horizontal",
    )
    y_bin_slider = create_bin_slider(
        n_bins=n_bins,
        n_min_bins=MIN_N_BINS,
        n_max_bins=MAX_N_BINS,
        orientation="vertical",
    )

    def set_x_bin_size(change):
        (
            x_bins,
            x_counts,
            y_bins,
            y_counts,
            heatmap_matrix,
        ) = compute_numeric_to_numeric_heatmap_data(
            df_notnull, x, y, [change.new, y_bin_slider.value]
        )
        z_heatmap = np.round(heatmap_matrix, ROUND_DIGITS)
        with fig_widget.batch_update():
            _update_heatmap_figure_data(
                heatmap_data,
                x=get_lower_bounds_of_bins(x_bins),
                y=get_lower_bounds_of_bins(y_bins),
                z=set_zero_to_nan(z_heatmap),
                hovertext=heatmap_hovertext(
                    x_bins, y_bins, z_heatmap, x, y, Z_HOVER_LABEL
                ),
            )
            _update_count_figure_data(
                top_counts_data, get_lower_bounds_of_bins(x_bins), x_counts
            )

    x_bin_slider.observe(set_x_bin_size, names="value")

    def set_y_bin_size(change):
        (
            x_bins,
            x_counts,
            y_bins,
            y_counts,
            heatmap_matrix,
        ) = compute_numeric_to_numeric_heatmap_data(
            df_notnull, x, y, [x_bin_slider.value, change.new]
        )
        z_heatmap = np.round(heatmap_matrix, ROUND_DIGITS)
        with fig_widget.batch_update():
            _update_heatmap_figure_data(
                heatmap_data,
                x=get_lower_bounds_of_bins(x_bins),
                y=get_lower_bounds_of_bins(y_bins),
                z=set_zero_to_nan(z_heatmap),
                hovertext=heatmap_hovertext(
                    x_bins, y_bins, z_heatmap, x, y, Z_HOVER_LABEL
                ),
            )
            _update_count_figure_data(
                right_counts_data, y_counts, get_lower_bounds_of_bins(y_bins)
            )

    y_bin_slider.observe(set_y_bin_size, names="value")

    output = widgets.VBox([])
    slider_with_plot = widgets.HBox([y_bin_slider, fig_widget])
    output.children = [slider_with_plot, x_bin_slider]
    return output


@embeddable_with_outlet_blocking
def scatter(df, numeric1, numeric2, outlet=None, loading=None, **kwargs):
    """An interactive scatter plot"""

    def scatter_figure(df):
        return go.FigureWidget(
            data=[go.Scatter(x=df[numeric1], y=df[numeric2], mode="markers")],
            layout=go.Layout(
                hovermode="closest",
                xaxis={"title": numeric1},
                yaxis={"title": numeric2},
                autosize=False,
                width=500,
                height=300,
                margin=go.layout.Margin(l=50, r=20, b=40, t=20),
                **PLOTLY_BACKGROUND,
            ),
        )

    max_rows = 10_000
    notification_text = f"Plotting scatter plots with more than {max_rows:,} rows is not recommended because it takes a long time, it might freeze your browser and the plot is hardly interpretable due to overplotting. Therefore, we randomly sampled {max_rows:,} rows."

    outlet.children = [
        RowsSampler(
            df=df,
            max_rows=max_rows,
            notification_text=notification_text,
            on_render=lambda df: scatter_figure(df),
        )
    ]
    return outlet


@embeddable_plain_blocking
def cat2_to_numeric_ppplot(df, cat2, numeric, same_y_axis=False, **kwargs):
    """
    An interactive predictive power plot for x being a column with 2 categories and y being a
    numeric column (like an integer or float)
    """

    df_notnull = df[[cat2, numeric]].dropna()

    numeric_series = df_notnull[numeric]
    cat2_series = df_notnull[cat2]
    cat2_classes = sorted(cat2_series.unique())

    left_cat2 = cat2_classes[0]
    left_num = numeric_series[cat2_series == left_cat2]

    right_cat2 = cat2_classes[1]
    right_num = numeric_series[cat2_series == right_cat2]

    bin_settings = _get_bin_settings(
        numeric_series, DEFAULT_N_BINS
    )  # we can let both histograms have exact same bins

    left_histogram = go.Histogram(
        y=left_num,
        ybins=bin_settings,
        autobiny=False,
        orientation="h",
        hoverinfo="none",
        opacity=BAR_OPACITY,
        name=str(left_cat2),  # in case it is of type numpy.indt64 (causing error)
    )
    right_histogram = go.Histogram(
        y=right_num,
        ybins=bin_settings,
        autobiny=False,
        orientation="h",
        hoverinfo="none",
        name=str(right_cat2),
        xaxis="x2",
        opacity=BAR_OPACITY,
    )

    cat2_table = cat2_series.value_counts()
    cat2_bar = go.Bar(
        x=cat2_classes,
        y=cat2_table[cat2_classes],
        yaxis="y2",
        xaxis="x3",
        opacity=BAR_OPACITY,
        hoverinfo="y",
        marker=dict(color=MARGINAL_DENSITY_COLOR),
        name="",  # make "trace" disappear in hover info
    )

    data = [left_histogram, right_histogram, cat2_bar]

    layout_left_xaxis = dict(title=str(left_cat2), domain=[0, 0.5])
    if same_y_axis:
        layout_left_xaxis["autorange"] = "reversed"

    layout = go.Layout(
        xaxis=layout_left_xaxis,
        yaxis=dict(title=numeric, domain=[0, 0.7]),
        xaxis2=dict(title=str(right_cat2), domain=[0.5, 1]),
        yaxis2=dict(title="Count", domain=[0.73, 1], anchor="x3"),
        xaxis3=dict(
            title=cat2,
            side="top",
            domain=[0, 1],
            anchor="y2",
            tickvals=["", ""],  # remove group label on xaxis
        ),
        bargap=0.1,
        showlegend=False,
        height=MULTIPLOT_FIGURE_HEIGHT,
        **PLOTLY_BACKGROUND,
    )

    fig_widget = go.FigureWidget(data=data, layout=layout)
    left_histogram_data = fig_widget.data[0]
    right_histogram_data = fig_widget.data[1]

    bin_slider = create_bin_slider(
        n_bins=10,
        n_min_bins=2,
        n_max_bins=100,
        step=1,
        description="Bins",
        readout=True,
        readout_format="d",
        orientation="vertical",
    )

    def set_bin_size(change):
        left_histogram_data.ybins = _get_bin_settings(numeric_series, change["new"])
        right_histogram_data.ybins = _get_bin_settings(numeric_series, change["new"])

    bin_slider.observe(set_bin_size, names="value")

    return widgets.HBox([bin_slider, fig_widget])


@embeddable_with_outlet_blocking
def compare_numeric_split_by_cat2(
    df, numeric, cat2, outlet=None, loading=None, **kwargs
):
    cat_classes = sorted(df[cat2].unique())
    cat_class_histograms = []
    for cat_class in cat_classes:
        cat_class_histograms.append(
            go.Histogram(
                x=df[numeric].loc[df[cat2] == cat_class],
                name=f"{cat2} {cat_class}",
                opacity=BAR_OPACITY,
            )
        )
    layout = go.Layout(barmode="overlay", hovermode="closest", **PLOTLY_BACKGROUND)
    fig = go.FigureWidget(data=cat_class_histograms, layout=layout)

    title = widgets.HTML(
        f"Answers the question: How do the {numeric} distributions compare if you split them by the {cat2} class?"
    )
    subtitle = widgets.HTML(
        f"For example: for a given {numeric} bin, which is the most frequent {cat2} class?"
    )
    outlet.children = [title, subtitle, fig]
    return outlet


@embeddable_with_outlet_blocking
def stacked_histogram(df, col_a, col_b, outlet=None, loading=None, **kwargs):
    series_col_a = df[col_a].dropna()

    n_bins = DEFAULT_N_BINS
    bin_settings = _get_bin_settings(series_col_a, n_bins)

    try:
        cat_classes = sorted(df[col_b].unique())
    except:
        cat_classes = df[col_b].unique()
    cat_class_histograms = []
    for cat_class in cat_classes:
        cat_class_histograms.append(
            go.Histogram(
                x=df[col_a].loc[df[col_b] == cat_class],
                autobinx=False,
                xbins=bin_settings,
                name=f"{col_b} {cat_class}",
                opacity=BAR_OPACITY,
            )
        )
    layout = go.Layout(
        barmode="stack",
        xaxis={"title": f"{col_a}"},
        yaxis=dict(title="Count", fixedrange=True),
        bargap=0.05,
        **PLOTLY_BACKGROUND,
    )
    fig = go.FigureWidget(data=cat_class_histograms, layout=layout)
    # return fig
    outlet.children = [fig]
    return outlet


@embeddable_plain_blocking
def numeric_to_cat2_ppplot(df, numeric, cat, **kwargs):
    BAR_GAP = 0.1

    df_notnull = df[[numeric, cat]].dropna()

    numeric_series = df_notnull[numeric]

    cat_series = df_notnull[cat]
    cat_classes = sorted(cat_series.unique())

    bin_settings = _get_bin_settings(numeric_series, DEFAULT_N_BINS)

    share_histograms = [
        go.Histogram(
            histfunc="avg",
            y=(cat_series == cat_class) * 100,
            x=numeric_series,
            name=str(cat_class),
            xbins=bin_settings,
            orientation="v",
            # hoverinfo="none",
            opacity=BAR_OPACITY,
        )
        for cat_class in cat_classes
    ]

    numeric_histogram = go.Histogram(
        x=numeric_series,
        xbins=bin_settings,
        yaxis="y2",
        name=numeric,
        hoverinfo="x",
        opacity=BAR_OPACITY,
        showlegend=False,
        marker=dict(color=MARGINAL_DENSITY_COLOR),
    )

    cat_table = cat_series.value_counts()
    cat_bar = go.Bar(
        y=cat_classes,
        x=cat_table[cat_classes],
        orientation="h",
        yaxis="y3",
        xaxis="x3",
        opacity=BAR_OPACITY,
        name=cat,
        showlegend=False,
        hoverinfo="none",
        marker=dict(color=MARGINAL_DENSITY_COLOR),
    )

    data = share_histograms + [numeric_histogram, cat_bar]

    x_domain_reference_value = 0.7
    y_domain_reference_value = 0.73
    layout = go.Layout(
        yaxis=dict(
            title=f"{cat} (share in %)",
            domain=[0, y_domain_reference_value],
            ticksuffix="%",
            hoverformat=".1f",
        ),
        xaxis=dict(title=numeric, domain=[0, x_domain_reference_value]),
        yaxis2=dict(
            title="Count", anchor="x2", domain=[y_domain_reference_value + 0.02, 1]
        ),
        xaxis3=dict(
            title="Count", domain=[x_domain_reference_value + 0.03, 1], anchor="y3"
        ),
        yaxis3=dict(
            title=cat,
            domain=[0, y_domain_reference_value - 0.03],
            anchor="x3",
            side="right",
            type="category",
        ),
        barmode="stack",
        bargap=BAR_GAP,
        legend=dict(orientation="h"),
        height=MULTIPLOT_FIGURE_HEIGHT,
        margin=go.layout.Margin(t=30),
        **PLOTLY_BACKGROUND,
    )

    fig_widget = go.FigureWidget(data=data, layout=layout)
    histograms = [fig_widget.data[i] for i in range(len(data) - 1)]

    bin_slider = create_bin_slider(
        n_bins=10,
        n_min_bins=2,
        n_max_bins=MAX_N_BINS,
        step=1,
        description="Bins",
        orientation="horizontal",
        readout=True,
        readout_format="d",
    )

    def set_bin_size(change):
        for hist in histograms:
            hist.xbins = _get_bin_settings(numeric_series, change["new"])

    bin_slider.observe(set_bin_size, names="value")

    return widgets.VBox([fig_widget, bin_slider])


@embeddable_plain_blocking
def cat300_downsample_cat10_plot(base_plot, df, x, y, **kwargs):
    message_html = f"The column '{x}' has many unique values. In order to provide a suitable analysis, we filtered the {CATEGORICAL_WITH_HIGH_CARDINALITY_BREAKPOINT} most common values of '{x}'"
    top_hint = notification(message_html, type="warning")

    top_list = (
        df[x]
        .value_counts()
        .index.tolist()[0:CATEGORICAL_WITH_HIGH_CARDINALITY_BREAKPOINT]
    )
    top_df = df[df[x].isin(top_list)]
    return top_hint, base_plot(top_df, x, y, **kwargs)


@embeddable_plain_blocking
def box_or_violin_plot(df, x, y, plot_type="violin", **kwargs):
    df = df[[x, y]].dropna()

    x_series = df[x]
    y_series = df[y]

    conditional_distributions = []
    x_counts = value_counts(x_series)
    violin_extra_elements = dict(box=dict(visible=True), meanline=dict(visible=True))
    for group in x_counts.index:
        trace = {
            "type": plot_type,
            "x": x_series[x_series == group],
            "y": y_series[x_series == group],
            "name": str(group),
            "boxpoints": False,
        }
        if plot_type == "violin":
            trace.update(violin_extra_elements)

        conditional_distributions.append(trace)

    x_bar = go.Bar(
        x=x_counts.index,
        y=x_counts,
        yaxis="y2",
        hoverinfo="y",
        showlegend=False,
        marker=dict(color=MARGINAL_DENSITY_COLOR),
        opacity=BAR_OPACITY,
    )

    y_marginal_distribution = dict(
        type=plot_type,
        y=y_series,
        xaxis="x2",
        name=f"{str(y)} (total)",
        showlegend=False,
        boxpoints=False,
        marker=dict(color=MARGINAL_DENSITY_COLOR),
    )
    if plot_type == "violin":
        y_marginal_distribution.update(violin_extra_elements)

    data = conditional_distributions + [x_bar, y_marginal_distribution]

    layout = dict(
        xaxis=dict(title=str(x), type="category", domain=[0, 0.8]),
        yaxis=dict(zeroline=True, title=str(y), domain=[0, 0.7]),
        xaxis2=dict(title="", domain=[0.83, 1]),
        yaxis2=dict(title="Count", domain=[0.73, 1]),
        **PLOTLY_BACKGROUND,
    )

    return go.FigureWidget(data=data, layout=layout)


@embeddable_plain_blocking
def violin_plot(df, x, y, **kwargs):
    return box_or_violin_plot(df, x, y, plot_type="violin", **kwargs)


@embeddable_plain_blocking
def boxplot(df, x, y, **kwargs):
    return box_or_violin_plot(df, x, y, plot_type="box", **kwargs)


@embeddable_plain_blocking
def numeric_to_cat10_ppplot(df, x, y, **kwargs):
    ROUND_DIGITS = 2
    Z_HOVER_LABEL = "Col. Freq."

    df_notnull = df[[x, y]].dropna()

    (
        x_bins,
        x_counts,
        y_categories,
        y_counts,
        heatmap_matrix,
    ) = compute_numeric_to_cat_heatmap_data(df_notnull, x, y, DEFAULT_N_BINS)

    x_heatmap = get_lower_bounds_of_bins(x_bins)
    y_heatmap = y_categories
    z_heatmap = np.round(heatmap_matrix, ROUND_DIGITS)

    hovertext = heatmap_hovertext(x_bins, y_categories, z_heatmap, x, y, Z_HOVER_LABEL)

    heatmap = go.Heatmap(
        z=z_heatmap,
        x=x_heatmap,
        y=y_heatmap,
        xgap=HEATMAP_TILE_PADDING,
        ygap=HEATMAP_TILE_PADDING,
        hoverinfo="text",
        hovertext=hovertext,
        colorscale="Reds",
        showscale=False,
        # colorbar=dict(x=-0.5, y=0.5, len=0.5) # it is not possible to have a horizontal color bar atm (https://github.com/plotly/plotly.js/issues/1244
    )

    top_counts = go.Bar(
        x=x_heatmap,
        y=x_counts,
        orientation="v",
        opacity=BAR_OPACITY,
        showlegend=False,
        marker=dict(color=MARGINAL_DENSITY_COLOR),
        name=x,
        yaxis="y2",
    )

    right_counts = go.Bar(
        x=y_counts,
        y=y_heatmap,
        orientation="h",
        opacity=BAR_OPACITY,
        showlegend=False,
        marker=dict(color=MARGINAL_DENSITY_COLOR),
        name=y,
        xaxis="x3",
        yaxis="y3",
    )

    data = [heatmap, top_counts, right_counts]

    layout = go.Layout(
        xaxis=dict(title=x, domain=[0, 0.7], showline=False, zeroline=False),
        yaxis=dict(
            type="category", title=y, domain=[0, 0.7], showline=False, zeroline=False
        ),
        yaxis2=dict(title="Count", domain=[0.73, 1], anchor="x2"),
        xaxis3=dict(title="Count", domain=[0.73, 1], anchor="y3"),
        yaxis3=dict(
            tickvals=[""] * len(y_counts),
            domain=[0, 0.7],
            anchor="x3",
            side="right",
            type="category",
        ),
        bargap=0.01,
        height=MULTIPLOT_FIGURE_HEIGHT,
        **PLOTLY_BACKGROUND,
    )

    fig_widget = go.FigureWidget(data=data, layout=layout)
    heatmap_data = fig_widget.data[0]
    top_counts_data = fig_widget.data[1]

    bin_slider = create_bin_slider(
        n_bins=10,
        n_min_bins=2,
        n_max_bins=100,
        step=1,
        description="Bins",
        readout=True,
        readout_format="d",
        orientation="horizontal",
    )

    def set_bin_size(change):
        (
            x_bins,
            x_counts,
            y_categories,
            _,
            heatmap_matrix,
        ) = compute_numeric_to_cat_heatmap_data(df_notnull, x, y, change.new)

        x_heatmap = get_lower_bounds_of_bins(x_bins)
        z_heatmap = np.round(heatmap_matrix, ROUND_DIGITS)
        hovertext = heatmap_hovertext(
            x_bins, y_categories, z_heatmap, x, y, Z_HOVER_LABEL
        )

        heatmap_data.x = x_heatmap
        heatmap_data.z = z_heatmap
        heatmap_data.hovertext = hovertext
        top_counts_data.x = x_heatmap
        top_counts_data.y = x_counts

    bin_slider.observe(set_bin_size, names="value")

    return widgets.VBox([fig_widget, bin_slider])


@embeddable_plain_blocking
def _relation_cat2_to_cat2(df, x, y, **kwargs):
    tab_contents = []
    # Removed ppplot because it's to complex for the user to understand.
    tab_contents.append(
        {
            "title": "Mosaic",
            "content": new_lazy_widget_decorator(mosaic_plot, df, x, y, **kwargs),
        }
    )
    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def cat2_to_cat2_ppplot(df, x, y, **kwargs):
    return cat10_to_cat10_ppplot(df, x, y, **kwargs)


@embeddable_plain_blocking
def _relation_cat2_to_cat10(df, x, y, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": f"Predictive Power Plot",
            "content": new_lazy_widget_decorator(
                cat2_to_cat10_ppplot, df, x, y, **kwargs
            ),
        }
    )
    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def _relation_cat10_to_cat2(df, x, y, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": "Stacked Bar Chart",
            "content": new_lazy_widget_decorator(
                stacked_bar_chart_sorted_by_x, df, x, y, **kwargs
            ),
        }
    )
    tab_contents.append(
        {
            "title": "Predictive Power Plot",
            "content": new_lazy_widget_decorator(
                cat10_to_cat2_ppplot, df, x, y, **kwargs
            ),
        }
    )
    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def _relation_cat10_to_cat10(df, x, y, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": f"Stacked Bar Chart",
            "content": new_lazy_widget_decorator(
                stacked_bar_chart_sorted_by_x, df, x, y, **kwargs
            ),
        }
    )
    tab_contents.append(
        {
            "title": f"Predictive Power Plot",
            "content": new_lazy_widget_decorator(
                cat10_to_cat10_ppplot, df, x, y, **kwargs
            ),
        }
    )
    return lazy_tabs(tab_contents)


def change_df_column_order(df, top_columns, **kwargs):
    """
    Change column order of df, moving top_columns to the front of df.

    :param top_columns: a list of the columns you want to display as the first columns in df

    :return: a pandas.DataFrame with new column order.
    """

    old_columns_list = df.columns.tolist()
    for column in top_columns:
        old_columns_list.remove(column)
    resorted_columns_list = top_columns + old_columns_list
    return df[resorted_columns_list]


@embeddable_plain_blocking
def _relation_numeric_to_cat300(df, x, y, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": f"Drilldown",
            "content": new_lazy_widget_decorator(
                numeric_to_cat_drilldown, df, x, y, **kwargs
            ),
        }
    )
    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def numeric_to_cat_drilldown(df, x, y, **kwargs):
    """
    Interactive widget. Create a slider and a table that lets the user bin values in columns x and then displays the
    count and number of unique value of column y in each created bin of x.
    """
    df = (
        df.copy()
    )  # copy so that we dont manipulate the original df because the function adds the binned num series and forwards it as a df

    bin_size = [10]
    new_x_name = f"binned {x}"
    plot_outlet = widgets.VBox()

    def set_bin_size(bins=10):
        bin_size[0] = bins
        df[new_x_name] = pd.cut(df[x], bins=bin_size[0], right=False, retbins=True)[0]
        plot_outlet.children = [
            cat_to_cat_uniques_table(
                df, new_x_name, y, show_df_subset_string=False, **kwargs
            )
        ]

    bin_slider = interactive(set_bin_size, bins=(2, 100, 1))
    set_bin_size()  # initialize
    return bin_slider, plot_outlet


@embeddable_plain_blocking
def _relation_cat300_to_numeric(df, x, y, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": f"Top{CATEGORICAL_WITH_HIGH_CARDINALITY_BREAKPOINT}",
            "content": new_lazy_widget_decorator(
                cat300_downsample_cat10_plot, boxplot, df, x, y, **kwargs
            ),
        }
    )
    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def _relation_cat2_to_cat300(df, x, y, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": f"Drilldown",
            "content": new_lazy_widget_decorator(
                cat_to_cat_uniques_table, df, x, y, y_is_high_cat=True, **kwargs
            ),
        }
    )
    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def _relation_cat300_to_cat2(df, x, y, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": "Stacked Bar Chart",
            "content": new_lazy_widget_decorator(
                cat300_downsample_cat10_plot,
                stacked_bar_chart_sorted_by_x,
                df,
                x,
                y,
                **kwargs,
            ),
        }
    )
    tab_contents.append(
        {
            "title": f"Top {CATEGORICAL_WITH_HIGH_CARDINALITY_BREAKPOINT} PP Plot",
            "content": new_lazy_widget_decorator(
                cat300_downsample_cat10_plot, cat10_to_cat2_ppplot, df, x, y, **kwargs
            ),
        }
    )
    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def _relation_cat300_to_cat10(df, x, y, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": f"Top{CATEGORICAL_WITH_HIGH_CARDINALITY_BREAKPOINT}",
            "content": new_lazy_widget_decorator(
                cat300_downsample_cat10_plot, cat10_to_cat10_ppplot, df, x, y, **kwargs
            ),
        }
    )
    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def cat_to_cat_uniques_table(df, cat300, y_any, show_df_subset_string=True, **kwargs):

    cat300_value_counts = (
        df[[cat300, y_any]]
        .groupby(cat300)
        .agg({cat300: "count"})
        .rename(columns={cat300: f"Subset row count"})
    )
    y_any_nunique = (
        df[[cat300, y_any]]
        .groupby(cat300)
        .agg({y_any: "nunique"})
        .rename(columns={y_any: f"Unique values of {y_any}"})
    )

    overview_df = pd.concat([y_any_nunique, cat300_value_counts], axis=1).reset_index()
    overview_df = overview_df.sort_values(by=cat300, ascending=True)

    qwidget = qgrid_widget(overview_df)

    filter_outlet = widgets.VBox()
    filter_outlet.children = [
        notification(
            f"Click on a row in the interactive table to see the distribution of {y_any} in the selected subset."
        )
    ]

    show_df_subset_string_list = [
        show_df_subset_string
    ]  # transform variable to list so that the variable is available in the closure handle_selection_changed

    def handle_selection_changed(event, qgrid_widget, **kwargs):
        if len(event["new"]) > 0:
            visible_overview_df = qwidget.get_changed_df()
            selected_overview_df = visible_overview_df.iloc[event["new"]]

            cat300_uniques = selected_overview_df[cat300].unique()
            array_string = (
                "[" + ", ".join([f"'{item}'" for item in cat300_uniques]) + "]"
            )
            subset_df_string = f"df[df['{cat300}'].isin({array_string})]"
            if show_df_subset_string_list[0]:
                header = widgets.HTML(
                    "<h3>Selected subset:</h3><br>" + subset_df_string
                )
            else:
                header = widgets.HTML("<h3>Selected subset:</h3>")

            subset_df = df[df[cat300].isin(cat300_uniques)]
            subset_df = change_df_column_order(subset_df, [cat300, y_any])

            tab_contents = []

            object_overview = generic_summary(column_object_distribution, **kwargs)
            tab_contents.append(
                {
                    "title": f"Subset {y_any}",
                    "content": new_lazy_widget_decorator(
                        object_overview, subset_df, y_any, **kwargs
                    ),
                }
            )
            tab_contents.append(
                {
                    "title": "Raw data view",
                    "content": new_lazy_widget_decorator(preview, subset_df, **kwargs),
                }
            )
            tabs = lazy_tabs(tab_contents)
            filter_outlet.children = [header, tabs]

    qwidget.on("selection_changed", handle_selection_changed)
    return qwidget, filter_outlet


@embeddable_plain_blocking
def _relation_cat300_to_cat300(df, cat300_a, cat300_b, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": f"Drilldown",
            "content": new_lazy_widget_decorator(
                cat300_downsample_cat10_plot,
                cat_to_cat_uniques_table,
                df,
                cat300_a,
                cat300_b,
                **kwargs,
            ),
        }
    )

    return lazy_tabs(tab_contents)


@embeddable_plain_blocking
def _relation_cat10_to_cat300(df, x, y, **kwargs):
    tab_contents = []
    tab_contents.append(
        {
            "title": f"Drilldown",
            "content": new_lazy_widget_decorator(
                cat_to_cat_uniques_table, df, x, y, **kwargs
            ),
        }
    )
    return lazy_tabs(tab_contents)


########################################
### utilities for the bivariate overview
########################################


def is_cat2_for_plot(series, category_count, **kwargs):
    return category_count <= 2


def is_cat10_for_plot(series, category_count, **kwargs):
    return category_count <= CATEGORICAL_WITH_HIGH_CARDINALITY_BREAKPOINT


def is_id_for_plot(series, category_count, **kwargs):
    if EXCLUDE_ID_TYPE:
        return False
    return category_count >= series.notna().count()


def is_datetime_for_plot(series):
    return is_datetime64_any_dtype(series)


def semantic_column_class(series, exclude_numeric=False, **kwargs):
    """
    Determine the semantic data type of a column which is relevant for plotting.

    For example: if an integer column has only two values, a histogramm doesn't make sense, so we
    we treat it like a categorical column with two categories.
    """

    include_numeric = not exclude_numeric
    series_cc = category_count(series)

    # timedelta is handled based on its value_counts as cat2, cat10, cat300, or id

    if series_cc == 0:
        if len(series) == 0:
            return "empty"
        else:
            return "only_nans"
    elif series_cc == 1:
        return "constant"
    elif is_datetime64_any_dtype(series):
        # needs to be before id check
        return "datetime"
    elif is_bool_dtype(series):
        # boolean should be before numeric
        return "cat2"
    elif include_numeric and is_numeric_dtype(series):
        # is skipped if numeric should be interpreted as categoric
        return "numeric"
    elif is_cat2_for_plot(series, series_cc):
        # object or strings with just two values
        return "cat2"
    elif is_cat10_for_plot(series, series_cc):
        return "cat10"
    elif is_id_for_plot(series, series_cc):
        # checked after numeric because numeric values might have no duplicates
        return "id"
    else:
        return "cat300"


# wrappers of highlevel functions should not be high level functions themselves, as
# the notifications will be shown twice then
# @maybe_show_notifications # plot wraps high_level_functions, which already maybe_show_notifications
@user_exposed_function
@catch_empty_df
@embeddable_plain_blocking
# @log_function
def plot(df, x=None, y=None, **kwargs):
    if x and y:
        return compare(df, x, y, **kwargs)
    elif x:
        return _column_summary(df, x, **kwargs)
    elif y:
        return _column_summary(df, y, **kwargs)
    else:
        return overview(df, **kwargs)


def get_compare_functions(col_a_desc, col_b_desc):
    """
    Given the semantic data types of column A and B, col_a_desc and col_b_desc, respectively,
    call the respective relation_..._to_... function
    """

    # TODO: What happens if col_a_desc = "numeric" and col_b_desc = "id"?
    # -> relation_id_to_id will be called which doesn't make sense
    special_functions = ["id", "constant", "empty", "only_nans"]
    if col_a_desc in special_functions:
        compare_to_func = f"relation_{col_a_desc}_to_any"
        compare_from_func = f"relation_{col_a_desc}_to_any"
    elif col_b_desc in special_functions:
        compare_to_func = f"relation_{col_b_desc}_to_id"
        compare_from_func = f"relation_{col_b_desc}_to_id"
    else:  # most important/frequent case
        compare_to_func = f"relation_{col_a_desc}_to_{col_b_desc}"
        compare_from_func = f"relation_{col_b_desc}_to_{col_a_desc}"

    return eval(compare_to_func), eval(compare_from_func)


# Deprecated ... don't call compare directly anymore but rather use the plot function
@log_function
@maybe_show_notifications
@embeddable_plain_blocking
def compare(
    df, x, y, directional=False, x_not_numeric=False, y_not_numeric=False, **kwargs
):
    function_hint_ = get_function_hint(
        f"bam.plot({DF_OLD}, {string_to_code(x)}, {string_to_code(y)})", **kwargs
    )

    if columns_do_not_exist(df, [x, y]):
        return columns_missing_error(
            df, [x, y], "Error when trying to show the Bivariate Plot:"
        )

    if x == y:
        return _column_summary(df, x, **kwargs)

    x_desc = semantic_column_class(df[x], exclude_numeric=x_not_numeric)
    y_desc = semantic_column_class(df[y], exclude_numeric=y_not_numeric)

    if x_desc == "datetime" or y_desc == "datetime":
        return (
            function_hint_,
            RowsSampler(
                df=df,
                on_render=lambda df: _datetime_bivariate_plot(
                    df, x, y, x_desc, y_desc, **kwargs
                ),
            ),
        )

    compare_to_func, compare_from_func = get_compare_functions(x_desc, y_desc)

    if directional:
        return (
            function_hint_,
            RowsSampler(
                df=df,
                on_render=lambda df: compare_to_func(df, x, y, **kwargs),
            ),
        )
    else:

        def tab_contents(df):
            return [
                {
                    # 'title': f"{x} predicts {y}", this is too long for typical column names
                    "title": f"A predicts B",
                    "content": new_lazy_widget_decorator(
                        compare_to_func, df, x, y, **kwargs
                    ),
                },
                {
                    "title": f"B predicts A",
                    "content": new_lazy_widget_decorator(
                        compare_from_func, df, y, x, **kwargs
                    ),
                },
                {
                    "title": f"{x}",
                    "content": new_lazy_widget_decorator(
                        _column_summary, df, x, **kwargs
                    ),
                },
                {
                    "title": f"{y}",
                    "content": new_lazy_widget_decorator(
                        _column_summary, df, y, **kwargs
                    ),
                },
            ]

        return (
            function_hint_,
            RowsSampler(
                df=df,
                on_render=lambda df: lazy_tabs(tab_contents(df)),
            ),
        )


@embeddable_plain_blocking
def _datetime_bivariate_plot(df, x, y, x_desc, y_desc, **kwargs):
    # ensure that x is datetime, otherwise swap x and y
    if x_desc != "datetime":
        x, y = y, x
        x_desc, y_desc = y_desc, x_desc
    compare_to_func, _ = get_compare_functions(x_desc, y_desc)

    tab_contents = []

    if (x_desc == "datetime") and (y_desc == "datetime"):
        tab_contents.append(
            {
                "title": f"A predicts B",
                "content": new_lazy_widget_decorator(
                    compare_to_func, df, x, y, **kwargs
                ),
            }
        )
        tab_contents.append(
            {
                "title": f"B predicts A",
                "content": new_lazy_widget_decorator(
                    compare_to_func, df, y, x, **kwargs
                ),
            }
        )
    else:
        tab_contents.append(
            {
                "title": f"Over time",
                "content": new_lazy_widget_decorator(
                    compare_to_func, df, x, y, **kwargs
                ),
            }
        )

    tab_contents.append(
        {
            "title": f"{x}",
            "content": new_lazy_widget_decorator(_column_summary, df, x, **kwargs),
        }
    )
    tab_contents.append(
        {
            "title": f"{y}",
            "content": new_lazy_widget_decorator(_column_summary, df, y, **kwargs),
        }
    )
    return lazy_tabs(tab_contents)


########################################
### utilities for the pairwise decision tree score information
########################################


def pp_score_features(df, target, progress=None, **kwargs):
    """
    For a given target, compute the pp score of all columns in df.

    :param df: pandas.DataFrame
    :param target: string column name of the target you want to compute the pp scores for.
    """

    sorted_scores = []
    for index, feature in enumerate(df.columns):
        score = pps.score(
            df,
            x=feature,
            y=target,
            invalid_score=PREDICTIVE_POWER_ERROR_SCORE,
            random_seed=get_option("global.random_seed"),
            catch_errors=True,
        )["ppscore"]
        sorted_scores.append({"score": score, "feature": feature})

        if progress:
            progress.value = index / len(df.columns)

    sorted_scores.sort(key=lambda x: x["score"], reverse=True)
    return sorted_scores


def model_score_sentence(score):
    """
    Create a natural language sentence about the model scores for a given ppscore result

    Examples:
    - regression: Age predicts Survived with 0.458 mean absolute error (0.406 baseline)
    - classification: Age predicts Pclass with 0.458 weighted F1 (0.406 baseline)
    - predict_itself: skip
    - predict_id: Age cannot predict Name because Name is an ID
    - predict_constant: Age can perfectly predict Name because Name only has a single value
    """

    case = score["case"]
    if case in ["regression", "classification"]:
        return f"""{score["x"]} predicts {score["y"]} with {score["ppscore"]:.3f} {link(PPSCORE_REPO_LINK, "PPS")} ({score["model_score"]:.3f} {score["metric"]} with {score["baseline_score"]:.3f} baseline) """
    elif case == "predict_itself":
        return ""
    elif case == "feature_is_id":
        return f"""{score["x"]} cannot predict {score["y"]} because {score["x"]} is an ID column"""
    elif case == "target_is_id":
        return f"""{score["x"]} cannot predict {score["y"]} because {score["y"]} is an ID column"""
    elif case == "target_is_constant":
        return f"""{score["y"]} can always be predicted perfectly because it only has a single value"""
    else:
        return f"""{score["x"]} predicts {score["y"]} with {score["ppscore"]:.3f} {link(PPSCORE_REPO_LINK, "PPS")} ({score["case"]}) """


@embeddable_plain_async
def _model_score_html_statement(df, target, feature, **kwargs):
    """
    Returns the model score sentence as HTML.
    """

    score = pps.score(
        df,
        x=feature,
        y=target,
        random_seed=get_option("global.random_seed"),
        catch_errors=True,
    )

    if score["is_valid_score"]:
        return widgets.HTML(model_score_sentence(score))
    else:
        return widgets.HTML(
            (
                f"<p>We could not compute a score for '{feature}' predicting '{target}'</p>"
            )
        )


############################


class PredictorsList(AsyncEmbeddable):
    """
    Compute ppscores of all features identified by df_column_indices against the target and display
    the results in an interactive list of the predictors and their ppscores.
    If the user clicks on a predictor, display details (such univariate and bivariate plots)
    """

    def init_embeddable(self, df=None, target=None, df_column_indices=None, **kwargs):
        """
        :param df_column_indices: list with the indices of the columns for which you want to compute
            the ppscore.
        """

        progress_ = widgets.FloatProgress(value=0.0, min=0.0, max=1.0)
        self.set_content(progress_, self.loading)

        max_calculation_steps = len(df_column_indices)  # set number of calculations

        sorted_scores = []
        excluded_features = []
        for index, feature in enumerate(df_column_indices):
            if feature == target:
                continue
            score = pps.score(
                df=df,
                x=feature,
                y=target,
                random_seed=get_option("global.random_seed"),
                catch_errors=True,
            )
            if score["is_valid_score"]:
                sorted_scores.append(score)
            else:
                excluded_features.append(feature)

            progress_.value = index / max_calculation_steps

        sorted_scores.sort(key=lambda x: x["ppscore"], reverse=True)

        function_hint_ = get_function_hint(
            f"bam.predictors({DF_OLD}, target={string_to_code(target)})", **kwargs
        )

        if len(sorted_scores) >= 1:
            header = widgets.HTML(
                (
                    f"<h3>'{target}' is predicted with 1 feature</h3>"
                    f"""<p>Score metric: <b>{link(PPSCORE_REPO_LINK, "Predictive Power Score")}</b></p>"""
                )
            )
        else:
            header = widgets.HTML("It was not possible to calculate predictors.")

        result_children = [function_hint_, header]
        self.set_content(*result_children)

        for score in sorted_scores:
            result_children.append(
                create_dt_score_focus_row(
                    df, score["x"], score["ppscore"], target, **kwargs
                )
            )
            self.set_content(*result_children)

        if len(excluded_features) > 0:
            excluded_features = "</b>, <b>".join(excluded_features)
            excluded_features = f"<b>{excluded_features}</b>"
            message = f"It was not possible to calculate a score for the following columns: {excluded_features}"
            result_children.append(widgets.HTML(message))
        self.set_content(*result_children)


@high_level_function
@user_exposed_function
@catch_empty_df
@embeddable_plain_blocking
def predictors(df, target, **kwargs):
    """
    Interactive widget that shows a columns selector and the PredictorsList() for the given target
    and columns (i.e. features) selection
    """
    # Attention: the ColumnsReducer should only filter features and not the target column
    features_df = df.head(10).drop(columns=[target])

    def render_list(df_column_indices):
        target_and_feature_columns = [target] + list(df_column_indices)
        return PredictorsList(
            df, target, df_column_indices=target_and_feature_columns, **kwargs
        )

    output = ColumnsReducer(
        df=features_df, max_columns=100, on_render=render_list, **kwargs
    )
    return output


def _scores_for_pp_scores_heatmap_(df, df_column_indices=None, progress=None, **kwargs):
    """
    Given a list of columns names specified in df_column_indices, computes all pairwise ppscores in
    dataset df.

    :param df_column_indices: list of indices or column names corresponding to the columns in df for
        which you want to compute the pairwise ppscores.

    :return: list of dicts. Each dict contains the target name and scores of all features.
    """

    heatmap_scores = []

    for index, target in enumerate(df_column_indices):
        scores = pp_score_features(
            df, target, **kwargs
        )  # dont insert progress because this is 1 level too deep

        summary_scores = []
        for column in df_column_indices:
            col_score = [score for score in scores if score["feature"] == column][0]
            summary_scores.append(col_score)

        heatmap_scores.append({"target": target, "scores": summary_scores})

        if progress is not None:
            progress.value = index / len(df_column_indices)
    return heatmap_scores


def _coordinates_for_pp_scores_heatmap_(
    df, heatmap_scores, df_column_indices=None, **kwargs
):
    """
    Helper function.

    Given a heatmap of ppscores and column names of the dataset df for which ppscores where computed,
    produce the x, y, and z labels for the heatmap.

    :param heatmap_scores: list of dicts. Each dict contains the target name and ppscores of all features.
    :param df_column_indices: list of indices or column names corresponding to the columns in df for
        which the ppscores where computed.

    :return: list with all dimensions of the heatmap for direct displaying.
    """

    heatmap_z = []
    for target_scores in heatmap_scores:
        row = []
        for feature_score in target_scores["scores"]:
            row.append(feature_score["score"])
        heatmap_z.append(row)
    heatmap_z.reverse()

    x = [column for column in df_column_indices]
    y = [column for column in df_column_indices]
    y.reverse()
    return x, y, heatmap_z


########################################
### layout components for toggleable deep dive button
########################################


def create_toggle_output(button_name, lazy_widget_old, style="secondary", **kwargs):
    """
    A button that displays a widget beneath it when the user clicks on it.

    :param button_name: string that contains the name of the button.
    :param lazy_widget_old: a lazy loaded widget.
    :param style: css style of the button.

    Example:
    create_toggle_output(
        "Summary of Age",
        new_lazy_widget_decorator(
            plot, df_titanic, "Age",
        )
    )
    """

    def create_activatable_button(
        deactive_description, deactive_callback, active_description, active_callback
    ):
        def click_button(button):
            # here I cannot use local immutable variables from the parent function eg active = False
            # I need to use reference-style like the callbacks OR a list. Using active = [False] would work
            if button.description == deactive_description:
                deactive_callback()
                button.description = active_description
            else:
                active_callback()
                button.description = deactive_description

        return Button(
            description=deactive_description,
            style=style,
            icon="search",  # 'info', 'search' https://fontawesome.com/icons?d=gallery&q=search
            on_click=click_button,
        ).add_class("bamboolib-width-200px")

    lazy_widget_old_outlet, callback = lazy_widget_old
    # List needed because open_details() changes it from different scope
    already_loaded = [False]

    toggable_outlet = widgets.HBox([])

    def open_details():
        toggable_outlet.children = [lazy_widget_old_outlet]
        if not already_loaded[0]:
            callback()
            already_loaded[0] = True

    def close_details():
        toggable_outlet.children = []

    button = create_activatable_button(
        f"show {button_name}", open_details, f"hide {button_name}", close_details
    )
    return button, toggable_outlet


def create_dt_score_focus_row(
    df, feature, score, target, df_manager, parent_tabs, **kwargs
):
    """
    Create a button that opens details about "x predicts y with score z" in a new tab.
    """

    label = widgets.HTML(f"{score:.3f} using '{feature}'").add_class(
        "bamboolib-width-300px"
    )

    from bamboolib.viz import RelateColumns

    button = Button(
        description=f"show details",
        icon="external-link",
        on_click=lambda _: RelateColumns(
            x=feature, y=target, df_manager=df_manager, parent_tabs=parent_tabs
        ).render_in(parent_tabs),
    )

    return widgets.HBox([label, button])


########################################
### pairwise column comparison
########################################


@embeddable_with_outlet_blocking  # https://plot.ly/python/heatmaps/
def bivariate_scores_heatmap(
    x,
    y,
    heatmap_z,
    colorscale=PATTERNS_HEATMAP_COLORSCALE,
    zmin=None,
    zmax=None,
    df=None,
    compare_outlet=None,
    outlet=None,
    loading=None,
    x_axis_title="features",
    y_axis_autorange=None,
    **kwargs,
):
    """
    The interactive ppscore heatmap figure widget
    """

    trace = go.Heatmap(
        x=x,
        y=y,
        z=heatmap_z,
        colorscale=colorscale,
        zmin=zmin,
        zmax=zmax,
        reversescale=False,
    )
    layout = go.Layout(
        xaxis=dict(title=x_axis_title, type="category"),
        yaxis=dict(autorange=y_axis_autorange, type="category"),
        autosize=True,
        height=300,
        margin=go.layout.Margin(
            ## problem that the labels are outside the plot or above the axis-title
            # https://github.com/plotly/plotly.js/issues/296
            # l=100,  # this needs to be adjusted based on the max lengths of the labels
            # r=20,
            # b=20,
            t=30,
            # pad=100
        ),
        **PLOTLY_BACKGROUND,
    )
    figure = go.FigureWidget(data=[trace], layout=layout)

    def handle_click(trace, points, state):
        compare_outlet.children = [get_loading_widget()]
        feat = str(points.ys[0])
        target = str(points.xs[0])
        compare_outlet.children = [plot(df, target, feat, **kwargs)]

    figure.data[0].on_click(handle_click)

    outlet.children = [figure]
    return outlet


@log_function
@user_exposed_function
@catch_empty_df
@embeddable_plain_blocking
def bivariate_plot(df, col_a=None, col_b=None, **kwargs):
    """
    A compound widget that lets the user specify which two columns she wants to plot. We choose the
    plot based on the two columns data types.
    """

    function_hint_ = get_function_hint(f"bam.bivariate_plot({DF_OLD})", **kwargs)
    if col_a is not None:
        function_hint_ = get_function_hint(
            f"bam.bivariate_plot({DF_OLD}, '{col_a}')", **kwargs
        )
        if col_b is not None:
            function_hint_ = get_function_hint(
                f"bam.bivariate_plot({DF_OLD}, {string_to_code(col_a)}, {string_to_code(col_b)})",
                **kwargs,
            )

    values = df.columns.tolist()
    if col_a is None:
        if col_b is None:
            col_a = values[0]
        else:
            col_a = [value for value in values if value != col_b][
                0
            ]  # in case someone gave col_b but not col_a
    if col_b is None:
        col_b = [value for value in values if value != col_a][0]

    comparison_outlet = widgets.VBox([])

    def update_comparison_outlet(col_a, col_b):
        widget, loading_callback = lazy_widget_old(compare, (df, col_a, col_b), kwargs)
        comparison_outlet.children = [widget]
        loading_callback()

    def create_dropdown(values, default):
        return Singleselect(
            value=default,
            options=values,
            placeholder="Choose column",
            width="md",
            set_soft_value=True,
        )

    dd_col_a = create_dropdown(values, col_a)
    dd_col_b = create_dropdown(values, col_b)

    def register_dropdown_callback(dropdown):
        def dropdown_changed(dropdown):
            update_comparison_outlet(dd_col_a.value, dd_col_b.value)

        dropdown.on_change(dropdown_changed)

    register_dropdown_callback(dd_col_a)
    register_dropdown_callback(dd_col_b)

    # initialize
    update_comparison_outlet(dd_col_a.value, dd_col_b.value)

    spacer = widgets.HTML("<br>")

    return (
        function_hint_,
        widgets.HBox(
            [widgets.HTML("Plot").add_class("bamboolib-width-40px"), dd_col_a]
        ).add_class("bamboolib-overflow-visible"),
        widgets.HBox(
            [widgets.HTML("and").add_class("bamboolib-width-40px"), dd_col_b]
        ).add_class("bamboolib-overflow-visible"),
        spacer,
        comparison_outlet,
    )


class PPScoreHeatmap(AsyncEmbeddable):
    """
    Given a selection of columns in a dataset df, show the pairwise ppscores of the columns in an
    interactive heatmap.
    """

    def init_embeddable(self, df=None, df_column_indices=None, **kwargs):
        """
        :param df_column_indices: list of column indices or column names specifying which columns to
            show in the heatmap
        """

        progress_ = widgets.FloatProgress(value=0.0, min=0.0, max=1.0)
        self.set_content(progress_, self.loading)

        compare_outlet = widgets.VBox()

        scores = _scores_for_pp_scores_heatmap_(
            df, df_column_indices=df_column_indices, progress=progress_
        )
        x, y, z = _coordinates_for_pp_scores_heatmap_(
            df, scores, df_column_indices=df_column_indices
        )
        heatmap = bivariate_scores_heatmap(
            x, y, z, df=df, compare_outlet=compare_outlet, **kwargs
        )

        title = widgets.HTML(
            (
                f"Each cell shows the <b>{link(PPSCORE_REPO_LINK, 'Predictive Power Score')}</b> "
                "of the feature on the x axis for the target on the y axis."
            )
        )
        compare_outlet.children = [
            notification("Click on a heatmap cell to inspect the relationship")
        ]

        self.set_content(title, heatmap, compare_outlet)


@high_level_function
@user_exposed_function
@catch_empty_df
@embeddable_plain_async
def patterns(df, *args, **kwargs):
    """
    Top-level function for displaying a ppscore heatmap. Lets user select columns for which she
    wants to create a ppscore heatmap and then creates and renders the heatmap.
    """

    function_hint_ = get_function_hint(f"bam.patterns({DF_OLD})", **kwargs)

    heatmap = ColumnsReducer(
        df=df,
        max_columns=100,
        on_render=lambda df_column_indices: PPScoreHeatmap(
            df, df_column_indices=df_column_indices, **kwargs
        ),
        render_content_after_init=False,
        **kwargs,
    )

    return (function_hint_, heatmap)


@embeddable_with_outlet_blocking
def correlation_heatmap(
    df, df_column_indices=None, compare_outlet=None, outlet=None, loading=None, **kwargs
):
    """
    An interactive figure widget showing the pairwise correlations for all columns in df_column_indices
    as a heatmap.
    """

    def maybe_sample_for_scores(df, **kwargs):
        if df.shape[0] > SAMPLE_FOR_SCORES:
            return df.sample(
                SAMPLE_FOR_SCORES, random_state=get_option("global.random_seed")
            )
        else:
            return df

    df_corr = (
        maybe_sample_for_scores(df)[df_column_indices]
        .corr()
        .dropna(axis=0, how="all")
        .dropna(axis=1, how="all")
    )
    x = df_corr.columns
    y = x
    z = df_corr

    heatmap = bivariate_scores_heatmap(
        x,
        y,
        z,
        zmin=-1,
        zmax=1,
        colorscale=CORRELATION_HEATMAP_COLORSCALE,
        df=df,
        compare_outlet=compare_outlet,
        x_axis_title="",
        y_axis_autorange="reversed",
        **kwargs,
    )

    outlet.children = [widgets.HTML("Pearson correlation"), heatmap]
    return outlet


@high_level_function
@user_exposed_function
@catch_empty_df
@embeddable_plain_async
def correlations(df, *args, **kwargs):
    """
    Top-level function for displaying a correlations heatmap. Lets user select columns for which she
    wants to create a correlations heatmap and then creates and renders the heatmap.
    """

    function_hint_ = get_function_hint(f"bam.correlations({DF_OLD})", **kwargs)

    compare_outlet = widgets.VBox([])

    df = df.select_dtypes("number")

    heatmap = ColumnsReducer(
        df=df,
        max_columns=100,
        columns_name="numeric columns",
        on_render=lambda df_column_indices: correlation_heatmap(
            df,
            df_column_indices=df_column_indices,
            compare_outlet=compare_outlet,
            **kwargs,
        ),
        **kwargs,
    )

    compare_outlet.children = [
        notification("Click on a heatmap cell to inspect the relationship")
    ]

    return function_hint_, heatmap, compare_outlet
