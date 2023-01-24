# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets
from traitlets import Unicode, Bool
from bamboolib import __widgets_version__


@widgets.register()
class GlimpseRow(widgets.Box):
    """
    This widget provides a single content row for the bamboolib glimpse which
    contains statistical information like count of missing values for a given column.
    The row is meant to be updated because the statistics might be calculated based
    on a sample if the dataset is too big.

    :param name: column name as str
    :param dtype: column data type as str
    :param unique_count: count of unique values as int
    :param unique_percent: percent of unique values as float e.g. 65.3
    :param missings_count: count of missing values as int
    :param missings_percent: percent of missing values as float e.g. 10.3
    :param loading: boolean if a loader bar should be shown
    :param sample_size: number of sampled rows as int
    """

    _view_name = Unicode("BamGlimpseRowView").tag(sync=True)
    _model_name = Unicode("BamGlimpseRowModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)
    name = Unicode("").tag(sync=True)
    dtype = Unicode("").tag(sync=True)
    unique_count = Unicode("").tag(sync=True)
    unique_percent = Unicode("").tag(sync=True)
    missings_count = Unicode("").tag(sync=True)
    missings_percent = Unicode("").tag(sync=True)
    loading = Bool(False).tag(sync=True)
    sample_size = Unicode("").tag(sync=True)

    def __init__(
        self,
        name="",
        dtype="",
        unique_count=0,
        unique_percent=0,
        missings_count=0,
        missings_percent=0,
        loading=False,
        sample_size=0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.add_class("bamboolib-glimpse-row")

        self.name = name
        self.dtype = dtype
        self.set_unique_and_missings(
            unique_count, unique_percent, missings_count, missings_percent
        )
        self.loading = loading
        self.sample_size = f"{sample_size:,}"

        self._click_callbacks = widgets.CallbackDispatcher()
        self.on_msg(self._handle_message_from_js)

    def set_unique_and_missings(
        self, unique_count=0, unique_percent=0, missings_count=0, missings_percent=0
    ):
        """
        Set and format the str values for the count and percentage of unique and missing values.

        :param unique_count: count of unique values as int
        :param unique_percent: percent of unique values as float e.g. 65.3
        :param missings_count: count of missing values as int
        :param missings_percent: percent of missing values as float e.g. 10.3
        """
        self.unique_count = f"{unique_count:,}"
        self.unique_percent = "{0:.1f}%".format(unique_percent)
        self.missings_count = f"{missings_count:,}"
        self.missings_percent = "{0:.1f}%".format(missings_percent)

    def _handle_message_from_js(self, widget, content, buffers=None):
        type_ = content.get("type", "")
        if type_ == "on_click":
            self._click_callbacks(self)

    def on_click(self, callback, remove=False):
        """
        Add or remove an on_click callback.

        :param callback: a function that expects the widget itself as single argument
        :param remove: boolean

        Example:
        >>> clickable.on_click(lambda widget: print("The user clicked me!"))
        """
        self._click_callbacks.register_callback(callback, remove=remove)


@widgets.register()
class GlimpseHeader(widgets.Box):
    """
    This widget provides the header row for the bamboolib glimpse that shows the names of the columns
    """

    _view_name = Unicode("BamGlimpseHeaderView").tag(sync=True)
    _model_name = Unicode("BamGlimpseHeaderModel").tag(sync=True)
    _view_module = Unicode("bamboolib").tag(sync=True)
    _model_module = Unicode("bamboolib").tag(sync=True)
    _view_module_version = Unicode(__widgets_version__).tag(sync=True)
    _model_module_version = Unicode(__widgets_version__).tag(sync=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.add_class("bamboolib-glimpse-header")
