# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import pandas as pd
import numpy as np
import ipywidgets as widgets

from bamboolib.helper import Transformation, DF_OLD, BamboolibError
from bamboolib.helper import string_to_code

from bamboolib.widgets.selectize import Singleselect
from bamboolib.widgets import Text

from bamboolib.transformations.base_components import SelectorGroupMixin, SelectorMixin

FIXED_NUMBER_OF_BINS = "A fixed number of bins"
FIXED_INTERVAL_BINS = "Fixed-interval bins"
CUSTOM_INTERVAL_BINS = "Custom, named intervals"
QUANTILE_BINS = "Quantile bins"

DEFAULT_LABELS = "Default labels"
RANGE_LABELS = "Custom Range labels, e.g. (0, 1]"
ASCENDING_COUNT_LABELS = "Ascending count, e.g. 1, 2, ..."
DESCENDING_COUNT_LABELS = "Descending count, e.g. 10, 9, ..."

LOWER_BOUND_INCLUSIVE = "Lower bound inclusive, e.g. [0, 1)"
UPPER_BOUND_INCLUSIVE = "Upper bound inclusive, e.g. (0, 1]"


class LabelOption(widgets.VBox):
    """
    Interface for the bin label option.
    """

    def __init__(self, transformation, *args, focus_after_init=False, **kwargs):
        """
        :param focus_after_init: boolean. If True, then set the cursor focus to the (first) input
            element being rendered in LableOption.
        """
        super().__init__(*args, **kwargs)
        self.transformation = transformation
        self.focus_after_init = focus_after_init

    def get_label_kwargs(self):
        """
        Return the kwargs used by the bin function. Will be pasted to the other kwargs, so make sure
        to prefix it with ", ".

        :returns: string. E.g. ", bins=10".
        """
        raise NotImplementedError


class Empty(LabelOption):
    """
    Class used if no label options are required, e.g. when uses chooses to go with the default bin
    labels.
    """

    def get_label_kwargs(self):
        return ""


class RangePrecision(LabelOption):
    """
    Let's the user set the bin label precision when a fixed number of bins with custom range
    labels is chosen.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.precision = Text(
            description="Bin label precision",
            value="3",
            focus_after_init=self.focus_after_init,
            width="lg",
            execute=self.transformation,
        )

        self.children = [self.precision]

    def get_label_kwargs(self):
        return f", precision={self.precision.value}"


class DescendingCount(LabelOption):
    """
    Let's the user set the number of the first bin when the bins are numbered in descending order.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.min_count = Text(
            description="Start counting at",
            placeholder="Min count",
            value="1",
            focus_after_init=self.focus_after_init,
            execute=self.transformation,
        )

        self.children = [self.min_count]

    def get_label_kwargs(self):
        min_ = int(self.min_count.value) - 1
        bin_count = int(self.transformation.bin_provider.get_bin_count())
        max_ = bin_count + min_
        return f", labels=np.arange({max_}, {min_}, -1)"


class AscendingCount(LabelOption):
    """
    Let's the user set the number of the first bin when the bins are numbered in ascending order.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.min_count = Text(
            description="Start counting at",
            placeholder="Min count",
            value="1",
            focus_after_init=self.focus_after_init,
            execute=self.transformation,
        )

        self.children = [self.min_count]

    def get_label_kwargs(self):
        bin_count = self.transformation.bin_provider.get_bin_count()
        bin_count = int(bin_count) + 1
        min_ = int(self.min_count.value)
        max_ = min_ + bin_count - 1
        return f", labels=np.arange({min_}, {max_}, 1)"


LABEL_CONFIGURATIONS = {
    DEFAULT_LABELS: Empty,
    RANGE_LABELS: RangePrecision,
    ASCENDING_COUNT_LABELS: AscendingCount,
    DESCENDING_COUNT_LABELS: DescendingCount,
}


class LabelConfiguration(widgets.VBox):
    """
    Manages the label configuration and renders the corresponding LableOption.
    """

    def __init__(self, transformation, focus_after_init=False):
        super().__init__()
        self.transformation = transformation

        self.labels_type = Singleselect(
            options=[
                DEFAULT_LABELS,
                RANGE_LABELS,
                ASCENDING_COUNT_LABELS,
                DESCENDING_COUNT_LABELS,
            ],
            placeholder="Label style",
            set_soft_value=True,
            width="lg",
            on_change=self.update_config_option,
        )

        self.config_outlet = widgets.HBox()
        self.update_config_option(focus_after_init=False)

        self.children = [self.labels_type, self.config_outlet]

    def update_config_option(self, *args, focus_after_init=True):
        """Depending on the selected label configuration, render the correct LableOption."""
        self.config_option = LABEL_CONFIGURATIONS[self.labels_type.value](
            self.transformation, focus_after_init=focus_after_init
        )
        self.config_outlet.children = [self.config_option]

    def get_label_kwargs(self):
        return self.config_option.get_label_kwargs()


class CutLimitsConfiguration(widgets.VBox):
    """
    Configuration object that handles whether the lower or upper bound of each bin is inclusive.
    Example: If lower bound is inclusive, then bins are of the form [a, b).
    """

    def __init__(self, transformation):
        super().__init__()
        self.transformation = transformation

        self.dropdown = Singleselect(
            options=[UPPER_BOUND_INCLUSIVE, LOWER_BOUND_INCLUSIVE],
            placeholder="Bin cutting style",
            set_soft_value=True,
            width="lg",
        )

        self.children = [self.dropdown]

    def get_bin_cut_kwargs(self, consider_lowest=True):
        """Return the functional argument as a string. Used in the exported code."""
        maybe_include_lowest = ""
        if consider_lowest:
            maybe_include_lowest = ", include_lowest=True"

        if self.dropdown.value == UPPER_BOUND_INCLUSIVE:  # (0, 1]
            return f"{maybe_include_lowest}"  # right=True
        else:
            return ", right=False"  # [0, 1) - include_lowest is redundant


class BinProvider(widgets.VBox):
    """
    Interface for the type of binning, e.g. fixed number of bins, quantile bins, etc.
    """

    def __init__(self, transformation, *args, focus_after_init=False, **kwargs):
        """
        :param transformation: the transformation object that has a reference to all components in the
            binning UI. Via transformation, we can e.g. access kwargs code from a LableOption object.
        """
        super().__init__(*args, **kwargs)
        self.transformation = transformation
        self.focus_after_init = focus_after_init

    def get_code(self):
        """
        Return the full binning code by assembling the kwargs.
        """
        raise NotImplementedError

    def get_bin_count(self):
        """
        The number of bins produced as a result. Note than LableOptions are accessing this method
        to produce the right kwargs codes.
        """
        raise NotImplementedError


class NumberOfBinsBinning(BinProvider):
    """Creates the final code when "fixed number of bins" is selected."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.number_of_bins = Text(
            placeholder="Number of bins, e.g. 10",
            focus_after_init=self.focus_after_init,
            width="lg",
            execute=self.transformation,
        )

        self.children = [self.number_of_bins]

    def get_code(self):
        column = self.transformation.column_selector.value
        bins = self.number_of_bins.value
        bin_cut = self.transformation.get_bin_cut_kwargs(consider_lowest=False)
        labels = self.transformation.label_config.get_label_kwargs()

        return (
            f"pd.cut({DF_OLD}[{string_to_code(column)}], bins={bins}{bin_cut}{labels})"
        )

    def get_bin_count(self):
        return self.number_of_bins.value


class FixedIntervalBinning(BinProvider):
    """Creates the final code when "fixed-interval bins" is selected."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.bin_width = Text(
            description="Bin width",
            placeholder="Bin width, e.g. 10",
            focus_after_init=True,
            width="lg",
            execute=self.transformation,
        )

        self.min_value = Text(
            description="Min value, empty for MIN(column)",
            placeholder="Min value, optional",
            execute=self.transformation,
        )

        self.max_value = Text(
            description="Max value, empty for MAX(column)",
            placeholder="Max value, optional",
            execute=self.transformation,
        )

        self.children = [self.bin_width, self.min_value, self.max_value]

    def _get_range_code(self):
        if self.bin_width.value == "":
            raise BamboolibError(
                "The bin width is empty.<br>Please specify the bin width"
            )

        min_value = self.min_value.value
        if min_value == "":
            min_value = self.transformation.get_series().min()
        else:
            # why do we need eval here? and this might fail easily, no?
            min_value = eval(min_value)

        max_value = self.max_value.value
        if max_value == "":
            max_value = self.transformation.get_series().max()
        else:
            # why do we need eval here? and this might fail easily, no?
            max_value = eval(max_value)

        limits = list(
            eval(f"np.arange({min_value}, {max_value}, {self.bin_width.value})")
        )
        if max_value not in limits:
            limits.append(max_value)

        return f"{limits}"

    def get_code(self):
        column = self.transformation.column_selector.value
        bins = self._get_range_code()
        bin_cut = self.transformation.get_bin_cut_kwargs()
        labels = self.transformation.label_config.get_label_kwargs()

        return (
            f"pd.cut({DF_OLD}[{string_to_code(column)}], bins={bins}{bin_cut}{labels})"
        )

    def get_bin_count(self):
        bin_count = len(eval(self._get_range_code())) - 1
        return str(bin_count)


class Interval(SelectorMixin, widgets.HBox):
    """Helper class for creating bin intervals."""

    def __init__(self, *args, transformation=None, focus_after_init=False, **kwargs):
        super().__init__(*args, **kwargs)

        self.from_ = Text(
            placeholder="From",
            focus_after_init=focus_after_init,
            width="xxs",
            execute=transformation,
        )

        self.to_ = Text(placeholder="To", width="xxs", execute=transformation)

        self.label = Text(placeholder="Label", width="sm", execute=transformation)

        self.children = [self.from_, self.to_, self.label, self.delete_selector_button]

    def get_interval(self):
        """Get the interval bordes."""
        if self.from_.value == "" or self.to_.value == "":
            raise BamboolibError(
                "There is an empty interval limit.<br>Please specify all interval limits"
            )
        return (eval(self.from_.value), eval(self.to_.value))

    def get_label(self):
        """Get the interval label. E.g. a user can label interval [18, 100) as 'adults'."""
        if self.label.value == "":
            raise BamboolibError(
                "There is an empty interval label.<br>Please specify all interval labels"
            )
        return self.label.value


class CustomIntervalBinning(SelectorGroupMixin, BinProvider):
    """Creates the final code when "Custom, named intervals" is selected."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.init_selector_group(add_button_text="add interval")

        self.children = [self.selector_group, self.add_selector_button]

    def create_selector(self, show_delete_button=None, focus_after_init=True, **kwargs):
        return Interval(
            transformation=self.transformation,
            selector_group=self,
            focus_after_init=focus_after_init,
            show_delete_button=show_delete_button,
        )

    def _ensure_labels_are_valid(self, labels):
        if len(set(labels)) != len(labels):
            raise BamboolibError(
                "There are currently duplicate interval labels.<br>Please make sure that all interval labels are unique"
            )

    def get_code(self):
        column = self.transformation.column_selector.value

        intervals = [selector.get_interval() for selector in self.get_selectors()]
        bins = f"pd.IntervalIndex.from_tuples({intervals})"

        bin_cut = self.transformation.get_bin_cut_kwargs()

        labels_list = [selector.get_label() for selector in self.get_selectors()]
        self._ensure_labels_are_valid(labels_list)
        labels = f".cat.rename_categories({labels_list})"

        return (
            f"pd.cut({DF_OLD}[{string_to_code(column)}], bins={bins}{bin_cut}){labels}"
        )


class QuantileBinning(BinProvider):
    """Creates the final code when "Quantile Bins" is selected."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.number_of_quantiles = Text(
            description="Number of quantiles",
            placeholder="Quantiles, e.g. 10",
            focus_after_init=True,
            width="lg",
            execute=self.transformation,
        )

        self.children = [self.number_of_quantiles]

    def get_code(self):
        column = self.transformation.column_selector.value
        quantiles = self.number_of_quantiles.value
        labels = self.transformation.label_config.get_label_kwargs()

        return f"pd.qcut({DF_OLD}[{string_to_code(column)}], q={quantiles}{labels})"

    def get_bin_count(self):
        return self.number_of_quantiles.value


BIN_PROVIDERS = {
    FIXED_NUMBER_OF_BINS: NumberOfBinsBinning,
    FIXED_INTERVAL_BINS: FixedIntervalBinning,
    CUSTOM_INTERVAL_BINS: CustomIntervalBinning,
    QUANTILE_BINS: QuantileBinning,
}


class BinColumn(Transformation):
    """The actual transformation object that handles the whole binning process."""

    def __init__(self, *args, column=None, **kwargs):
        super().__init__(*args, **kwargs)

        focus_column = column is None
        focus_binning = not focus_column

        self.column_selector = Singleselect(
            options=list(self.get_df().columns),
            placeholder="Choose column",
            value=column,
            focus_after_init=focus_column,
            set_soft_value=True,
            width="lg",
            on_change=lambda dropdown: self.set_column(dropdown.value),
        )

        self.binning_type = Singleselect(
            options=list(BIN_PROVIDERS.keys()),
            placeholder="Choose bin type",
            set_soft_value=True,
            focus_after_init=focus_binning,
            width="lg",
            on_change=self.update_bin_provider,
        )

        self.bin_outlet = widgets.HBox()

        self.label_outlet = widgets.VBox()
        self.label_config = LabelConfiguration(self)

        self.cut_limits_outlet = widgets.VBox()
        self.cut_limits_config = CutLimitsConfiguration(self)

        self.bin_provider = None

        self.update_bin_provider(focus_after_init=False)
        self.set_column(self.column_selector.value)

    def get_bin_cut_kwargs(self, **kwargs):
        return self.cut_limits_config.get_bin_cut_kwargs(**kwargs)

    def get_series(self):
        return self.get_df()[self.column_selector.value]

    def update_bin_provider(self, *args, focus_after_init=True, **kwargs):
        self.bin_provider = BIN_PROVIDERS[self.binning_type.value](
            self, focus_after_init=focus_after_init
        )
        self.bin_outlet.children = [self.bin_provider]
        self._update_label_outlet()
        self._update_cut_limits_outlet()

    def _update_label_outlet(self):
        if self.binning_type.value == CUSTOM_INTERVAL_BINS:
            self.label_outlet.children = []
        else:
            self.label_outlet.children = [widgets.HTML("with"), self.label_config]

    def _update_cut_limits_outlet(self):
        if self.binning_type.value == QUANTILE_BINS:
            self.cut_limits_outlet.children = []
        else:
            self.cut_limits_outlet.children = [
                widgets.HTML("and make"),
                self.cut_limits_config,
            ]

    def render(self):
        self.set_title("Bin column")
        self.set_content(
            self.column_selector,
            widgets.HTML("into"),
            self.binning_type,
            self.bin_outlet,
            self.label_outlet,
            self.cut_limits_outlet,
            self.rename_column_group,
        )

    def get_description(self):
        return f"<b>Bin column</b>"

    def get_code(self):
        return f"{DF_OLD}[{string_to_code(self.new_column_name_input.value)}] = {self.bin_provider.get_code()}"
