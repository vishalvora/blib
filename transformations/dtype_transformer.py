# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

# LATER: add more dtype options - https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.DataFrame.astype.html


import pandas as pd
import numpy as np
import ipywidgets as widgets

from pandas.api.types import is_datetime64_any_dtype, is_bool_dtype

from bamboolib.helper import Transformation, DF_OLD, log_error, notification, VSpace
from bamboolib.helper import string_to_code

from bamboolib.widgets import Singleselect, Text


DATETIME_FORMAT_HELP_TEXT = """
<u>Format string examples:</u> <a href='https://docs.python.org/3/library/datetime.html#strftime-and-strptime-behavior' target='_blank' class='bamboolib-link'>(see full documentation)</a><br>
<ul>
    <li>2020-12-30 23:59:59 &minus; %Y-%m-%d %H:%M:%S</li>
    <li>Sunday 27 December 2020, UTC &minus; %A %d %B %Y, %z</li>
    <li>Sun 27 Dec 20, 11 AM, -0400 &minus; %a %d %b %y, %I %p, %z</li>
</ul>
"""


class NoOptionsEmbeddable(widgets.VBox):
    """
    Basically an empty embeddable when no options are required by BulkChangeDatatype.
    """

    def get_kwargs(self):
        """
        Return the kwargs that shall be displayed in the final code export, e.g.
        {"format": "YYYY-mm-dd", infer_datetime_format: True}

        :return: kwargs dict.
        """
        return {}


class HTMLEmbeddable(widgets.VBox):
    """
    An Embeddable that only display some HTML

    Example usage: when the user selects the special selector in the dropdown, we tell him that this
    is not a valid option to choose.
    """

    def __init__(self, html="", **kwargs):
        super().__init__()
        self.html = html
        self.children = [widgets.HTML(self.html)]

    def get_kwargs(self):
        return {"html": self.html}


class DatetimeOptionsEmbeddable(widgets.VBox):
    """
    Embeddable for showing options when casting columns to datetime of from datetime to string.
    """

    def __init__(self, focus_after_init=False, transformation=None, **kwargs):
        super().__init__()

        self.string_format_text = Text(
            value="",
            placeholder="Format string (optional)",
            focus_after_init=focus_after_init,
            width="lg",
            execute=transformation,
        )

        format_link = widgets.HTML(DATETIME_FORMAT_HELP_TEXT)

        self.children = [self.string_format_text, format_link]

    def get_kwargs(self):
        kwargs = {}
        if self.string_format_text.value:
            kwargs["format"] = self.string_format_text.value
        else:
            kwargs["infer_datetime_format"] = True
        return kwargs


class DatetimeToStringOptionsEmbeddable(DatetimeOptionsEmbeddable):
    """Options shown when casting from datetime to string."""

    def get_kwargs(self):
        kwargs = {}
        if self.string_format_text.value:
            kwargs["date_format"] = self.string_format_text.value
        return kwargs


ADVANCED_SECTION_SEPARATOR = "advanced section separator"


class DefaultHandler:
    """
    Base class for casting data types. Inherit from DefaultHandler for specifing cases.

    :param default_code_template: string. The code template used.
    """

    default_code_template = "TO BE OVERRIDEN"

    def __init__(self, column, source_dtype, has_na):
        self.column = column
        self.source_dtype = source_dtype
        self.has_na = has_na

        self.embeddable_kwargs = {}

    def kwargs_to_string(self, kwargs):
        """
        Takes a kwarg dict and returns its items as a functional arguments string.

        For example, {"a": 1, "b": "foo"} becomes "a=1, b='foo'"
        """
        result = []
        for key, value in kwargs.items():
            if isinstance(value, bool):
                value_string = str(value)
            elif isinstance(value, str):
                value_string = f"'{value}'"
            else:
                continue
            result.append(f"{key}={value_string}")
        return ", ".join(result)

    def get_options_embeddable(self):
        """The options embedabble to use. Override if you need a specific option embeddable."""
        return NoOptionsEmbeddable

    def get_code(self, option_section, *args, **kwargs):
        """
        Returns the transformation code displayed to the user.

        :param option_section: object. The options Embeddanle that has a get_wargs() method.
            E.g. DatetimeToStringOptionsEmbeddable
        """
        kwargs = self.kwargs_to_string(option_section.get_kwargs())
        return self.__class__.default_code_template % (
            string_to_code(self.column),
            kwargs,
        )


class ToString(DefaultHandler):
    """Handles casting data type to string."""

    def get_options_embeddable(self):
        if is_datetime64_any_dtype(self.source_dtype):
            return DatetimeToStringOptionsEmbeddable
        return NoOptionsEmbeddable

    def get_code(self, option_section):
        date_format = option_section.get_kwargs().get("date_format", "")
        if is_datetime64_any_dtype(self.source_dtype) and date_format != "":
            return self._get_datetime_code(date_format=date_format)
        else:
            return f"{DF_OLD}[{string_to_code(self.column)}].astype('string')"  # pandas > 1.1.x
            # return f"pd.Series({DF_OLD}['{self.column}'].apply(str), dtype='string')"  # pandas 1.0.x < 1.1
            # # old syntax pre pandas 1.0 which does not work from int to str any more
            # # maybe they will make the API consistent later on:
            # https://github.com/pandas-dev/pandas/issues/35174
            # return f"{DF_OLD}['{self.column'].astype(str)"  # old syntax does not work any more in panas

    def _get_datetime_code(self, date_format):
        return f"{DF_OLD}[{string_to_code(self.column)}].dt.strftime('{date_format}')"


class ToNullableInt(DefaultHandler):
    """
    Supports casting to integer columns containing NAs. Note that this class expects the bit-size
    of the integer you want to convert to.

    :param bit_size: integer. Bit-size of the integer you want to convert to.
    """

    bit_size = "TO BE OVERRIDDEN"

    def get_code(self, option_section, *args, **kwargs):
        kwargs = self.kwargs_to_string(option_section.get_kwargs())

        if self.has_na:
            # Note that we need quotes around Int here!
            return f"{DF_OLD}[%s].astype('Int{self.__class__.bit_size}'%s)" % (
                string_to_code(self.column),
                kwargs,
            )
        else:
            return f"{DF_OLD}[%s].astype('int{self.__class__.bit_size}'%s)" % (
                string_to_code(self.column),
                kwargs,
            )


class ToInt64(DefaultHandler):
    # Plays a special role as this class is used as a default integer in the UI (selection "Integer")
    # It supports a downcast to smaller memory size but also nullable ints
    def get_code(self, option_section, *args, **kwargs):
        kwargs = self.kwargs_to_string(option_section.get_kwargs())

        if self.has_na:
            return f"{DF_OLD}[%s].astype('Int64'%s)" % (
                string_to_code(self.column),
                kwargs,
            )
        elif is_bool_dtype(self.source_dtype):
            return f"{DF_OLD}[%s].astype(int%s)" % (string_to_code(self.column), kwargs)
        else:
            return (
                f"pd.to_numeric({DF_OLD}[%s], downcast='integer', errors='coerce'%s)"
                % (string_to_code(self.column), kwargs)
            )


class ToInt32(ToNullableInt):
    bit_size = 32


class ToInt16(ToNullableInt):
    bit_size = 16


class ToInt8(ToNullableInt):
    bit_size = 8


class ToUnsignedInt64(DefaultHandler):
    default_code_template = f"{DF_OLD}[%s].astype('uint64'%s)"


class ToUnsignedInt32(DefaultHandler):
    default_code_template = f"{DF_OLD}[%s].astype('uint32'%s)"


class ToUnsignedInt16(DefaultHandler):
    default_code_template = f"{DF_OLD}[%s].astype('uint16'%s)"


class ToUnsignedInt8(DefaultHandler):
    default_code_template = f"{DF_OLD}[%s].astype('uint8'%s)"


class ToFloat64(DefaultHandler):
    default_code_template = (
        f"pd.to_numeric({DF_OLD}[%s], downcast='float', errors='coerce'%s)"
    )


class ToFloat32(DefaultHandler):
    default_code_template = f"{DF_OLD}[%s].astype('float32'%s)"


class ToFloat16(DefaultHandler):
    default_code_template = f"{DF_OLD}[%s].astype('float16'%s)"


class ToBool(DefaultHandler):
    default_code_template = f"{DF_OLD}[%s].astype(bool%s)"


class ToCategory(DefaultHandler):
    default_code_template = f"{DF_OLD}[%s].astype('category'%s)"


class ToObject(DefaultHandler):
    default_code_template = f"{DF_OLD}[%s].astype('object'%s)"


class ToDatetime(DefaultHandler):
    default_code_template = (
        f"pd.to_datetime({DF_OLD}[%s], %s)"  # infer_datetime_format=True,
    )

    def get_options_embeddable(self):
        return DatetimeOptionsEmbeddable


class ToTimedelta(DefaultHandler):
    default_code_template = f"pd.to_timedelta({DF_OLD}[%s]%s)"


class AdvancedSection(DefaultHandler):
    """
    Handler for representing our separator in the dropdown.

    Maybe becomes obsolete when we can disable special items in the dropdown from the frontend.
    """

    def __init__(self, column, source_dtype, *args, **kwargs):
        super().__init__(column, source_dtype, *args, **kwargs)
        self.embeddable_kwargs = {
            "html": "<b>This is a separator. Please select another data type</b>"
        }

    def get_options_embeddable(self):
        return HTMLEmbeddable


DTYPE_TRANSFORMATION = {
    "string": {"name": "String/Text", "handler": ToString},
    "int64": {"name": "Integer", "handler": ToInt64},
    "float64": {"name": "Float", "handler": ToFloat64},
    "bool": {"name": "Boolean", "handler": ToBool},
    "category": {"name": "Categorical/Factor", "handler": ToCategory},
    "datetime64[ns]": {"name": "Datetime", "handler": ToDatetime},
    "timedelta64[ns]": {"name": "Timedelta", "handler": ToTimedelta},
    ADVANCED_SECTION_SEPARATOR: {
        "name": "---- advanced options ----",
        "handler": AdvancedSection,
    },
    "object": {"name": "Object", "handler": ToObject},
    "int32": {"name": "Integer (32-bit)", "handler": ToInt32},
    "int16": {"name": "Integer (16-bit)", "handler": ToInt16},
    "int8": {"name": "Integer (8-bit)", "handler": ToInt8},
    "float32": {"name": "Float (32-bit)", "handler": ToFloat32},
    "float16": {"name": "Float (16-bit)", "handler": ToFloat16},
    "uint64": {"name": "Unsigned integer (64-bit)", "handler": ToUnsignedInt64},
    "uint32": {"name": "Unsigned integer (32-bit)", "handler": ToUnsignedInt32},
    "uint16": {"name": "Unsigned integer (16-bit)", "handler": ToUnsignedInt16},
    "uint8": {"name": "Unsigned integer (8-bit)", "handler": ToUnsignedInt8},
}
DTYPE_CHOICES = [
    (DTYPE_TRANSFORMATION[key]["name"], key) for key in DTYPE_TRANSFORMATION.keys()
]


def has_na(series: pd.Series) -> bool:
    return series.isnull().values.any()


class DtypeSelector(widgets.VBox):
    """
    Handles the datatype selection and the respective options embeddable that needs to be displayed
    depending on the data type the user wants to cast to.
    """

    def __init__(self, transformation, df, column, target_dtype, focus_after_init=True):
        super().__init__()
        self.transformation = transformation
        self.df = df
        self.column = column
        self.target_dtype = target_dtype

        self.has_na = has_na(df[column])
        self.old_column_dtype = df[column].dtype

        if not str(self.old_column_dtype) in DTYPE_TRANSFORMATION.keys():
            log_error(
                "missing feature",
                self,
                f"unavailable column dtype: {self.old_column_dtype}",
            )

        self.dropdown = Singleselect(
            options=DTYPE_CHOICES,
            set_soft_value=True,
            focus_after_init=focus_after_init,
            width="md",
            on_change=lambda widget: self._update_options_section(
                focus_after_init=True
            ),
        )
        # DTYPE_CHOICES is a list of tuples, so we cannot set value=self.target_dtype
        # in Singleselect
        self.dropdown.value = self.target_dtype

        self._update_options_section(focus_after_init=False)

    def _update_options_section(self, focus_after_init=None):
        """Depending on the chosen datatype, find and display the correct options section."""
        HandlerClass = DTYPE_TRANSFORMATION[self.dropdown.value]["handler"]
        self.dtype_change_handler = HandlerClass(
            column=self.column, source_dtype=self.old_column_dtype, has_na=self.has_na
        )

        embeddable = self.dtype_change_handler.get_options_embeddable()
        embeddable_kwargs = self.dtype_change_handler.embeddable_kwargs

        self.option_section = embeddable(
            transformation=self.transformation,
            focus_after_init=focus_after_init,
            **embeddable_kwargs,
        )
        if self.target_dtype:
            self.children = [
                widgets.HTML(
                    f"<b>{DTYPE_TRANSFORMATION[self.target_dtype]['name']}</b>"
                ),
                self.option_section,
            ]
        else:
            self.children = [self.dropdown, self.option_section]

    def get_description(self):
        dtype_name = DTYPE_TRANSFORMATION[self.dropdown.value]["name"]
        return f"<b>Change data type</b> of {self.column} to {dtype_name}"

    def get_code(self):
        return self.dtype_change_handler.get_code(self.option_section)

    def get_metainfos(self):
        from_ = self.old_column_dtype
        to_ = self.dropdown.value
        return {
            f"dtype_change_from_{from_}": True,
            f"dtype_change_to_{to_}": True,
            "dtype_change_pair": f"{from_} to {to_}",
        }


class DtypeTransformer(Transformation):
    """Change the data type of a single column.

    :param target_dtype: Allows presetting the data type to cast the column to.
    """

    target_dtype = None  # TO BE OVERRIDDEN
    modal_title = "Change data type"

    def __init__(self, *args, column=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.column = column
        focus_dtype_after_init = True if column else False

        self.old_dtype_output = widgets.HTML()
        self.dtype_selector_wrapper = widgets.VBox()

        self._setup_column_header()
        self._update_old_dtype_output()
        self._update_dtype_selector(focus_after_init=focus_dtype_after_init)

    def _update_dtype_selector(self, focus_after_init=True):
        """Rerender DtypeSelector"""
        self.dtype_selector = DtypeSelector(
            self,
            self.get_df(),
            self.column,
            target_dtype=self.__class__.target_dtype,
            focus_after_init=focus_after_init,
        )
        self.dtype_selector_wrapper.children = [self.dtype_selector]

    def _update_old_dtype_output(self):
        old_dtype = self.get_df()[self.column].dtype
        self.old_dtype_output.value = f"Old data type: <b>{str(old_dtype)}</b>"

    def _setup_column_header(self):
        if self.column is None:
            self.set_column(self.get_df().columns[0])

            def update_column(column_selector):
                self.set_column(column_selector.value)
                self._update_old_dtype_output()
                self._update_dtype_selector()

            self.column_selector = Singleselect(
                options=list(self.get_df().columns),
                focus_after_init=True,
                set_soft_value=True,
                placeholder="Choose column",
                width="lg",
                on_change=update_column,
            )

            self.column_header = widgets.VBox(
                [
                    widgets.HTML("Change data type of column"),
                    self.column_selector,
                    widgets.HTML("to"),
                ]
            )
        else:
            self.new_column_name_input.value = self.column
            self.column_header = widgets.VBox(
                [self.old_dtype_output, widgets.HTML(f"Change '{self.column}' to")]
            )

    def render(self):
        self.set_title(self.__class__.modal_title)
        self.set_content(
            notification(
                """Want to change data types of multiple columns at once? Please use the <b>Bulk change data types</b> transformation.""",
                type="info",
            ),
            VSpace("md"),
            self.column_header,
            self.dtype_selector_wrapper,
            self.rename_column_group,
        )

    def is_valid_transformation(self):
        return self.dtype_selector.dropdown.value != ADVANCED_SECTION_SEPARATOR

    def get_description(self):
        return self.dtype_selector.get_description()

    def get_code(self):
        return f"{DF_OLD}[{string_to_code(self.new_column_name_input.value)}] = {self.dtype_selector.get_code()}"

    def get_metainfos(self):
        return self.dtype_selector.get_metainfos()

    """
    Functions to set inputs programatically. Used for unit testing.
    """

    def test_set_column_name(self, column_name):
        self.column_selector.value = column_name

    def test_set_target_dtype(self, target_dtype):
        self.dtype_selector.dropdown.value = target_dtype

    def test_set_string_format(self, string_format):
        self.dtype_selector.option_section.string_format_text.value = string_format


"""
Children of DtypeTransformer which allow to open e.g. "to Integer" from the search bar.
"""


class ToIntegerTransformer(DtypeTransformer):
    target_dtype = "int64"
    modal_title = "To Integer"


class ToInteger32Transformer(DtypeTransformer):
    target_dtype = "int32"
    modal_title = "To Integer (32-bit)"


class ToInteger16Transformer(DtypeTransformer):
    target_dtype = "int16"
    modal_title = "To Integer (16-bit)"


class ToInteger8Transformer(DtypeTransformer):
    target_dtype = "int8"
    modal_title = "To Integer (8-bit)"


class ToUnsignedIntegerTransformer(DtypeTransformer):
    target_dtype = "uint64"
    modal_title = "To Unsigned Integer"


class ToUnsignedInteger32Transformer(DtypeTransformer):
    target_dtype = "uint32"
    modal_title = "To Unsigned Integer (32-bit)"


class ToUnsignedInteger16Transformer(DtypeTransformer):
    target_dtype = "uint16"
    modal_title = "To Unsigned Integer (16-bit)"


class ToUnsignedInteger8Transformer(DtypeTransformer):
    target_dtype = "uint8"
    modal_title = "To Unsigned Integer (8-bit)"


class ToFloatTransformer(DtypeTransformer):
    target_dtype = "float64"
    modal_title = "To Float"


class ToFloat32Transformer(DtypeTransformer):
    target_dtype = "float32"
    modal_title = "To Float (32-bit)"


class ToFloat16Transformer(DtypeTransformer):
    target_dtype = "float16"
    modal_title = "To Float (16-bit)"


class ToBoolTransformer(DtypeTransformer):
    target_dtype = "bool"
    modal_title = "To Boolean"


class ToCategoryTransformer(DtypeTransformer):
    target_dtype = "category"
    modal_title = "To Category"


class ToStringTransformer(DtypeTransformer):
    target_dtype = "string"
    modal_title = "To Text/String"


class ToObjectTransformer(DtypeTransformer):
    target_dtype = "object"
    modal_title = "To Object"


class ToDatetimeTransformer(DtypeTransformer):
    target_dtype = "datetime64[ns]"
    modal_title = "To Datetime"


class ToTimedeltaTransformer(DtypeTransformer):
    target_dtype = "timedelta64[ns]"
    modal_title = "To Timedelta"
