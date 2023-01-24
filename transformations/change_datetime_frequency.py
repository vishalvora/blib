# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.helper import (
    Transformation,
    DF_OLD,
    DF_NEW,
    notification,
    collapsible_notification,
    VSpace,
)

from bamboolib.widgets import Singleselect, Text
from bamboolib.helper import string_to_code


CALCULATION_OPTIONS = [
    ("Keep values and fill with missings (FILL)", "asfreq()"),
    ("Forward fill (FILL)", "ffill()"),
    ("Backward fill (FILL)", "backfill()"),
    ("Resample with nearest value (FILL)", "nearest()"),
    ("Interpolate linearly (FILL)", "interpolate()"),
    ("Count non-missing values (AGG)", "count()"),
    ("Count rows in group (size) (AGG)", "size().to_frame(name='count')"),
    ("Number of unique values (AGG)", "nunique()"),
    ("Sum (AGG)", "sum()"),
    ("OHLC - Open High Low Close (AGG)", "ohlc()"),
    ("Mean/Average (AGG)", "mean()"),
    ("Median (AGG)", "median()"),
    ("Min (AGG)", "min()"),
    ("Max (AGG)", "max()"),
    ("First value (AGG)", "first()"),
    ("Last value (AGG)", "last()"),
    ("Standard deviation - std (AGG)", "std()"),
    ("Variance (AGG)", "var()"),
    ("Standard error of the mean - sem (AGG)", "sem()"),
    ("Product of all values (AGG)", "prod()"),
]


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


class ChangeDatetimeFrequency(Transformation):
    """
    EITHER expand a timeseries column and fill it with values OR group by and calculate aggregations
    (also known as: resample or expand grid). E.g. based on year, quarter, month, week, weekday, day,
    hour, minute, second calculate forward fill, backward fill, interpolation and more.
    """

    def __init__(self, *args, column=None, **kwargs):
        super().__init__(*args, **kwargs)

        df = self.get_df()
        datetime_columns = list(df.select_dtypes("datetime").columns)
        self._no_datetime_columns = len(datetime_columns) == 0
        # Singleselect will throw an error if there are no options
        if self._no_datetime_columns:
            return

        column_already_exists = column is not None

        self.datetime_column = Singleselect(
            placeholder="Datetime column",
            options=datetime_columns,
            value=column,
            set_soft_value=True,
            width="md",
            focus_after_init=(not column_already_exists),
        )

        self.frequency_amount = Text(
            value="1",
            placeholder="Amount of frequency",
            focus_after_init=column_already_exists,
            execute=self,
            width="xxs",
        )

        self.frequency_type = Singleselect(
            placeholder="Choose frequency",
            options=FREQUENCY_OPTIONS,
            set_soft_value=True,
            width="md",
        )

        self.calculation_dropdown = Singleselect(
            placeholder="Choose calculation",
            options=CALCULATION_OPTIONS,
            set_soft_value=True,
            width="xxl",
        )

    def render(self):
        self.set_title("Change datetime frequency")
        if self._no_datetime_columns:
            self.outlet.set_content(
                notification(
                    "This component needs a 'datetime' column but there is no column with type 'datetime' in your dataframe.<br>Please change the datatype of your target column to 'datetime'",
                    type="error",
                )
            )
        else:
            self.set_content(
                collapsible_notification(
                    "Explanation",
                    """
                    <p>
                        Imagine you have a dataset with two columns - the day <b>and</b> the total revenue for the day. Unfortunately, you have no observations (rows) for some days.<br>
                    </p>
                    <br>
                    <p>
                        Now, there are <b>two different use cases</b>:
                    </p>
                    <br>
                    1) Expand the timeseries and fill with values (FILL)
                    <ul>
                        <li>
                            e.g. forward fill or interpolate missing values to make sure that you have a row for each day
                        </li>
                    </ul>
                    2) Group by and calculate aggregated values (AGG)<br>
                    <ul>
                        <li>
                            e.g. calculate the weekly mean value<br>
                        </li>
                    </ul>
                    """,
                ),
                VSpace("md"),
                widgets.HTML("Change frequency of"),
                self.datetime_column,
                widgets.HTML("to new frequency"),
                widgets.HBox([self.frequency_amount, self.frequency_type]),
                widgets.HTML("and calculate"),
                self.calculation_dropdown,
                self.rename_df_group,
            )

    def get_exception_message(self, exception):
        if "cannot reindex from a duplicate axis" in str(exception):
            return notification(
                f"""You tried to apply a FILL calculation but this is not possible because the column <b>{self.datetime_column.value}</b> contains duplicate values when grouped by the frequency <b>{self.frequency_type.label}</b>.<br><br>
                Please try one of the following solutions:<br>
                1) choose an AGG calculation<br>
                2) choose a higher frequency<br>
                3) clean the datetime column from the duplicate values<br>""",
                type="error",
            )
        return None

    def get_description(self):
        return "Change datetime frequency"

    def get_code(self):
        frequency = f"{self.frequency_amount.value}{self.frequency_type.value}"
        column = self.datetime_column.value
        calculation = self.calculation_dropdown.value
        return f"{DF_NEW} = {DF_OLD}.set_index({string_to_code(column)}).resample('{frequency}').{calculation}.reset_index()"
        # Attention: use "set_index" instead of the "on" kwarg because it is more robust:
        # e.g. this works:   df2.set_index("ship_date").resample('1D').count().reset_index()
        # this throws error: df2.resample('1D', on='ship_date').count().reset_index()
