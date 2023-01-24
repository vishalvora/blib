# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


from bamboolib.edaviz.constants import *

from IPython.display import display

import textwrap
import ipywidgets as widgets
import numpy as np
import pandas as pd
import plotly.graph_objs as go


COLORS = {
    "error": ["#721c24", "#f8d7da", "#f5c6cb"],
    "info": ["#004085", "#cce5ff", "#b8daff"],
    "warning": ["#856404", "#fff3cd", "#ffeeba"],
    "success": ["#155724", "#d4edda", "#c3e6cb"],
    "light": ["#595959", "#efefef", "#e0e0e0"],
}


def link(href, label):
    return f"<a href='{href}' target='_blank' class='bamboolib-link'>{label}</a>"


def _get_bin_settings(series, n_bins):
    """
    Creates a description of how bins should be created by plotly when e.g. plotting histogramms.

    :return: dict with the bin settings, i.e. the lower end of the first bin (start), the upper end
        of the last bin (end), and the bin size
    """

    hist_data = np.histogram(series, bins=n_bins)
    start = hist_data[1][0]
    bin_settings = dict(
        start=start,
        end=None,  # plotly uses largest value by default
        size=hist_data[1][1] - start,
    )

    return bin_settings


def create_bin_slider(
    n_bins,
    n_min_bins,
    n_max_bins,
    step=1,
    description="Max bins",
    readout=True,
    readout_format="d",
    orientation="vertical",
):

    slider = widgets.IntSlider(
        value=n_bins,
        min=n_min_bins,
        max=n_max_bins,
        step=step,
        description=description,
        readout=readout,
        readout_format=readout_format,
        orientation=orientation,
    )
    slider.add_class("bamboolib-slider")
    return slider


def _user_info_when_one_column_is_id(id_column_name):
    """
    Shows the user a message if she wants to create a bivariate plot where one column is an ID.
    """
    return widgets.HTML(
        textwrap.dedent(
            f"""<b>There are no reasonable visualizations because '{id_column_name}'
        seems like an ID.</b> This is because there are no duplicate values for
        '{id_column_name}'"""
        )
    )


def set_zero_to_nan(x: np.ndarray) -> np.ndarray:
    x_copy = x.copy()
    if np.any(x_copy == 0):
        x_copy[x_copy == 0] = np.nan
    return x_copy


def iqr(x):
    """Compute the inter quartile range of array x."""

    return np.subtract(*np.percentile(x, [75, 25]))


def _freedman_diaconis_bins(a):
    """
    Calculate number of hist bins using Freedman-Diaconis rule.

    Link: https://en.wikipedia.org/wiki/Freedman%E2%80%93Diaconis_rule
    """
    a = np.asarray(a)
    if len(a) < 2:
        return 1
    h = 2 * iqr(a) / (len(a) ** (1 / 3))
    # Fall back to sqrt(a) bins if IQR is 0
    if h == 0:
        return int(np.sqrt(a.size))
    else:
        return int(np.ceil((a.max() - a.min()) / h))


def _lower_bound(bin_) -> float:
    """Gets the lower bound of a string interval, e.g. if bin_ = "[10, 20)", returns 10."""
    return float(bin_.split(",")[0][1:])


def get_lower_bounds_of_bins(bins: np.array) -> np.array:
    return [_lower_bound(bin_) for bin_ in bins]


def value_counts(series):
    return (
        series.value_counts(dropna=True).sort_index()
        if series.dtype != "object"
        else series.astype(str).value_counts(dropna=True).sort_index()
    )


def get_heatmap_data(df_wide, frequencies=True):
    """
    Given a pivot table, extracts all features needed for plotting a heatmap (e.g. our hexbin plot)
    with marginal densities.

    These features are e.g.:
    - x_bins/y_bins (array of strings), e.g. ["[0, 10)", "[10, 20)", ...]
    - x_counts/y_counts (array of integers), the marginal absolute frequencies
    - heatmap_matrix_values (2darray of floats)

    :param df_wide: a pivot table (i.e. absolute frequency table)
    """
    heatmap_matrix_counts = df_wide.values
    x_counts = heatmap_matrix_counts.sum(axis=0)

    def replace_nan(x, how):
        x[np.isnan(x)] = how
        return x

    if frequencies:
        heatmap_matrix_values = replace_nan(heatmap_matrix_counts / x_counts, 0)
    else:
        heatmap_matrix_values = heatmap_matrix_counts

    y_counts = heatmap_matrix_counts.sum(axis=1)
    y_bins = df_wide.index.astype(str)
    x_bins = df_wide.columns.astype(str)
    # For plotly, we sometimes replace zeros in heatmap_matrix_values with np.nan (which is of type float).
    # This only works if values in heatmap_matrix_values are floats as well.
    heatmap_matrix_values = heatmap_matrix_values.astype(float)
    return x_bins, x_counts, y_bins, y_counts, heatmap_matrix_values


def compute_numeric_to_cat_heatmap_data(df, numeric, cat, n_bins):
    df["bin"] = pd.cut(df[numeric], n_bins, right=False, precision=1)

    df = df[["bin", cat]].dropna()
    df["n_obs"] = 1
    df_long = df.groupby(["bin", cat]).agg("sum").reset_index()
    df_wide = df_long.pivot(index="bin", columns=cat, values="n_obs").fillna(0).T

    (
        numeric_bins,
        numeric_counts,
        cat_classes,
        cat_counts,
        heatmap_matrix_freqs,
    ) = get_heatmap_data(df_wide)

    return numeric_bins, numeric_counts, cat_classes, cat_counts, heatmap_matrix_freqs


def compute_numeric_to_numeric_heatmap_data(df, x, y, n_bins, frequencies=True):
    if df.empty:
        return (
            np.array(["[0, 1)"]),
            np.array([0]),
            np.array(["[0, 1)"]),
            np.array([0]),
            np.array([[0.0]]),
        )

    df["bin_x"] = pd.cut(df[x], bins=n_bins[0], right=False, precision=1)
    df["bin_y"] = pd.cut(df[y], bins=n_bins[1], right=False, precision=1)

    df = df[["bin_x", "bin_y"]].dropna()
    df["count"] = 1
    df_long = df.groupby(["bin_x", "bin_y"]).agg("sum").reset_index()

    df_wide = df_long.pivot(index="bin_x", columns="bin_y", values="count").fillna(0).T

    x_bins, x_counts, y_bins, y_counts, heatmap_matrix_values = get_heatmap_data(
        df_wide, frequencies=frequencies
    )

    return x_bins, x_counts, y_bins, y_counts, heatmap_matrix_values


def heatmap_hovertext(x, y, z, x_label, y_label, z_label):
    hovertext = list()
    for yi, yy in enumerate(y):
        hovertext.append(list())
        for xi, xx in enumerate(x):
            hovertext[-1].append(
                f"{x_label}: {xx}<br />{y_label}: {yy}<br />{z_label}: {z[yi][xi]}"
            )
    return hovertext


def _update_count_figure_data(figure_data, x, y):
    figure_data.x = x
    figure_data.y = y


def _update_heatmap_figure_data(figure_data, x=None, y=None, z=None, hovertext=None):
    if not x is None:
        figure_data.x = x
    if not y is None:
        figure_data.y = y
    if not z is None:
        figure_data.z = z
    if not hovertext is None:
        figure_data.hovertext = hovertext


def create_numeric_heatmap_layout_with_marginal_densities(x, y):
    x_domain = [0, 0.7]
    y_domain = [0.76, 1]
    heatmap_axis = dict(domain=x_domain, showline=False, zeroline=False, showgrid=False)
    bar_x_axis = dict(title="", domain=x_domain, showticklabels=False)
    bar_y_axis = dict(title="Count", domain=y_domain)
    return go.Layout(
        xaxis=dict(title=x, **heatmap_axis),
        yaxis=dict(title=y, **heatmap_axis),
        xaxis2=dict(anchor="y2", **bar_x_axis),
        yaxis2=dict(anchor="x2", **bar_y_axis),
        xaxis3=dict(anchor="y3", **bar_y_axis),
        yaxis3=dict(anchor="x3", **bar_x_axis),
        bargap=0.01,
        height=MULTIPLOT_FIGURE_HEIGHT,
        margin=go.layout.Margin(t=30, r=10),
        **PLOTLY_BACKGROUND,
    )


def create_marginal_density_bar_chart(x, y, orientation, name, xaxis, yaxis):
    return go.Bar(
        x=x,
        y=y,
        orientation=orientation,
        opacity=BAR_OPACITY,
        showlegend=False,
        marker=dict(color=MARGINAL_DENSITY_COLOR),
        name=name,
        xaxis=xaxis,
        yaxis=yaxis,
    )
