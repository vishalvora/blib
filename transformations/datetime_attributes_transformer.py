# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from pandas.api.types import is_datetime64_any_dtype

from bamboolib.helper import (
    Transformation,
    list_to_string,
    DF_OLD,
    notification,
    BamboolibError,
)

from bamboolib.widgets.selectize import Multiselect, Singleselect

DATETIME_ATTRIBUTES = {
    "year": {
        "name": "year",
        "suffix": "year",
        "description": "Year, e.g. 2012",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.year",
    },
    "quarter": {
        "name": "quarter",
        "suffix": "quarter",
        "description": "Quarter, e.g. 4",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.quarter",
    },
    "month_number": {
        "name": "month number",
        "suffix": "month_number",
        "description": "Month number, e.g. 1 (January)",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.month",
    },
    "month_name": {
        "name": "month name",
        "suffix": "month_name",
        "description": "Month name, e.g. January",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.month_name()",
    },
    "week": {
        "name": "week",
        "suffix": "week",
        "description": "Week number, e.g. 50",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.week",
    },
    "dayofyear": {
        "name": "day of year number",
        "suffix": "dayofyear",
        "description": "Day of year, e.g. 351",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.dayofyear",
    },
    "dayofmonth": {
        "name": "day of month number",
        "suffix": "dayofmonth",
        "description": "Day of month, e.g. 30",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.day",
    },
    "dayofweek": {
        "name": "day of week number",
        "suffix": "dayofweek",
        "description": "Day of week, e.g. 0 (Monday)",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.dayofweek",
    },
    "weekday_name": {
        "name": "weekday name",
        "suffix": "weekday_name",
        "description": "Weekday name, e.g. Thursday",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.day_name()",
    },
    "hour": {
        "name": "hour",
        "suffix": "hour",
        "description": "Hour, e.g. 21",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.hour",
    },
    "minute": {
        "name": "minute",
        "suffix": "minute",
        "description": "Minute, e.g. 58",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.minute",
    },
    "second": {
        "name": "second",
        "suffix": "second",
        "description": "Second, e.g. 57",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.second",
    },
    "microsecond": {
        "name": "microsecond",
        "suffix": "microsecond",
        "description": "Microsecond",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.microsecond",
    },
    "nanosecond": {
        "name": "nanosecond",
        "suffix": "nanosecond",
        "description": "Nanosecond",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.nanosecond",
    },
    "is_leap_year": {
        "name": "is leap year",
        "suffix": "is_leap_year",
        "description": "is leap year, e.g. True",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.is_leap_year",
    },
    "is_year_start": {
        "name": "is year start",
        "suffix": "is_year_start",
        "description": "is year start, e.g. True",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.is_year_start",
    },
    "is_year_end": {
        "name": "is year end",
        "suffix": "is_year_end",
        "description": "is year end, e.g. True",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.is_year_end",
    },
    "is_quarter_start": {
        "name": "is quarter start",
        "suffix": "is_quarter_start",
        "description": "is quarter start, e.g. True",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.is_quarter_start",
    },
    "is_quarter_end": {
        "name": "is quarter end",
        "suffix": "is_quarter_end",
        "description": "is quarter end, e.g. True",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.is_quarter_end",
    },
    "is_month_start": {
        "name": "is month start",
        "suffix": "is_month_start",
        "description": "is month start, e.g. True",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.is_month_start",
    },
    "is_month_end": {
        "name": "is month end",
        "suffix": "is_month_end",
        "description": "is month end, e.g. True",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].dt.is_month_end",
    },
    "timestamp": {
        "name": "timestamp",
        "suffix": "timestamp",
        "description": "Timestamp, e.g. 1451606401",
        "code": f"{DF_OLD}['%s'] = {DF_OLD}['%s'].values.astype('int64') // 10 ** 9",
    },
}


class DatetimeAttributesTransformer(Transformation):
    """
    Create new column and get properties like year, quarter, month, week, weekday, day, hour, minute,
    second or timestamp from a datetime column.
    """

    def __init__(self, *args, column=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.column = column
        focus_selected_attributes = True if column else False

        df = self.get_df()
        self.datetime_columns = [
            column for column in df.columns if is_datetime64_any_dtype(df[column].dtype)
        ]

        self._maybe_setup_column_header()

        options = [
            {"label": value["description"], "value": key}
            for key, value in DATETIME_ATTRIBUTES.items()
        ]
        self.selected_attributes = Multiselect(
            options=options,
            placeholder="Choose attribute(s)",
            focus_after_init=focus_selected_attributes,
            width="lg",
        )

    def _maybe_setup_column_header(self):
        if self.column:
            self.header = widgets.HTML(f"From '{self.column}' extract")
        elif self.has_datetime_columns():
            self.column = self.datetime_columns[0]

            self.column_selector = Singleselect(
                options=self.datetime_columns,
                focus_after_init=True,
                placeholder="Choose column",
                set_soft_value=True,
                width="lg",
            )

            def update_column(selector):
                self.column = self.column_selector.value

            self.column_selector.on_change(update_column)

            self.header = widgets.VBox(
                [
                    widgets.HTML("From column"),
                    self.column_selector,
                    widgets.HTML("extract"),
                ]
            )

    def render(self):
        self.set_title("Datetime attributes")
        if self.has_datetime_columns():
            self.set_content(widgets.VBox([self.header, self.selected_attributes]))
        else:
            # LATER: allow this anyway? and implicitely convert the column to string? maybe show a warning?
            message = notification(
                "<b>Error:</b> Currently, the dataframe contains no columns with data type datetime",
                type="error",
            )
            # Attention: set content on outlet because we dont want to show an execute button
            self.outlet.set_content(message)

    def has_datetime_columns(self):
        return (self.column is not None) or len(self.datetime_columns) > 0

    def _transformation_code(self, attribute):
        new_column_name = f"{self.column}_{attribute['suffix']}"
        return attribute["code"] % (new_column_name, self.column)

    def is_valid_transformation(self):
        if len(self.selected_attributes.value) <= 0:
            raise BamboolibError(
                "You did not select an attribute that you want to extract.<br>Please choose at least one attribute"
            )
        return True

    def get_description(self):
        attribute_names = [
            DATETIME_ATTRIBUTES[id_]["name"] for id_ in self.selected_attributes.value
        ]
        attributes_list = list_to_string(attribute_names, quoted=False)
        return f"<b>Extract datetime attribute(s)</b> {attributes_list} from '{self.column}'"

    def get_code(self):
        codes = []
        for id_ in self.selected_attributes.value:
            attribute = DATETIME_ATTRIBUTES[id_]
            code = self._transformation_code(attribute)
            codes.append(code)
        return "\n".join(codes)
