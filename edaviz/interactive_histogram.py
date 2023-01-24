# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

from math import ceil, log

import ipywidgets as widgets

import plotly.graph_objs as go

# import seaborn as sns
# import matplotlib.pyplot as plt

from bamboolib.edaviz.base import AsyncEmbeddable, css_spinner
from bamboolib.helper import notification
from bamboolib.widgets import CopyButton, Button

from IPython.display import display


def triggers_rendering(original_function):
    """
    Decorator that makes sure only the latest state change is rendered and that global state
    cannot be changed while graph is being rendered.

    :param original_function: function changing state.
    """

    def new_function(self, *args, **kwargs):
        if self._state["rendering"]:
            return

        self._state["rendering_id"] += 1
        rendering_id = self._state["rendering_id"]

        original_function(self, *args, **kwargs)

        self._update_code_export()
        self._update_gui(rendering_id)

    return new_function


class InteractiveHistogram(AsyncEmbeddable):
    def _get_max_bin_width(self, range_size):
        """
        Computes a bin width which results in 5 to 12 bins.

        :param range_size: (float) the range from minimum to maximum x value in the histogram.

        :return: a float for the bin width, which is either 1, 2.5 or 5 - scaled to the magnitude
        of the range_size.
        """
        power = ceil(log(range_size, 10))
        onesy = 1 * 10 ** (power - 1)
        fivesy = 0.5 * (10 ** (power - 1))
        two_point_fivesy = 0.25 * (10 ** (power - 1))
        if (range_size / onesy) >= 5:
            return onesy
        elif (range_size / fivesy) >= 5:
            return fivesy
        elif (range_size / two_point_fivesy) >= 5:
            return two_point_fivesy
        else:
            return onesy / 10

    def _get_min_bin_width(self, range_size):
        return self._get_max_bin_width(range_size) / 10

    def round_relatively(self, target, relative=None, precision=2):
        """
        Rounds the target number to presision digits based on the magnitude of the relative.

        Example:
        self.relative(target=0.123, relative=1)  # equals 0.12
        self.relative(target=0.123, relative=10)  # equals 0.1
        """
        if relative is None:
            relative = target

        if relative == 0:
            # log(0, 10) is not defined, so we default to 0 in our case
            magnitude = 0
        else:
            magnitude = ceil(log(abs(relative), 10))

        rounding = (magnitude * -1) + precision
        return round(target, rounding)

    @triggers_rendering
    def _change_limits(self, change):
        if self.min_value_input.value < self.max_value_input.value:
            self._state["limit_min"] = self.min_value_input.value
            self._state["limit_max"] = self.max_value_input.value
            self._calculate_and_set_new_derived_state()

    @triggers_rendering
    def _change_bin_width(self, change):
        new_bin_width = change["new"]
        if new_bin_width > 0:
            self._state["bin_width_value"] = new_bin_width
            self._state["number_of_bins"] = self._calculate_new_number_of_bins(
                new_bin_width
            )
            # Attention: we cannot recalculate the binning state (as with self._calculate_and_set_new_derived_state())
            # because this might lead to the following error:
            # If the bin_width_input has a value that very fine-grained (more than the bin_slider_widget is able to perform)
            # then the relative rounding of the new_bin_width might make the bin_width more coarse
            # The visual effect is that the bin_width_input cannot be set to a fine-grained value and automatically resets

    @triggers_rendering
    def _zoom_histogram(self, xaxis, xrange):
        range_ = abs(xrange[1] - xrange[0])
        self._state["limit_min"] = self.round_relatively(xrange[0], range_)
        self._state["limit_max"] = self.round_relatively(xrange[1], range_)
        self._calculate_and_set_new_derived_state()

    @triggers_rendering
    def _undo_zoom(self, button):
        zoom_history = self._state["zoom_history"]
        if len(zoom_history) >= 2:
            zoom_history.pop()  # removes current range
            last_range = zoom_history[-1]
            self._state["limit_min"] = last_range[0]
            self._state["limit_max"] = last_range[1]
            if len(zoom_history) <= 1:
                self._state["undo_zoom_disabled"] = True
            self._calculate_and_set_new_derived_state()

    @triggers_rendering
    def _reset_zoom(self, button):
        zoom_history = self._state["zoom_history"]
        first_range = zoom_history[0]
        self._state["limit_min"] = first_range[0]
        self._state["limit_max"] = first_range[1]
        zoom_history.clear()
        zoom_history.append(first_range)
        self._state["undo_zoom_disabled"] = True
        self._calculate_and_set_new_derived_state()

    def _init_gui(self):
        self._state["rendering"] = True

        self.min_value_input = widgets.FloatText(
            value=self._state["limit_min"], description="Min:"
        )
        self.min_value_input.observe(self._change_limits, names="value")
        self.min_value_input.add_class("bamboolib-input")
        self.min_value_input.add_class("bamboolib-float-text")
        self.min_value_input.add_class("bamboolib-input-md")

        self.max_value_input = widgets.FloatText(
            value=self._state["limit_max"], description="Max:"
        )
        self.max_value_input.observe(self._change_limits, names="value")
        self.max_value_input.add_class("bamboolib-input")
        self.max_value_input.add_class("bamboolib-float-text")
        self.max_value_input.add_class("bamboolib-input-md")

        self.bin_width_input = widgets.FloatText(
            value=self._state["bin_width_value"], description="Bin width:"
        )
        self.bin_width_input.observe(self._change_bin_width, names="value")
        self.bin_width_input.add_class("bamboolib-input")
        self.bin_width_input.add_class("bamboolib-float-text")
        self.bin_width_input.add_class("bamboolib-input-md")

        self.bin_width_slider = widgets.FloatSlider(
            description="Bin width:",
            continuous_update=False,
            orientation="horizontal",
            readout=False,
            # valid default values that will be overriden later
            value=self._state["bin_width_value"],
            min=self._state["bin_width_min"],
            max=self._state["bin_width_max"],
            step=self._state["bin_width_step"],
        )
        self.bin_width_slider.observe(self._change_bin_width, names="value")
        self.bin_width_slider.add_class("bamboolib-input-md")
        self.bin_width_slider.add_class("bamboolib-hide-label")

        self.copy_code_button = CopyButton()

        self.loader_outlet = widgets.VBox()
        self._init_fig_widget()

        self.undo_zoom_button = Button(
            description="Undo zoom",
            disabled=self._state["undo_zoom_disabled"],
            on_click=self._undo_zoom,
        )

        self.reset_zoom_button = Button(
            description="Reset zoom", on_click=self._reset_zoom
        )

        self.top_buttons = widgets.HBox(
            [self.copy_code_button, self.undo_zoom_button, self.reset_zoom_button]
        ).add_class("bamboolib-interactive-histogram-top-buttons-group")
        self.limit_box = widgets.VBox([self.min_value_input, self.max_value_input])
        self.bin_width_box = widgets.VBox([self.bin_width_input, self.bin_width_slider])

        self.set_content(
            widgets.HTML("<h4>Histogram</h4>"),
            self.top_buttons,
            self.loader_outlet,
            self.fig_widget,
            widgets.HBox([self.limit_box, self.bin_width_box]),
        )

        self._state["rendering"] = False

    def _init_fig_widget(self):
        if self._state["plotting_backend"] == "seaborn":
            self.fig_widget = widgets.Output()
            self._update_figure_widget(0)

        else:
            bin_width = self._state["bin_width_value"]
            data = [
                go.Histogram(
                    x=self._state["series"],
                    xbins={
                        # Attention: plotly histograms have a bug because they sometimes auto-zoom on the first display
                        # e.g. with the following settings and bam.plot(df3, 'Pclass') for titanic df
                        # the third class is not shown because the zoom is smaller than 3 then ...
                        # "start": self._state["limit_min"],
                        # "end": self._state["limit_max"],
                        # the following adjustment seems to fix the error
                        # it is important to note that this adjustment only happens during init of the figure
                        # and not for later updates which are handled separately
                        "start": self._state["limit_min"] - bin_width,
                        "end": self._state["limit_max"] + bin_width,
                        "size": bin_width,
                    },
                )
            ]

            layout = go.Layout(
                yaxis=dict(title="Count", fixedrange=True),
                bargap=0.05,
                width=500,
                height=300,
                margin=go.layout.Margin(l=0, r=0, b=0, t=0),
            )

            self.fig_widget = go.FigureWidget(data=data, layout=layout)
            self.fig_widget.layout.xaxis.on_change(self._zoom_histogram, "range")

            self.histogram_trace = self.fig_widget.data[0]

    def _update_code_export(self):
        df_name = self.df_manager.get_current_df_name()
        if self._state["plotting_backend"] == "seaborn":
            pass  # should not be reached!

            # # to be activated again
            # series = self._state["series"]
            # start = self._state["limit_min"]
            # end = self._state["limit_max"]
            # nbins = int(self._state["number_of_bins"])
            # width = self._state["bin_width_value"]

            # import_ = (
            #     "" if self.df_manager.user_imported(sns) else f"import seaborn as sns\n"
            # )

            # filter_ = ""
            # if (series.min() != start) or (series.max() != end):
            #     filter_ = f""".loc[({df_name}["{self.column}"] >= {start}) & ({df_name}["{self.column}"] <= {end})]"""

            # self._state[
            #     "code_export"
            # ] = f"""{import_}sns.distplot({df_name}{filter_}["{self.column}"],
            #  bins=[{start} + i*{width} for i in range({nbins+1})], kde=False)"""
            # # Attention: indentation is on purpose and aligns with sns.distplot
            # # Alternative: optionally add .figure.show() to the code
        else:
            start = self._state["limit_min"]
            end = self._state["limit_max"]
            size = self._state["bin_width_value"]
            import_ = (
                ""
                if self.df_manager.user_imported(go)
                else f"import plotly.graph_objs as go\n"
            )

            self._state[
                "code_export"
            ] = f"""{import_}go.Figure(
    data=[go.Histogram(x={df_name}["{self.column}"], xbins={{"start": {start}, "end": {end}, "size": {size}}})],
    layout=go.Layout(title="Histogram of {self.column}", yaxis={{"title": "Count"}}, bargap=0.05),
    )"""

        # def _create_seaborn_svg(self, rendering_id):
        #     if self._state["rendering_id"] != rendering_id:
        #         return

        #     start = self._state["limit_min"]
        #     end = self._state["limit_max"]
        #     nbins = int(self._state["number_of_bins"])
        #     width = self._state["bin_width_value"]

        #     self.loader_outlet.children = [widgets.HTML(f"{css_spinner()} Loading ...")]

        #     series = self._state["series"]
        #     if (series.min() != start) or (series.max() != end):
        #         series = self.df.loc[
        #             (self.df[self.column] >= start) & (self.df[self.column] <= end)
        #         ][self.column]

        #     if self._state["rendering_id"] != rendering_id:
        #         return

        # figure = plt.figure(figsize=(5.12, 3.84))
        #     sns.distplot(
        #         series, bins=[start + i * width for i in range(nbins + 1)], kde=False
        #     )
        # plt.tight_layout()
        # plt.close(figure)

    #     from io import BytesIO

    #     imgdata = BytesIO()
    #     figure.savefig(imgdata, format="svg")
    #     svg_string = imgdata.getvalue().decode("utf-8")

    #     if self._state["rendering_id"] != rendering_id:
    #         return

    #     self.fig_widget.clear_output(wait=True)
    #     self.fig_widget.outputs = (
    #         {"output_type": "display_data", "data": {"image/svg+xml": svg_string}},
    #     )

    #     self.loader_outlet.children = []

    def _update_figure_widget(self, rendering_id):
        if self._state["plotting_backend"] == "seaborn":
            pass
            # self._create_seaborn_svg(rendering_id)
        else:
            with self.fig_widget.batch_update():
                self.fig_widget.layout.xaxis.range = [
                    self._state["limit_min"],
                    self._state["limit_max"],
                ]
                self.histogram_trace.xbins = {
                    "start": self._state["limit_min"],
                    "end": self._state["limit_max"],
                    "size": self._state["bin_width_value"],
                }
        # in the end, we update the code export - but only after the update was successful
        # so that the user always copies the code of the chart that he currently sees
        self.copy_code_button.copy_string = self._state["code_export"]

    def _update_gui(self, rendering_id):
        if self._state["rendering"]:
            return

        self._state["rendering"] = True

        self.min_value_input.value = self._state["limit_min"]
        self.max_value_input.value = self._state["limit_max"]
        self.bin_width_input.value = self._state["bin_width_value"]

        self.bin_width_slider.step = self._state["bin_width_step"]
        # Important: when updating the bin_width_slider, FIRST update min and max and THEN the value
        # ... otherwise the value might be capped by the min or max
        if self._state["bin_width_min"] > self.bin_width_slider.max:
            self.bin_width_slider.max = self._state["bin_width_max"]
            self.bin_width_slider.min = self._state["bin_width_min"]
        else:  # if self._state["bin_width_min"] < self.bin_width_slider.min and all other cases
            self.bin_width_slider.min = self._state["bin_width_min"]
            self.bin_width_slider.max = self._state["bin_width_max"]
        self.bin_width_slider.value = self._state["bin_width_value"]

        self.undo_zoom_button.disabled = self._state["undo_zoom_disabled"]

        if self._state["rendering_id"] != rendering_id:
            return

        from bamboolib.helper import execute_asynchronously

        execute_asynchronously(self._update_figure_widget, rendering_id)

        self._state["rendering"] = False

    def init_embeddable(self, df, column, **kwargs):
        self.df = df
        self.column = column
        original_series = df[column].dropna()

        default_min = original_series.min()
        default_max = original_series.max()
        if default_max == default_min:
            default_max = default_min + 1

        series_has_more_than_10k_rows = len(original_series) > 10_000
        min_max_diff_is_larger_than_1billion = (
            abs(default_max - default_min) > 1_000_000_000
        )
        use_seaborn = (
            series_has_more_than_10k_rows or min_max_diff_is_larger_than_1billion
        )

        plotting_backend = "seaborn" if use_seaborn else "plotly"
        ### TODO: remove this early return here if we support widgets.Output or found a workaround for seaborn
        if plotting_backend == "seaborn":
            if series_has_more_than_10k_rows:
                note = """
                The interactive histogram only supports up to 10,000 rows of data.<br>
                <br>
                However, your table has more rows than that.<br>
                <br>
                You can sample or filter the data to meet the limit.
                """
            else:  # min_max_diff_is_larger_than_1billion is True
                note = """
                The histogram currently only supports columns where the difference between<br>
                the minimum and maximum value is less than 1,000,000,000.<br>
                <br>
                However, the difference in your column is larger.<br>
                <br>
                In the near future, we will support this kind of columns.<br>
                Until then you might want to remove outliers or reshape the column e.g. divide by 1000.
                """
            self.set_content(
                widgets.HTML("<h4>Histogram</h4>"), notification(note, type="warning")
            )
            return

        self._state = {
            "series": original_series,
            "plotting_backend": plotting_backend,
            "rendering_id": 0,  # used for orchestrating concurrent calls
            "undo_zoom_disabled": True,
            "zoom_history": [[default_min, default_max]],
            "limit_min": default_min,
            "limit_max": default_max,
            "bin_width_value": 1,
            "bin_width_min": 0,
            "bin_width_max": 10,
            "bin_width_step": 1,
            "number_of_bins": 20,
            "code_export": "",
            "rendering": True,
        }
        self._calculate_and_set_new_derived_state()
        self._update_code_export()

        self._init_gui()

    def _calculate_new_number_of_bins(self, new_bin_width):
        # requires the state to have a valid limit_min, limit_max
        range_ = abs(self._state["limit_max"] - self._state["limit_min"])
        return max(1, ceil(range_ / new_bin_width))

    def _update_zoom_stack(self):
        zoom_history = self._state["zoom_history"]
        new_min, new_max = self._state["limit_min"], self._state["limit_max"]
        if len(zoom_history) > 0:
            if zoom_history[-1] == [new_min, new_max]:
                # current dimensions are already the last item on the stack
                return
        zoom_history.append([new_min, new_max])
        if len(zoom_history) >= 2:
            self._state["undo_zoom_disabled"] = False

    def _calculate_and_set_new_derived_state(self):
        # requires the state to have a valid limit_min, limit_max and number_of_bins

        # inputs
        old_number_of_bins = self._state["number_of_bins"]
        range_ = abs(self._state["limit_max"] - self._state["limit_min"])

        # calculation
        step_size = self._get_min_bin_width(range_)
        bin_width_rough = range_ / old_number_of_bins
        bin_width_rounded = max(1, ceil(bin_width_rough / step_size)) * step_size
        new_bin_width = self.round_relatively(bin_width_rounded)

        # set new state
        self._update_zoom_stack()
        self._state["bin_width_value"] = new_bin_width
        self._state["bin_width_min"] = self._get_min_bin_width(range_)
        self._state["bin_width_max"] = self._get_max_bin_width(range_)
        self._state["bin_width_step"] = step_size
        self._state["number_of_bins"] = self._calculate_new_number_of_bins(
            new_bin_width
        )
