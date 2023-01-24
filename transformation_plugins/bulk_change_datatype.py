# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from pandas.api.types import is_datetime64_any_dtype

from bamboolib.plugins import TransformationPlugin, DF_OLD, DF_NEW, Singleselect, Text

from bamboolib.helper import log_error, string_to_code, AuthorizedPlugin
from bamboolib.transformations.columns_selector import ColumnsSelector
from bamboolib.transformations.dtype_transformer import DATETIME_FORMAT_HELP_TEXT

COLUMN_NAME_PLACEHOLDER = "column_name"


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

    def __init__(self, columns, source_dtype, has_na):
        self.columns = columns
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
        return self.__class__.default_code_template % (COLUMN_NAME_PLACEHOLDER, kwargs)


class ToString(DefaultHandler):
    """Handles casting data type(s) to string."""

    def get_options_embeddable(self):
        if is_datetime64_any_dtype(self.source_dtype):
            return DatetimeToStringOptionsEmbeddable
        return NoOptionsEmbeddable

    def get_code(self, option_section):
        date_format = option_section.get_kwargs().get("date_format", "")
        date_format = string_to_code(date_format)

        if is_datetime64_any_dtype(self.source_dtype) and date_format != "":
            return self._get_datetime_code(date_format=date_format)
        else:
            return f"""{DF_OLD}[{COLUMN_NAME_PLACEHOLDER}].astype('string')"""  # pandas > 1.1.x
            # return f"pd.Series({DF_OLD}['{self.columns}'].apply(str), dtype='string')"  # pandas 1.0.x < 1.1
            # # old syntax pre pandas 1.0 which does not work from int to str any more
            # # maybe they will make the API consistent later on:
            # https://github.com/pandas-dev/pandas/issues/35174
            # return f"{DF_OLD}['{self.columns'].astype(str)"  # old syntax does not work any more in panas

    def _get_datetime_code(self, date_format):
        """Helper that returns code for casting to string if the columns to cast are datetimes"""
        # dt.strftime() returns object dtype (pandas 1.1.2), so need to apply .astype('string') on top
        return f"{DF_OLD}[{COLUMN_NAME_PLACEHOLDER}].dt.strftime({date_format}).astype('string')"


class ToNullableInt(DefaultHandler):
    """
    Supports casting to integer columns containing NAs. Note that this class expects the bit-size
    of the integer you want to convert to.

    :param bit_size: integer. Bit-size of the integer you want to convert to.
    """

    bit_size = "TO BE OVERRIDDEN"

    def get_code(self, option_section, *args, **kwargs):
        kwargs = self.kwargs_to_string(option_section.get_kwargs())
        # We don't want to confuse non-techies with bit-sizes if they "just want to convert to integer"
        bit_size = "" if self.__class__.bit_size == 64 else self.__class__.bit_size

        if self.has_na:
            # Note that we need quotes around Int here!
            return f"{DF_OLD}[{COLUMN_NAME_PLACEHOLDER}].astype('Int{self.__class__.bit_size}'{kwargs})"
        else:
            return (
                f"{DF_OLD}[{COLUMN_NAME_PLACEHOLDER}].astype('int{bit_size}'{kwargs})"
            )


class ToInt64(ToNullableInt):
    bit_size = 64


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
    default_code_template = f"{DF_OLD}[%s].astype('float64'%s)"


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

    def __init__(self, columns, source_dtype, *args, **kwargs):
        super().__init__(columns, source_dtype, *args, **kwargs)
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


def has_na(df) -> bool:
    return df.isnull().values.any()


class DtypeSelector(widgets.VBox):
    """
    Handles the datatype selection and the respective options embeddable that needs to be displayed
    depending on the data type the user wants to cast to.
    """

    def __init__(self, transformation, df, columns):
        super().__init__()
        self.transformation = transformation
        self.df = df

        self.columns = columns if len(columns) > 0 else [df.columns[0]]

        def get_source_dtype(df, column_names):
            """Get the source data type of the selected columns."""
            unique_dtypes = df[column_names].dtypes.unique()
            if len(unique_dtypes) > 1:
                # Stable fix for all target data types if selected columns have multiple dtypes.
                return "string"
            else:
                return unique_dtypes[0]

        self.has_na = has_na(df[self.columns])
        self.old_column_dtype = get_source_dtype(self.df, self.columns)

        if not str(self.old_column_dtype) in DTYPE_TRANSFORMATION.keys():
            log_error(
                "missing feature",
                self,
                f"unavailable column dtype: {self.old_column_dtype}",
            )

        self.dropdown = Singleselect(
            options=DTYPE_CHOICES,
            set_soft_value=True,
            focus_after_init=False,
            width="md",
            on_change=lambda widget: self._update_options_section(
                focus_after_init=True
            ),
        )

        self._update_options_section(focus_after_init=False)

    def _update_options_section(self, focus_after_init=None):
        """Depending on the chosen datatype, find and display the correct options section."""
        HandlerClass = DTYPE_TRANSFORMATION[self.dropdown.value]["handler"]
        self.dtype_change_handler = HandlerClass(
            columns=self.columns, source_dtype=self.old_column_dtype, has_na=self.has_na
        )

        embeddable = self.dtype_change_handler.get_options_embeddable()
        embeddable_kwargs = self.dtype_change_handler.embeddable_kwargs

        self.option_section = embeddable(
            transformation=self.transformation,
            focus_after_init=focus_after_init,
            **embeddable_kwargs,
        )
        self.children = [self.dropdown, self.option_section]

    def get_description(self):
        dtype_name = DTYPE_TRANSFORMATION[self.dropdown.value]["name"]
        return f"<b>Change data type</b> of {self.columns} to {dtype_name}"

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


class BulkChangeDatatype(AuthorizedPlugin, TransformationPlugin):
    """
    The plugin for changing data types in bulk.
    """

    name = "Bulk change data types"
    description = "Change data types of multiple columns e.g. to boolean, to integer, to float, to string, to category, to datetime, to timedelta"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.old_dtype_output = widgets.HTML()
        self.dtype_selector_wrapper = widgets.VBox()

        self.new_column_name_suffix_input = Text(
            description="Suffix of new column name - empty for overwriting column(s)",
            value="",
            placeholder="Suffix of new column name(s)",
            execute=self,
            width="lg",
        )

        self.columns_input = ColumnsSelector(
            transformation=self,
            focus_after_init=True,
            set_all_columns_as_default=False,
            # ATTENTION: the on_change is needed for the toString dtype change
            # when the input columns are all datetimes then the toString should show conversion options
            # otherwise, it should not. Thus, the dtype_selector is dependent on the columns_input
            on_change=self._update_dtype_selector,
        )

        self.column_header = widgets.VBox(
            [
                widgets.HTML("Change data type of column(s)"),
                self.columns_input,
                widgets.HTML("to"),
            ]
        )

        self._update_dtype_selector()

    def _update_dtype_selector(self, *args, **kwargs):
        """Rerender DtypeSelector"""
        self.dtype_selector = DtypeSelector(
            transformation=self, df=self.get_df(), columns=self.columns_input.value
        )
        self.dtype_selector_wrapper.children = [self.dtype_selector]

    def render(self):
        self.set_title(self.__class__.name)
        self.set_content(
            self.column_header,
            self.dtype_selector_wrapper,
            self.new_column_name_suffix_input,
        )

    def is_valid_transformation(self):
        return self.dtype_selector.dropdown.value != ADVANCED_SECTION_SEPARATOR

    def get_description(self):
        return self.dtype_selector.get_description()

    def get_code(self):
        import textwrap

        suffix = string_to_code(self.new_column_name_suffix_input.value)
        if (
            self.new_column_name_suffix_input.value != ""
        ):  # suffix is never == "" after applying string_to_code on it
            column_name_code_with_suffix = f"{COLUMN_NAME_PLACEHOLDER} + {suffix}"
        else:
            column_name_code_with_suffix = COLUMN_NAME_PLACEHOLDER

        final_code = textwrap.dedent(
            f"""
            for {COLUMN_NAME_PLACEHOLDER} in {self.columns_input.get_columns_code()}:
                {DF_OLD}[{column_name_code_with_suffix}] = {self.dtype_selector.get_code()}
        """
        ).strip()

        return final_code

    def get_metainfos(self):
        return self.dtype_selector.get_metainfos()

    """
    Functions to set inputs programatically. Used for unit testing.
    """

    def test_set_column_names(self, column_names):
        self.columns_input.value = column_names

    def test_set_target_dtype(self, target_dtype):
        self.dtype_selector.dropdown.value = target_dtype

    def test_set_string_format(self, string_format):
        self.dtype_selector.option_section.string_format_text.value = string_format
