# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


# Constants
CATEGORICAL_WITH_HIGH_CARDINALITY_BREAKPOINT = 20

PPSCORE_REPO_LINK = "https://github.com/8080labs/ppscore"

# datetimes
PANDAS_DATETIME = "datetime64[ns]"

# colors
COLOR_GREEN = "#5fba7d"
COLOR_RED = "#d65f5f"
COLOR_BLUE_LIGHT = "#A1D8FF"
MARGINAL_DENSITY_COLOR = "#3C78D8"
CORRELATION_HEATMAP_COLORSCALE = [  # goes from red to blue
    [0, "rgb(151, 20, 38)"],
    [0.0526315789473684, "rgb(161, 44, 60)"],
    [0.105263157894737, "rgb(172, 69, 83)"],
    [0.157894736842105, "rgb(183, 94, 106)"],
    [0.210526315789474, "rgb(194, 118, 129)"],
    [0.263157894736842, "rgb(205, 143, 152)"],
    [0.315789473684211, "rgb(216, 168, 175)"],
    [0.368421052631579, "rgb(227, 193, 197)"],
    [0.421052631578947, "rgb(238, 217, 220)"],
    [0.473684210526316, "rgb(249, 242, 243)"],
    [0.526315789473684, "rgb(241, 244, 246)"],
    [0.578947368421053, "rgb(215, 222, 230)"],
    [0.631578947368421, "rgb(189, 200, 213)"],
    [0.684210526315789, "rgb(162, 178, 196)"],
    [0.736842105263158, "rgb(136, 156, 180)"],
    [0.789473684210526, "rgb(110, 135, 163)"],
    [0.842105263157895, "rgb(83, 113, 146)"],
    [0.894736842105263, "rgb(57, 91, 130)"],
    [0.947368421052632, "rgb(31, 69, 113)"],
    [1, "rgb(5, 48, 97)"],
]
PATTERNS_HEATMAP_COLORSCALE = [
    [0, "rgb(255, 255, 255)"],
    [0.0526315789473684, "rgb(249, 242, 243)"],
    [0.105263157894737, "rgb(244, 230, 232)"],
    [0.157894736842105, "rgb(238, 217, 220)"],
    [0.210526315789474, "rgb(233, 205, 209)"],
    [0.263157894736842, "rgb(227, 193, 197)"],
    [0.315789473684211, "rgb(222, 180, 186)"],
    [0.368421052631579, "rgb(216, 168, 175)"],
    [0.421052631578947, "rgb(211, 156, 163)"],
    [0.473684210526316, "rgb(205, 143, 152)"],
    [0.526315789473684, "rgb(200, 131, 140)"],
    [0.578947368421053, "rgb(194, 118, 129)"],
    [0.631578947368421, "rgb(189, 106, 117)"],
    [0.684210526315789, "rgb(183, 94, 106)"],
    [0.736842105263158, "rgb(178, 81, 95)"],
    [0.789473684210526, "rgb(172, 69, 83)"],
    [0.842105263157895, "rgb(167, 57, 72)"],
    [0.894736842105263, "rgb(161, 44, 60)"],
    [0.947368421052632, "rgb(156, 32, 49)"],
    [1, "rgb(151, 20, 38)"],
]

# plotly graph display
BAR_OPACITY = 0.8
DEFAULT_N_BINS = 10
HEATMAP_TILE_PADDING = 0.5
MULTIPLOT_FIGURE_HEIGHT = 500
MIN_N_BINS = 1
MIN_N_BINS_HEXBIN = 10
MAX_N_BINS = 100

PLOTLY_BACKGROUND = {"paper_bgcolor": "rgba(0,0,0,0)", "plot_bgcolor": "rgba(0,0,0,0)"}
