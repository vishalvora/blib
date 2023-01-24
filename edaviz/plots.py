# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


from bamboolib.edaviz.constants import *

from bamboolib.edaviz.base import embeddable_plain_blocking
from bamboolib.edaviz.utils import value_counts

import numpy as np
import plotly.graph_objs as go


def maybe_expand_value_counts(subset_value_count, total_value_count):
    """
    The subset_value_count series needs to have all indices that total_value_count has
    If an index does not exist, the value should be filled with a 0
    """
    if subset_value_count.size == total_value_count.size:
        return subset_value_count
    else:
        total_df = total_value_count.to_frame(name="value")
        total_df["value"] = 0
        subset_df = subset_value_count.to_frame(name="value")
        total_df.update(subset_df)
        return total_df["value"]


@embeddable_plain_blocking
def mosaic_plot(df, x, y, **kwargs):
    """
    A figure widget for a mosaic plot (used to display two binary variables).
    """

    MAX_SHARE = 100
    FIGURE_MARGIN = 40

    df = df[[x, y]].dropna()
    x_series = df[x]
    y_series = df[y]

    x_counts = value_counts(x_series)
    # Causes ValueError if not list or np.array
    weights = list(MAX_SHARE * x_counts / np.sum(x_counts))

    y_counts = value_counts(y_series)

    def bar_x_values(weights):
        x_left_bar = weights[0] / 2
        x_right_bar = MAX_SHARE - weights[1] / 2
        return x_left_bar, x_right_bar

    subset_bars = []
    for y_class in y_counts.index:
        x_subset_counts = value_counts(x_series[y_series == y_class])
        x_subset_freqs = (MAX_SHARE * x_subset_counts / x_counts).fillna(0)

        bar = go.Bar(
            x=bar_x_values(weights),
            y=(x_subset_freqs).tolist(),
            orientation="v",
            opacity=BAR_OPACITY,
            name=str(y_class),
            width=weights,
            textfont=dict(family="Arial", size=11),
            marker=dict(line=dict(color="white", width=2)),
        )
        subset_bars.append(bar)

    data = subset_bars

    layout = go.Layout(
        barmode="stack",
        xaxis=dict(
            ticktext=x_counts.index, tickvals=data[0].x, title=x, range=[0, MAX_SHARE]
        ),
        yaxis=dict(
            tickvals=[""] * 2,
            ticksuffix="%",
            title=y,
            range=[0, MAX_SHARE],
            hoverformat=".1f",
        ),
        margin=go.layout.Margin(
            l=FIGURE_MARGIN, r=FIGURE_MARGIN, b=FIGURE_MARGIN, t=FIGURE_MARGIN, pad=0
        ),
        width=500,
        height=300,
        **PLOTLY_BACKGROUND,
    )

    return go.FigureWidget(data=data, layout=layout)


@embeddable_plain_blocking
def cat2_to_cat2_facet_bar_plot(df, x, y, **kwargs):
    """
    A bar plot of x, facetted by y.
    """

    df_notnull = df[[x, y]].dropna()

    x_series = df_notnull[x]
    y_series = df_notnull[y]

    x_counts = value_counts(x_series)
    y_counts = value_counts(y_series)

    left_y_series = y_series[x_series == x_counts.index[0]]
    right_y_series = y_series[x_series == x_counts.index[1]]

    left_y_counts = value_counts(left_y_series)
    right_y_counts = value_counts(right_y_series)

    left_y_bar = go.Bar(
        y=left_y_counts.index,
        x=left_y_counts,
        orientation="h",
        hoverinfo="x",
        opacity=BAR_OPACITY,
        name=str(
            x_counts.index[0]
        ),  # in case it is of type numpy.int64 (causing error)
    )
    right_y_bar = go.Bar(
        y=right_y_counts.index,
        x=right_y_counts,
        orientation="h",
        hoverinfo="x",
        xaxis="x2",
        opacity=BAR_OPACITY,
        name=str(
            x_counts.index[1]
        ),  # in case it is of type numpy.int64 (causing error)
    )

    x_bar = go.Bar(
        x=x_counts.index,
        y=x_counts,
        yaxis="y2",
        xaxis="x3",
        opacity=BAR_OPACITY,
        hoverinfo="y",
        marker=dict(color=MARGINAL_DENSITY_COLOR),
    )
    y_bar = go.Bar(
        x=y_counts,
        y=y_counts.index,
        xaxis="x4",
        opacity=BAR_OPACITY,
        hoverinfo="x",
        marker=dict(color=MARGINAL_DENSITY_COLOR),
        orientation="h",
    )

    data = [left_y_bar, right_y_bar, x_bar, y_bar]

    layout = go.Layout(
        xaxis=dict(title=str(x_counts.index[0]), domain=[0, 0.35]),
        yaxis=dict(title=y, domain=[0, 0.7], type="category"),
        xaxis2=dict(title=str(x_counts.index[1]), domain=[0.35, 0.7], anchor="y"),
        yaxis2=dict(title="Count", domain=[0.73, 1], anchor="x3"),
        xaxis3=dict(
            title=x,
            side="top",
            domain=[0, 0.7],
            anchor="y2",
            tickvals=["", ""],  # remove group label on xaxis
        ),
        xaxis4=dict(title="Count", domain=[0.73, 1], anchor="y"),
        bargap=0.1,
        showlegend=False,
        height=MULTIPLOT_FIGURE_HEIGHT,
        **PLOTLY_BACKGROUND,
    )

    return go.FigureWidget(data=data, layout=layout)


@embeddable_plain_blocking
def cat2_to_cat10_ppplot(df, cat2, cat10, same_y_axis=False, **kwargs):
    df_notnull = df[[cat2, cat10]].dropna()

    cat10_series = df_notnull[cat10]
    cat2_series = df_notnull[cat2]

    cat2_counts = value_counts(cat2_series)
    cat10_counts = value_counts(cat10_series)

    axes = ["x1", "x2"]
    subset_bars = []

    for axis, cat2_class in zip(
        axes, cat2_counts.index
    ):  # ("x1", "group1"), ("x2", "group2")
        subset_counts = value_counts(cat10_series[cat2_series == cat2_class])
        subset_counts = maybe_expand_value_counts(subset_counts, cat10_counts)

        bar = go.Bar(
            y=subset_counts.index,
            x=subset_counts,
            orientation="h",
            opacity=BAR_OPACITY,
            name=str(cat2_class),
            xaxis=axis,
        )
        subset_bars.append(bar)

    cat2_bar = go.Bar(
        x=cat2_counts.index,
        y=cat2_counts,
        xaxis="x3",
        yaxis="y2",
        name="",
        opacity=BAR_OPACITY,
        marker=dict(color=MARGINAL_DENSITY_COLOR),
    )

    data = subset_bars + [cat2_bar]

    layout_left_xaxis = dict(title=str(cat2_counts.index[0]), domain=[0, 0.5])
    if same_y_axis:
        layout_left_xaxis["autorange"] = "reversed"

    layout = go.Layout(
        xaxis=layout_left_xaxis,
        yaxis=dict(title=cat10, domain=[0, 0.7], type="category"),
        xaxis2=dict(title=str(cat2_counts.index[1]), domain=[0.5, 1]),
        yaxis2=dict(title="Count", domain=[0.73, 1], anchor="x3"),
        xaxis3=dict(
            title=cat2,
            side="top",
            domain=[0, 1],
            anchor="y2",
            tickvals=["", ""],  # remove group label on xaxis
        ),
        bargap=0.2,
        showlegend=False,
        height=MULTIPLOT_FIGURE_HEIGHT,
        margin=go.Margin(t=40),
        **PLOTLY_BACKGROUND,
    )

    return go.FigureWidget(data=data, layout=layout)


@embeddable_plain_blocking
def stacked_bar_chart_sorted_by_x(df, x, y, **kwargs):
    """
    A stacked bar chart, where y is the group variable and x is on the x axis.
    """

    df = df[[x, y]].dropna()

    x_series = df[x]
    y_series = df[y]

    y_groups = value_counts(y_series).index
    x_total_counts = value_counts(x_series)

    subset_bars = []
    for y_group in y_groups:
        x_subset_counts = value_counts(x_series[y_series == y_group])
        # Maybe expand value counts to avoid stacking bugs (when initially rednering the chart and
        # when selecting groups using the color legend)
        x_subset_counts = maybe_expand_value_counts(x_subset_counts, x_total_counts)

        bar = go.Bar(
            x=x_subset_counts.index,
            y=x_subset_counts,
            orientation="v",
            opacity=BAR_OPACITY,
            name=str(y_group),
        )
        subset_bars.append(bar)

    layout = go.Layout(
        barmode="stack",
        hovermode="x",
        xaxis=dict(type="category", title=f"{x}"),
        yaxis={"title": f"{y}"},
        margin=go.layout.Margin(t=30),  # don't need that much space from top
        **PLOTLY_BACKGROUND,
    )

    fig = go.FigureWidget(data=subset_bars, layout=layout)
    return fig


@embeddable_plain_blocking
def cat10_to_cat10_ppplot(df, x, y, **kwargs):
    def transpose(matrix):
        return list(map(list, zip(*matrix)))

    df_notnull = df[[x, y]].dropna()

    x_series = df_notnull[x]
    y_series = df_notnull[y]

    x_counts = value_counts(x_series)
    y_counts = value_counts(y_series)

    heatmap_data = []
    for x_class in x_counts.index:
        subset_counts = value_counts(y_series[x_series == x_class])
        subset_counts = maybe_expand_value_counts(subset_counts, y_counts)
        subset_counts = subset_counts / np.sum(subset_counts)

        heatmap_data.append(list(subset_counts))

    heatmap = go.Heatmap(
        z=transpose(heatmap_data),
        x=x_counts.index,
        y=y_counts.index,
        xgap=HEATMAP_TILE_PADDING,
        ygap=HEATMAP_TILE_PADDING,
        hoverinfo="z",
        colorscale="Reds",
        showscale=False,
        # colorbar=dict(x=0, y=0, len=0.5) # it is not possible to have a horizontal color bar atm (https://github.com/plotly/plotly.js/issues/1244)
    )

    x_bar = go.Bar(
        x=x_counts.index,
        y=x_counts,
        yaxis="y2",
        name=x,
        hoverinfo="none",
        opacity=BAR_OPACITY,
        showlegend=False,
        marker=dict(color=MARGINAL_DENSITY_COLOR),
    )

    y_bar = go.Bar(
        y=y_counts.index,
        x=y_counts,
        orientation="h",
        yaxis="y3",
        xaxis="x3",
        opacity=BAR_OPACITY,
        name=y,
        showlegend=False,
        hoverinfo="none",
        marker=dict(color=MARGINAL_DENSITY_COLOR),
    )

    data = [heatmap, x_bar, y_bar]

    layout = go.Layout(
        xaxis=dict(type="category", title=x, domain=[0, 0.7]),
        yaxis=dict(type="category", title=y, domain=[0, 0.7]),
        yaxis2=dict(title="Count", anchor="x2", domain=[0.75, 1]),
        xaxis3=dict(title="Count", domain=[0.73, 1], anchor="y3"),
        yaxis3=dict(
            title=y, domain=[0, 0.7], anchor="x3", side="right", type="category"
        ),
        height=MULTIPLOT_FIGURE_HEIGHT,
        margin=go.layout.Margin(t=30),
        **PLOTLY_BACKGROUND,
    )

    return go.FigureWidget(data=data, layout=layout)


@embeddable_plain_blocking
def cat10_to_cat2_ppplot(df, cat10, cat2, **kwargs):
    df_notnull = df[[cat10, cat2]].dropna()

    cat10_series = df_notnull[cat10]
    cat2_series = df_notnull[cat2]

    cat10_counts = value_counts(cat10_series)
    cat2_counts = value_counts(cat2_series)

    subset_bars = []
    for cat2_class in cat2_counts.index:
        cat10_subset_counts = value_counts(cat10_series[cat2_series == cat2_class])
        cat10_subset_freqs = (100 * cat10_subset_counts / cat10_counts).fillna(0)

        bar = go.Bar(
            x=cat10_counts.index,
            y=cat10_subset_freqs,
            orientation="v",
            opacity=BAR_OPACITY,
            name=str(cat2_class),
        )
        subset_bars.append(bar)

    cat10_bar = go.Bar(
        x=cat10_counts.index,
        y=cat10_counts,
        yaxis="y2",
        name=cat10,
        opacity=BAR_OPACITY,
        showlegend=False,
        marker=dict(color=MARGINAL_DENSITY_COLOR),
    )

    cat2_bar = go.Bar(
        y=cat2_counts.index,
        x=cat2_counts,
        orientation="h",
        yaxis="y3",
        xaxis="x3",
        opacity=BAR_OPACITY,
        name=cat2,
        showlegend=False,
        marker=dict(color=MARGINAL_DENSITY_COLOR),
    )

    data = subset_bars + [cat10_bar, cat2_bar]

    layout = go.Layout(
        yaxis=dict(
            title=f"{cat2} (share in %)",
            domain=[0, 0.73],
            ticksuffix="%",
            hoverformat=".1f",
        ),
        xaxis=dict(title=cat10, domain=[0, 0.7], type="category"),
        yaxis2=dict(title="Count", anchor="x2", domain=[0.75, 1]),
        xaxis3=dict(title="Count", domain=[0.73, 1], anchor="y3"),
        yaxis3=dict(
            title=cat2, domain=[0, 0.7], anchor="x3", side="right", type="category"
        ),
        barmode="stack",
        bargap=0.2,
        legend=dict(orientation="h"),
        height=MULTIPLOT_FIGURE_HEIGHT,
        margin=go.layout.Margin(l=80, r=80, b=50, t=30),
        **PLOTLY_BACKGROUND,
    )

    return go.FigureWidget(data=data, layout=layout)
