# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

# """
# Functions that we may use in the future again and contain too much effort to simply through away.
# """


# @embeddable_with_outlet_blocking
# def _dropdown_comparison_cat300_to_numeric(
#     df, cat300, numeric, outlet=None, loading=None, **kwargs
# ):
#     df = change_df_column_order(df, [cat300, numeric])

#     cat300_sample = df[cat300].value_counts().index[0]
#     cat300_sample_df = df[df[cat300] == cat300_sample]

#     qgrid_widget = preview(
#         cat300_sample_df, show_rows=cat300_sample_df.shape[0]
#     ).children[0]

#     hist_series = cat300_sample_df[numeric]
#     max_bin_count = 10

#     fig_widget = go.FigureWidget(
#         [],  # empty data
#         go.Layout(
#             xaxis={
#                 "range": [df[numeric].min(), df[numeric].max()],
#                 "title": f"{numeric}",
#             },
#             yaxis={"title": "count"},
#             bargap=0.05,
#             autosize=False,
#             width=500,
#             height=500,
#             **PLOTLY_BACKGROUND,
#         ),
#     )
#     fig_placeholder = widgets.VBox([])

#     def handle_zoom(xaxis, xrange):
#         fig_widget.data[0].x = hist_series[
#             (hist_series >= xrange[0]) & (hist_series <= xrange[1])
#         ]

#     fig_widget.layout.xaxis.on_change(handle_zoom, "range")

#     def series_has_valid_values(series):
#         return series[series.notna()].count() > 0

#     def update_hist_figure(new_series, new_title):
#         global hist_series
#         hist_series = new_series
#         new_hist = go.Histogram(x=hist_series, nbinsx=max_bin_count)
#         fig_widget.update(data=[new_hist])
#         fig_widget.layout.title = new_title

#     def update_hist(new_series, cat300_sample):
#         if series_has_valid_values(new_series):
#             title = f"{numeric}, where {cat300} is {cat300_sample}"
#             update_hist_figure(new_series, title)
#             fig_placeholder.children = [fig_widget, bin_slider]
#         else:
#             new_series = pd.Series([0])
#             title = f"There are no valid {numeric} values, where {cat300} is {cat300_sample}"
#             fig_placeholder.children = [widgets.HTML(f"<h3>{title}</h3>")]

#     def set_bin_size(bins=10):
#         global max_bin_count
#         max_bin_count = bins
#         fig_widget.data[0].nbinsx = max_bin_count

#     bin_slider = interactive(set_bin_size, bins=(2, 100, 1))

#     update_hist(hist_series, cat300_sample)  # initialize the histogram data

#     cat300_sample_dd = widgets.Dropdown(
#         value=cat300_sample,
#         options=df[cat300].value_counts().index.tolist(),
#         description=f"{cat300} Category",
#         disabled=False,
#     )

#     def on_cat300_dropdown_change(value):
#         global cat300_sample
#         cat300_sample = value["new"]
#         cat300_sample_df = df[df[cat300] == cat300_sample]
#         qgrid_widget.df = cat300_sample_df
#         update_hist(cat300_sample_df[numeric], cat300_sample)

#     cat300_sample_dd.observe(on_cat300_dropdown_change, names="value")

#     title = widgets.HTML(
#         f"Answers the question: Given a '{cat300}' class, how is '{numeric}' distributed?"
#     )
#     subtitle = widgets.HTML(
#         f"For example: if '{cat300}' = {cat300_sample}, how is '{numeric}' distributed?"
#     )
#     # TODO: lazy loading via incremental updates - always add to an output widget because the
#     # results are shown right away
#     outlet.children = [title, subtitle, cat300_sample_dd, fig_placeholder, qgrid_widget]
#     return outlet


# @embeddable_plain_blocking
# def cat_to_any_drilldown_table(
#     df,
#     cat300,
#     y_any,
#     y_is_high_cat=False,
#     y_is_numeric=False,
#     show_df_subset_string=True,
#     **kwargs,
# ):

#     cat300_value_counts = (
#         df[[cat300, y_any]]
#         .groupby(cat300)
#         .agg({cat300: "count"})
#         .rename(columns={cat300: f"Subset row count"})
#     )
#     if y_is_numeric:
#         var = (
#             df[[cat300, y_any]]
#             .groupby(cat300)
#             .agg({y_any: "var"})
#             .rename(columns={y_any: f"Variance of {y_any}"})
#         )
#         mean = (
#             df[[cat300, y_any]]
#             .groupby(cat300)
#             .agg({y_any: "mean"})
#             .rename(columns={y_any: f"Mean of {y_any}"})
#         )
#         min_ = (
#             df[[cat300, y_any]]
#             .groupby(cat300)
#             .agg({y_any: "min"})
#             .rename(columns={y_any: f"Min of {y_any}"})
#         )
#         max_ = (
#             df[[cat300, y_any]]
#             .groupby(cat300)
#             .agg({y_any: "max"})
#             .rename(columns={y_any: f"Max of {y_any}"})
#         )
#         columns = [cat300_value_counts, var, mean, min_, max_]
#         overview_df = pd.concat(columns, axis=1).reset_index()
#     else:
#         y_any_nunique = (
#             df[[cat300, y_any]]
#             .groupby(cat300)
#             .agg({y_any: "nunique"})
#             .rename(columns={y_any: f"Nunique of {y_any}"})
#         )
#         overview_df = pd.concat(
#             [cat300_value_counts, y_any_nunique], axis=1
#         ).reset_index()
#     overview_df = overview_df.sort_values(by="Subset row count", ascending=False)

#     qwidget = qgrid_widget(overview_df)

#     filter_outlet = widgets.VBox()
#     filter_outlet.children = [
#         notification(
#             "Click on a row in the interactive table to drill down on the subset"
#         )
#     ]

#     show_df_subset_string_list = [
#         show_df_subset_string
#     ]  # transform variable to list so that the variable is available in the closure handle_selection_changed

#     def handle_selection_changed(event, qgrid_widget, **kwargs):
#         if len(event["new"]) > 0:
#             visible_overview_df = qwidget.get_changed_df()
#             selected_overview_df = visible_overview_df.iloc[event["new"]]

#             cat300_uniques = selected_overview_df[cat300].unique()
#             array_string = (
#                 "[" + ", ".join([f"'{item}'" for item in cat300_uniques]) + "]"
#             )
#             subset_df_string = f"df[df['{cat300}'].isin({array_string})]"
#             if show_df_subset_string_list[0]:
#                 header = widgets.HTML(
#                     "<h3>Selected subset:</h3><br>" + subset_df_string
#                 )
#             else:
#                 header = widgets.HTML("<h3>Selected subset:</h3>")

#             subset_df = df[df[cat300].isin(cat300_uniques)]
#             subset_df = change_df_column_order(subset_df, [cat300, y_any])

#             tab_contents = []
#             tab_contents.append(
#                 {
#                     "title": "Raw data view",
#                     "content": new_lazy_widget_decorator(preview, subset_df, **kwargs),
#                 }
#             )
#             tab_contents.append(
#                 {
#                     "title": f"Subset {y_any}",
#                     "content": new_lazy_widget_decorator(
#                         _column_summary, subset_df, y_any, **kwargs
#                     ),
#                 }
#             )
#             tab_contents.append(
#                 {
#                     "title": "Subset overview",
#                     "content": new_lazy_widget_decorator(overview, subset_df, **kwargs),
#                 }
#             )
#             tabs = lazy_tabs(tab_contents)
#             filter_outlet.children = [header, tabs]

#     qwidget.on("selection_changed", handle_selection_changed)
#     return qwidget, filter_outlet
