# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import pandas as pd
import ipywidgets as widgets

from bamboolib.helper import (
    Transformation,
    DF_OLD,
    DF_NEW,
    BamboolibError,
    notification,
    string_to_code,
)

from bamboolib.widgets import Multiselect, Singleselect

from bamboolib.transformations.columns_selector import ColumnsSelector

from bamboolib.transformations.base_components import SelectorGroupMixin, SelectorMixin


# Based on reduction_kernels in /pandas/pandas/core/groupby/base.py.
# The list is resorted based on expected frequency of usage.
# 2 kernels (quantile and nth) are removed because they need an additional parameter
AGGREGATION_OPTIONS = [
    ("Count (size)", "size"),  # with missing values
    ("Count (excl. missings)", "count"),
    ("Sum", "sum"),
    ("Mean/Average", "mean"),
    ("Median", "median"),
    ("Min", "min"),
    ("Max", "max"),
    ("First value", "first"),
    ("Last value", "last"),
    ("Number of unique values", "nunique"),
    # distribution metrics
    ("Standard deviation - std", "std"),
    ("Variance", "var"),
    ("Standard error of the mean - sem", "sem"),
    ("Mean absolute deviation - mad", "mad"),
    ("Skew", "skew"),
    ("Group number - 0 to n", "ngroup"),
    ("All (boolean operator)", "all"),
    ("Any (boolean operator)", "any"),
    ("Index of max value", "idxmax"),
    ("Index of min value", "idxmin"),
    ("Product of all values", "prod"),
]
# there are other functions that return values on a different aggregation level
# ... those are helpful but cannot be mixed with the reduction kernels above
# eg rank
# eg cumcount - https://pandas.pydata.org/pandas-docs/version/0.17.0/generated/pandas.core.groupby.GroupBy.cumcount.html
# eg pct_change - https://pandas.pydata.org/pandas-docs/version/0.17.0/generated/pandas.core.groupby.DataFrameGroupBy.pct_change.html


class SimpleCalculation:
    """
    Handles simple aggregation code syntax of the form e.g. a_count=("a", "count").

    The simple syntax fails if the user chooses a column name that is not a valid kwarg key,
    e.g. "1 my col". In this case, we need a different (robust) syntax
    """

    def __init__(self, calculation_selector):
        self.selector = calculation_selector

    def has_valid_simple_syntax(self):
        """
        Check if the code syntax is valid, e.g.
        test(Pclass=("Survived", "count"))

        With simple calculation code, we can do the check with this hack because the code should always be
        of the form new_name=("column_name", "aggregation_function").
        """

        def test(**kwargs):
            pass

        try:
            exec(f"test({self.get_simple_aggregation_code()})", {}, {"test": test})
            return True
        except:
            return False

    def get_new_column_name(self):
        return self.selector.get_column() + f"_{self.selector.get_aggregation()}"

    def get_robust_aggregation_dict(self):
        """
        :return: dict, e.g. {"Pclass": ("Survived", "count")}
        """
        return {
            self.get_new_column_name(): (
                self.selector.get_column(),
                self.selector.get_aggregation(),
            )
        }

    def get_simple_aggregation_code(self):
        """
        :return: string, e.g. 'Pclass=("Survived", "count")'
        """
        new_name = self.get_new_column_name()
        return f"{new_name}=({string_to_code(self.selector.get_column())}, '{self.selector.get_aggregation()}')"


class SimpleCodeExporter:
    """
    Exports the aggregation code in simple syntax form if possible. If not possible, uses the robust
    aggregation syntax.
    """

    def __init__(self, calculations):
        self.calculations = calculations

    def _get_simple_aggregation_code(self):
        """Get the simple syntax of the aggregation code."""
        return ", ".join(
            [
                calculation.get_simple_aggregation_code()
                for calculation in self.calculations
            ]
        )

    def _get_robust_aggregation_code(self):
        """Get the robust syntax of the aggregation code."""
        final_dict = {}
        for partial_dict in [
            calculation.get_robust_aggregation_dict()
            for calculation in self.calculations
        ]:
            final_dict = {**final_dict, **partial_dict}

        return f"**{final_dict}"

    def get_code(self):
        """
        The simple syntax fails if the user chooses a column name that is not a valid kwarg key,
        e.g. "1 my col", because this is then not valid python syntax, e.g.
        df.groupby(['Pclass']).agg(1 my col=('Pclass', 'count')).reset_index()
        In this case we need the following robust syntax:
        df.groupby(['Pclass']).agg(**{"1 my col": ('Pclass', 'count')})
        """
        can_use_simple_syntax = all(
            [calculation.has_valid_simple_syntax() for calculation in self.calculations]
        )

        if can_use_simple_syntax:
            return self._get_simple_aggregation_code()
        else:
            return self._get_robust_aggregation_code()


class CalculationSelector(SelectorMixin, widgets.HBox):
    """
    Manages one column selector and an aggregation function selector. Maybe comes with a delete
    button to remove itself.
    """

    def __init__(self, transformation, show_delete_button=True, **kwargs):
        super().__init__(show_delete_button=show_delete_button, **kwargs)
        self.transformation = transformation

        self.aggregation_dropdown = Multiselect(
            options=AGGREGATION_OPTIONS,
            focus_after_init=show_delete_button,
            placeholder="Value(s)",
            width="xs",
        )

        self.columns_selector = ColumnsSelector(self.transformation)

        self.children = [
            self.aggregation_dropdown,
            widgets.HTML(" of "),
            self.columns_selector,
            self.delete_selector_button,
        ]

    def has_valid_value(self):
        return (
            len(self.columns_selector.value) > 0
            and len(self.aggregation_dropdown.value) > 0
        )

    def get_all_columns(self):
        return self.columns_selector.value

    def get_all_aggregations(self):
        return self.aggregation_dropdown.value

    def get_column(self):
        if not self.is_simple_calculation():
            # A user should never see this
            raise Exception(
                "Cannot call get_column when the calculation is not a simple calculation"
            )
        return self.columns_selector.value[0]

    def get_aggregation(self):
        if not self.is_simple_calculation():
            # A user should never see this
            raise Exception(
                "Cannot call get_aggregation when the calculation is not a simple calculation"
            )
        return self.aggregation_dropdown.value[0]

    def get_complex_calculation_dict_code(self):
        aggregations = self.aggregation_dropdown.value
        columns = self.columns_selector.value
        if len(columns) == 1:
            # Examples:
            # {"Survived": ["count", "min"]}
            # {"Survived": ["count"]}
            return f"{{{string_to_code(columns[0])}: {aggregations}}}"
        else:
            column_code = self.columns_selector.get_columns_code()
            # Example: {col: ["count", "min"] for col in ["Survived", "Pclass"]}
            return f"{{col: {aggregations} for col in {column_code}}}"

    def is_simple_calculation(self):
        return (
            self.columns_selector.has_column_names()
            and len(self.columns_selector.value) == 1
            and len(self.aggregation_dropdown.value) == 1
        )

    def get_metainfos(self):
        infos = {}
        for type_ in self.aggregation_dropdown.value:
            infos[f"aggregation_type_{type_}"] = True

        if len(self.aggregation_dropdown.value) > 1:
            infos[f"multiple_aggregations_per_column"] = True
        return infos

    def test_select_aggregation_functions(self, aggregation_functions: list):
        self.aggregation_dropdown.value = aggregation_functions

    def test_select_columns_to_aggregate(self, columns_to_aggregate: list):
        self.columns_selector.value = columns_to_aggregate


class AggregationSection(SelectorGroupMixin, widgets.VBox):
    """
    Manages the `CalculationSelector`s, i.e. basically an indefinite number of column name/aggregation
    pair components.
    """

    def __init__(self, transformation):
        super().__init__()
        self.transformation = transformation

        self.init_selector_group("add calculation")

        self.children = [
            widgets.HTML("and calculate"),
            self.selector_group,
            self.add_selector_button,
        ]

    def create_selector(self, show_delete_button=None, **kwargs):
        return CalculationSelector(
            self.transformation,
            selector_group=self,
            show_delete_button=show_delete_button,
        )

    def _get_single_calculation_code(self):
        selector = self.get_selectors()[0]
        if selector.is_simple_calculation():
            return SimpleCodeExporter([SimpleCalculation(selector)]).get_code()
        else:
            return selector.get_complex_calculation_dict_code()

    def _valid_selectors(self):
        return [
            selector for selector in self.get_selectors() if selector.has_valid_value()
        ]

    def _get_multiple_calculations_code(self):
        if self._all_calculations_are_simple():
            calculations = [
                SimpleCalculation(selector) for selector in self._valid_selectors()
            ]
            return SimpleCodeExporter(calculations).get_code()
        else:
            if self._dicts_override_each_other():
                return self._get_tuple_code()
            else:
                dicts_code = ", ".join(
                    [
                        f"**{selector.get_complex_calculation_dict_code()}"
                        for selector in self._valid_selectors()
                    ]
                )
                return "{%s}" % dicts_code

    def _dicts_override_each_other(self):
        previous_columns = []
        for selector in self._valid_selectors():
            new_columns = list(selector.get_all_columns())
            for column in new_columns:
                if column in previous_columns:
                    return True
            previous_columns += new_columns
        return False

    def _get_tuple_code(self):
        """
        Gather all columns and their aggregations.
        Then write it in the following way: {"Survived": ["count", "min"], "Age": ["min"]}.
        """
        full_dict = {}
        for selector in self._valid_selectors():
            for column in selector.get_all_columns():
                for aggregation in selector.get_all_aggregations():
                    if column not in full_dict.keys():
                        full_dict[column] = [aggregation]
                    else:
                        existing_aggregations = full_dict[column]
                        if aggregation in existing_aggregations:
                            pass
                        else:
                            existing_aggregations.append(aggregation)
        return f"{full_dict}"

    def get_code(self):
        if self._only_has_single_calculation():
            return self._get_single_calculation_code()
        else:
            return self._get_multiple_calculations_code()

    def _only_has_single_calculation(self):
        """Returns True if we only have one aggregation function applied to a selected column."""
        return len(self.get_selectors()) == 1

    def _all_calculations_are_simple(self):
        return all(
            calculation.is_simple_calculation() for calculation in self.get_selectors()
        )

    def columns_need_flattening(self):
        if self._all_calculations_are_simple():
            return False
        else:
            return True

    def get_metainfos(self):
        aggregation_metainfos = {}
        for aggregation in self.get_selectors():
            aggregation_metainfos = {
                **aggregation_metainfos,
                **aggregation.get_metainfos(),
            }

        return {
            "aggregation_section_count": len(self.get_selectors()),
            **aggregation_metainfos,
        }

    def test_select_aggregation_functions(self, aggregation_functions: list):
        self.get_selectors()[-1].test_select_aggregation_functions(
            aggregation_functions
        )

    def test_select_columns_to_aggregate(self, columns_to_aggregate: list):
        self.get_selectors()[-1].test_select_columns_to_aggregate(columns_to_aggregate)


class GroupbyWithMultiselect(Transformation):
    """
    Manages `AggregationSection`, groupby columns and how to merge the result (as new df or new column).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        df = self.get_df()

        self.groupby_columns = Multiselect(
            options=list(self.get_df().columns),
            placeholder="Choose column(s)",
            focus_after_init=True,
            width="lg",
        )

        self.aggregation_section = AggregationSection(self)

        self.merge_result = Singleselect(
            placeholder="Choose style",
            options=[("New Table", False), ("New Columns", True)],
            set_soft_value=True,
            width="lg",
        )

    def render(self):
        self.set_title("Aggregate/Group by")
        self.set_content(
            widgets.VBox(
                [
                    widgets.HTML("Group by"),
                    self.groupby_columns,
                    self.aggregation_section,
                    widgets.HTML("and store result as"),
                    self.merge_result,
                    self.rename_df_group,
                ]
            )
        )

    def get_description(self):
        description = f"<b>Group by and aggregate</b>"

        if self.merge_result.value:
            description = f"<b>Add new column(s)</b> based on {description}"
        return description

    def _get_normalization_code(self, new_df):
        if self.aggregation_section.columns_need_flattening():
            return f"""
{new_df}.columns = ['_'.join(multi_index) for multi_index in {new_df}.columns.ravel()]
{new_df} = {new_df}.reset_index()"""
        else:
            return ".reset_index()"
        # the code here and the transformation above are not simplified concerning the normalization because
        # a) the merge part cannot be normalized expost because normalization needs to happen in between
        # b) the normalization for the normal statement is a little bit more complicated then the solution here in this concrete scenario

    def _get_agg_code(self):
        new_df = "tmp_groupby_df" if self.merge_result.value else DF_NEW
        aggregation_code = self.aggregation_section.get_code()
        normalization = self._get_normalization_code(new_df)

        return f"""{new_df} = {DF_OLD}.groupby({self.groupby_columns.value}).agg({aggregation_code}){normalization}"""

    def is_valid_transformation(self):
        if len(self.groupby_columns.value) == 0:
            raise BamboolibError(
                "You did not select any columns to group by.<br>Please select some groupby column(s)"
            )
        return True

    def get_exception_message(self, exception):
        exception_message = str(exception)
        # Happens when a user tries to do a numeric aggregation on a string column.
        # This error message is only created with pandas versions around 1.2.X and the
        # message changed with pandas 1.3.X
        if (
            # pandas 1.2.X - 1.3.X
            "No numeric types to aggregate"
            in exception_message
        ) or (
            # pandas >=1.3.X
            ("Could not convert" in exception_message)
            and ("to numeric" in exception_message)
        ):
            return notification(
                "You tried to apply a numeric aggregation (e.g. mean or sum) to a non-numeric column (e.g. a String column).<br><br>Please review your aggregations and the data types of your columns and make sure that they are compatible",
                type="error",
            )
        if "No objects to concatenate" in exception_message:
            # This can be removed, when the case is handled via is_valid_transformation
            return notification(
                "You did not provide an aggregation e.g. count of ColumnA.<br><br>Please add an aggregation",
                type="error",
            )
        return None

    def get_code(self):
        aggregation_code = self._get_agg_code()

        if self.merge_result.value:
            aggregation_code += f"""
{DF_NEW} = {DF_OLD}.merge(tmp_groupby_df, on={self.groupby_columns.value})"""
        return aggregation_code

    def reset_preview_columns_selection(self):
        if self.merge_result.value:
            return False
        else:  # create new table
            return True

    def get_metainfos(self):
        return {
            "groupby_type": self.merge_result.label,
            "groupby_columns_count": len(self.groupby_columns.value),
            **self.aggregation_section.get_metainfos(),
        }

    def test_select_groupby_columns(self, groupby_columns: list):
        self.groupby_columns.value = groupby_columns

    def test_select_aggregation_functions(self, aggregation_functions: list):
        self.aggregation_section.test_select_aggregation_functions(
            aggregation_functions
        )

    def test_select_columns_to_aggregate(self, columns_to_aggregate: list):
        self.aggregation_section.test_select_columns_to_aggregate(columns_to_aggregate)

    def test_select_merge_result(self, merge_result: bool):
        self.merge_result.value = merge_result


# Solution options:
# named_dict: Survived_count=('Survived', 'count')
#   - unflexible but short and not flattening
# agg_dict with single column: {"Survived": ["min", "max"]}
#   - very powerful but needs flattening
# agg_dict with list comprehension: {col: ["min", "max"] for col in ["Survived", "Age"]}
#   - very powerful but needs flattening
# merged agg_dict: {**{col: ["min"] for col in ["Survived", "Age"]}, **{col: ["max"] for col in ["Survived", "Age"]}
#   - most powerful but needs flattening
