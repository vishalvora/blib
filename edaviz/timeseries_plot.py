# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


import ipywidgets as widgets
import pandas as pd
from pandas.api.types import is_numeric_dtype

import plotly.graph_objs as go
import plotly.express as px

from bamboolib.helper import notification, VSpace, execute_asynchronously
from bamboolib.widgets import Singleselect, Multiselect, Button, Text
from bamboolib.edaviz.base import AsyncEmbeddable, get_loading_widget


FREQUENCY_OPTIONS = [
    ("Day(s)", "D"),
    ("Business day(s) (weekday)", "B"),
    ("Hour(s)", "H"),
    # ("Business hour(s)", "BH"),
    ("Minute(s)", "min"),
    ("Second(s)", "S"),
    #
    ("Week(s)", "W"),
    ("Month(s) (start)", "MS"),
    ("Month(s) (end date)", "M"),
    # ("Business month(s) (start)", "BMS"),
    # ("Business month(s) (end date)", "BM"),
    # # Semi month: 15th (or other day_of_month) and calendar month
    ("Semi month(s) (start)", "SMS"),
    ("Semi month(s) (end date)", "SM"),
    ("Quarter(s) (start)", "QS"),
    ("Quarter(s) (end date)", "Q"),
    # ("Business quarter(s) (start)", "BQS"),
    # ("Business quarter(s) (end date)", "BQ"),
    ("Year(s) (start)", "AS"),
    ("Year(s) (end date)", "A"),
    # ("Business year(s) (start)", "BAS"),
    # ("Business year(s) (end date)", "BA"),
    #
    ("Millisecond(s)", "ms"),
    ("Microsecond(s)", "us"),
    ("Nanosecond(s)", "N"),
]

FREQUENCY_SECONDS = [
    ("Day(s)", 60 * 60 * 24),
    # the adjustment with 7/5 is a correction for calculating the weekdays in a month/year etc
    ("Business day(s) (weekday)", 60 * 60 * 24 * (7 / 5)),
    ("Hour(s)", 60 * 60),
    # ("Business hour(s)", "BH"),
    ("Minute(s)", 60),
    ("Second(s)", 1),
    #
    ("Week(s)", 60 * 60 * 24 * 7),
    ("Month(s) (start)", 60 * 60 * 24 * 7 * 30),
    ("Month(s) (end date)", 60 * 60 * 24 * 7 * 30),
    # ("Business month(s) (start)", "BMS"),
    # ("Business month(s) (end date)", "BM"),
    # # Semi month: 15th (or other day_of_month) and calendar month
    ("Semi month(s) (start)", 60 * 60 * 24 * 7 * 15),
    ("Semi month(s) (end date)", 60 * 60 * 24 * 7 * 15),
    ("Quarter(s) (start)", 60 * 60 * 24 * 7 * 30 * 6),
    ("Quarter(s) (end date)", 60 * 60 * 24 * 7 * 30 * 6),
    # ("Business quarter(s) (start)", "BQS"),
    # ("Business quarter(s) (end date)", "BQ"),
    ("Year(s) (start)", 60 * 60 * 24 * 7 * 30 * 12),
    ("Year(s) (end date)", 60 * 60 * 24 * 7 * 30 * 12),
    # ("Business year(s) (start)", "BAS"),
    # ("Business year(s) (end date)", "BA"),
    #
    ("Millisecond(s)", 1 / 1_000),
    ("Microsecond(s)", 1 / 1_000_000),
    ("Nanosecond(s)", 1 / 1_000_000_000),
]

THRESHOLD_FOR_THIN_BARS = 500
THRESHOLD_FOR_TOO_MANY_BARS = 5_000


def default_frequency(series: pd.Series, min_n_data_points: int = 20):
    """
    Determines the time frequency that results in the smallest number of data points larger than
    min_n_data_points (the larger the aggregation, the fewer data points).
    """

    SECONDS_PER_YEAR = 31557600  # 365.25 * 24 * 60 * 60
    SECONDS_PER_MONTH = 2629800  # 365.25 * 24 * 60 * 60 / 12
    SECONDS_PER_DAY = 86400
    SECONDS_PER_HOUR = 3600

    timedelta_in_seconds = (series.max() - series.min()).total_seconds()

    timedelta_in_years = timedelta_in_seconds / SECONDS_PER_YEAR
    if timedelta_in_years > min_n_data_points:
        return "AS"  # years

    timedelta_in_months = timedelta_in_seconds / SECONDS_PER_MONTH
    if timedelta_in_months > min_n_data_points:
        return "MS"  # months

    timedelta_in_days = timedelta_in_seconds / SECONDS_PER_DAY
    if timedelta_in_days > min_n_data_points:
        return "D"  # days

    timedelta_in_hour = timedelta_in_seconds / SECONDS_PER_HOUR
    if timedelta_in_hour > min_n_data_points:
        return "h"  # hours

    return "min"


def get_result_rows(series, frequency_amount, frequency_label):
    """
    Computes the number of bars we'd have to display.

    Example:
    get_result_rows(series, 3, "MS") computest the number of bars needed to display the time series
    grouped by every 3 months.

    :param frequency_label: For example "AS" for year.
    :type frequency_label: string
    :type frequency_amount: int
    """

    timedelta_in_seconds = (series.max() - series.min()).total_seconds()
    units_per_second = [
        item[1] for item in FREQUENCY_SECONDS if item[0] == frequency_label
    ][0]
    return int(timedelta_in_seconds / (frequency_amount * units_per_second))


class UnivariateTimeseriesPlot(AsyncEmbeddable):
    """
    Creates a (univariate) histogram for a datetime column.
    """

    def _init_gui(self):
        self.state["rendering"] = True

        self.notification_outlet = widgets.VBox()
        self.figure_outlet = widgets.VBox()

        self.frequency_amount = Text(
            value="1",
            placeholder="Amount of frequency",
            width="xxs",
            on_submit=lambda _: execute_asynchronously(self._start_calculation),
        )

        self.frequency_type = Singleselect(
            placeholder="Choose frequency",
            options=FREQUENCY_OPTIONS,
            value=self.state["default_frequency"],
            set_soft_value=True,
            width="md",
            on_change=lambda _: execute_asynchronously(self._start_calculation),
        )

        count_per = widgets.HTML("Count per")
        count_per.add_class("bamboolib-element-next-to-selectize")

        of_column = widgets.HTML(f"""of <b>{self.state["datetime_column"]}</b>""")
        of_column.add_class("bamboolib-element-next-to-selectize")

        frequency_line = widgets.HBox(
            [count_per, self.frequency_amount, self.frequency_type, of_column]
        )
        frequency_line.add_class("bamboolib-overflow-visible")

        self.set_content(
            widgets.HTML(
                f"""<h3>Distribution of '{self.state["datetime_column"]}'</h3>"""
            ),
            widgets.HBox(
                [
                    widgets.HTML(f"<b>Minimum:</b> {str(self.df[self.column].min())}"),
                    widgets.HTML("<div style='width: 24px'></div>"),
                    widgets.HTML(f"<b>Maximum:</b> {str(self.df[self.column].max())}"),
                    widgets.HTML("<div style='width: 24px'></div>"),
                    widgets.HTML(
                        f"<b>Difference:</b> {str(self.df[self.column].max() - self.df[self.column].min())}"
                    ),
                ]
            ),
            VSpace("xl"),
            frequency_line,
            self.notification_outlet,
            self.figure_outlet,
        )

    def _start_calculation(self):
        render_id = self.state["render_id"] + 1
        self.state["render_id"] = render_id

        self.notification_outlet.children = []
        self.figure_outlet.children = [get_loading_widget()] + self.spacer_list

        self.state["aborted_calculation"] = False

        try:
            frequency_amount = int(self.frequency_amount.value)
        except:
            self.frequency_amount.value = "1"
            frequency_amount = 1

        number_of_result_rows = get_result_rows(
            series=self.df[self.column],
            frequency_amount=frequency_amount,
            frequency_label=self.frequency_type.label,
        )
        if number_of_result_rows < THRESHOLD_FOR_TOO_MANY_BARS:
            self._finish_calculation(render_id)
        else:
            self.state["aborted_calculation"] = True
            self._update_outlets(render_id)

    def _finish_calculation(self, render_id):
        datetime_column = self.state["datetime_column"]
        temp_df = (
            self.df.set_index(datetime_column)
            .resample(f"{self.frequency_amount.value}{self.frequency_type.value}")
            .size()
            .to_frame(name="count")
            .reset_index()
        )

        if self.state["render_id"] != render_id:
            return

        frequency_prefix = (
            ""
            if int(self.frequency_amount.value) == 1
            else f"{int(self.frequency_amount.value)} "
        )

        figure = px.bar(
            temp_df,
            x=datetime_column,
            y="count",
            title=f"Count per {frequency_prefix}{self.frequency_type.label} of {datetime_column}",
        )
        figure_widget = go.FigureWidget(figure)
        self.state["figure_output"] = [figure_widget]

        number_of_bars = temp_df.shape[0]
        if number_of_bars > THRESHOLD_FOR_THIN_BARS:
            self.state["notification_output"] = [
                notification(
                    "The bars are hardly visible because the frequency is too high. Please zoom in the chart or lower the frequency.",
                    type="info",
                )
            ]
        else:
            self.state["notification_output"] = []

        if self.state["render_id"] != render_id:
            return

        self._update_outlets()

    def _update_outlets(self, render_id=None):
        if self.state["aborted_calculation"]:
            self.notification_outlet.children = []
            warning = notification(
                f"""
                The frequency is very high. Therefore, the calculation will take some time and the resulting graph might freeze your browser window.<br>
                You can either adjust the frequency, filter the data or calculate the result anyway.
                """,
                type="warning",
            )

            def calculate_anyway(button):
                self.state["aborted_calculation"] = False
                self._finish_calculation(render_id)

            button = Button(
                description="Calculate result anyway - let's see what my browser can handle",
                on_click=calculate_anyway,
            )

            self.figure_outlet.children = [warning, button] + self.spacer_list
        else:
            self.notification_outlet.children = self.state["notification_output"]
            self.figure_outlet.children = self.state["figure_output"]

    def init_embeddable(self, df, column, **kwargs):
        self.df = df
        self.column = column
        self.spacer_list = [widgets.HTML("<br>") for i in range(10)]

        frequency_symbol = default_frequency(df[column])
        self.state = {
            "render_id": 0,
            "datetime_column": column,
            "default_frequency": frequency_symbol,
            "aborted_calculation": False,
            # outputs
            "figure_output": [],
            "notification_output": [],
        }

        self._init_gui()
        self._start_calculation()


NUMERIC_AGGREGATION_OPTIONS = [
    ("Median", "median"),
    ("Mean/average", "mean"),
    ("Min", "min"),
    ("Max", "max"),
    ("Sum", "sum"),
    ("Count (size)", "size"),  # with missing values
    ("Count (excl. missings)", "count"),
    ("Number of unique values", "nunique"),
    # Distribution metrics
    ("Standard deviation - std", "std"),
    ("Variance", "var"),
    ("Standard error of the mean - sem", "sem"),
    ("Mean absolute deviation - mad", "mad"),
    ("Skew", "skew"),
]


CATEGORIC_AGGREGATION_OPTIONS = [
    ("Number of unique values", "nunique"),
    ("Count (size)", "size"),  # with missing values
    ("Count (excl. missings)", "count"),
    # ("First value", "first"),
    # ("Last value", "last"),
]


class BivariateTimeseriesPlot(AsyncEmbeddable):
    """
    A Plot object where x is a datetime and y is not a datetime (e.g. numeric or categorical).
    y is aggregated with the aggregation function specified by user and displayed over time at the
    selected frequency (e.g. months, years, quarters of x).
    """

    def _init_gui(self):
        self.state["rendering"] = True

        self.notification_outlet = widgets.VBox()
        self.figure_outlet = widgets.VBox()

        self.aggregations = Multiselect(
            placeholder="Choose aggregation",
            options=self.aggregations_options,
            value=[self.aggregations_options[0][1]],
            width="xl",
            on_change=lambda _: execute_asynchronously(self._start_calculation),
        )

        self.frequency_amount = Text(
            value="1",
            placeholder="Amount of frequency",
            width="xxs",
            on_submit=lambda _: execute_asynchronously(self._start_calculation),
        )

        self.frequency_type = Singleselect(
            placeholder="Choose frequency",
            options=FREQUENCY_OPTIONS,
            value=self.default_frequency,
            set_soft_value=True,
            width="md",
            on_change=lambda _: execute_asynchronously(self._start_calculation),
        )

        per_label = widgets.HTML(f"""per""")
        per_label.add_class("bamboolib-element-next-to-selectize")

        of_target_column_per = widgets.HTML(f"""of <b>{self.target_column}</b>""")
        of_target_column_per.add_class("bamboolib-element-next-to-selectize")

        of_datetime_column = widgets.HTML(f"""of <b>{self.datetime_column}</b>""")
        of_datetime_column.add_class("bamboolib-element-next-to-selectize")

        aggregation_line = widgets.HBox([self.aggregations, of_target_column_per])
        aggregation_line.add_class("bamboolib-overflow-visible")

        frequency_line = widgets.HBox(
            [per_label, self.frequency_amount, self.frequency_type, of_datetime_column]
        )
        frequency_line.add_class("bamboolib-overflow-visible")

        self.set_content(
            aggregation_line,
            frequency_line,
            self.notification_outlet,
            self.figure_outlet,
        )

    def _start_calculation(self):
        render_id = self.state["render_id"] + 1
        self.state["render_id"] = render_id

        self.notification_outlet.children = []
        if len(self.aggregations.value) > 0:
            self.figure_outlet.children = [get_loading_widget()] + self.spacer_list
        else:
            please_choose_an_aggregation = notification(
                f"""Please choose at least 1 aggregation e.g. 'mean' for <b>{self.target_column}</b>""",
                type="info",
            )
            self.figure_outlet.children = [
                please_choose_an_aggregation
            ] + self.spacer_list
            return

        self.state["aborted_calculation"] = False

        try:
            frequency_amount = int(self.frequency_amount.value)
        except:
            self.frequency_amount.value = "1"
            frequency_amount = 1

        number_of_result_rows = get_result_rows(
            series=self.df[self.datetime_column],
            frequency_amount=frequency_amount,
            frequency_label=self.frequency_type.label,
        )
        if number_of_result_rows < THRESHOLD_FOR_TOO_MANY_BARS:
            self._finish_calculation(render_id)
        else:
            self.state["aborted_calculation"] = True
            self._update_outlets(render_id)

    def _finish_calculation(self, render_id):
        temp_df = (
            self.df.set_index(self.datetime_column)
            .resample(f"{self.frequency_amount.value}{self.frequency_type.value}")
            .agg({self.target_column: self.aggregations.value})
        )
        temp_df.columns = [
            "_".join(multi_index) for multi_index in temp_df.columns.ravel()
        ]
        temp_df = temp_df.reset_index()
        # the frequency might result in missing values - e.g. 1 day per ship_date in sales dataset
        # if the graph has NAs this looks weird - thus we drop missings per default
        # later we might detect when we did this and show an option to the user that he might change that
        # alternatively, the user might also specify a fill value for the NAs
        # but this is so much configuration that the user might as well just create the graph herself then
        temp_df = temp_df.dropna()

        if self.state["render_id"] != render_id:
            return

        self.temp_df = temp_df

        columns = [
            column for column in temp_df.columns if str(column) != self.datetime_column
        ]
        figure = px.line(temp_df, x=self.datetime_column, y=columns)

        figure_widget = go.FigureWidget(figure)
        self.state["figure_output"] = [figure_widget]

        if self.state["render_id"] != render_id:
            return

        self._update_outlets()

    def _update_outlets(self, render_id=None):
        if self.state["aborted_calculation"]:
            self.notification_outlet.children = []
            warning = notification(
                f"""
                The frequency is very high. Therefore, the calculation will take some time and the resulting graph might freeze your browser window.<br>
                You can either adjust the frequency, filter the data or calculate the result anyway.
                """,
                type="warning",
            )

            def calculate_anyway(button):
                self.state["aborted_calculation"] = False
                self._finish_calculation(render_id)

            button = Button(
                description="Calculate result anyway - let's see what my browser can handle",
                on_click=calculate_anyway,
            )

            self.figure_outlet.children = [warning, button] + self.spacer_list
        else:
            self.notification_outlet.children = self.state["notification_output"]
            self.figure_outlet.children = self.state["figure_output"]

    def init_embeddable(self, df, datetime_column, target_column, **kwargs):
        self.df = df
        self.datetime_column = datetime_column
        self.target_column = target_column
        self.spacer_list = [widgets.HTML("<br>") for i in range(10)]

        if is_numeric_dtype(self.df[self.target_column].dtype):
            self.aggregations_options = NUMERIC_AGGREGATION_OPTIONS
        else:
            self.aggregations_options = CATEGORIC_AGGREGATION_OPTIONS

        frequency_symbol = default_frequency(df[datetime_column])
        self.default_frequency = frequency_symbol
        self.state = {
            "render_id": 0,
            "aborted_calculation": False,
            # outputs
            "figure_output": [],
            "notification_output": [],
        }

        self._init_gui()
        self._start_calculation()
