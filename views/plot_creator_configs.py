# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import inspect
import textwrap
import traceback
import attr

import ipywidgets as widgets
import plotly.graph_objs as go

import bamboolib._environment as env
from bamboolib.config import get_option

from bamboolib.helper import (
    DF_OLD,
    execute_asynchronously,
    exec_code,
    notification,
    string_to_code,
)

from bamboolib.widgets.block_manager import Block
from bamboolib.widgets import (
    Singleselect,
    Multiselect,
    CopyButton,
    Button,
    CloseButton,
    Text,
    TracebackOutput,
    CodeOutput,
)
from bamboolib.widget_combinations import (
    ListInput,
    DictInput,
    IndentationDictItem,
    SideBySideDictItem,
)

from bamboolib.views import plotly_color_themes
from bamboolib.views import plotly_marker_options


PLOTLY_LINESTYLE_OPTIONS = [
    "solid",
    "dot",
    "dash",
    "longdash",
    "dashdot",
    "longdashdot",
]

SHOW_CODE = False

# ATTENTION: due to the fact that as of Jan 7 2022 we are not enabled to use widgets.Layout
# we needed to hardcode the CSS classes
# if you change the LABEL_WIDTH you need to make sure that the corresponding CSS class exists
# e.g. currently this is the pattern bamboolib-width-{LABEL_WIDTH}
# and thus bamboolib-width-180px
LABEL_WIDTH = "180px"
ALL_COLUMNS = "bamboolib_all_columns_placeholder"

FIGURE = "figure__bamboolib_template_name"


class PlotCreatorBlock(Block):
    """
    A base block for the plot creator that allows to `set_content`

    The class provides features like a name_label, delete_button,
    a label if the block needs to be refreshed, or a sign if the block
    is not supported by the current figure
    """

    name = "TO BE OVERRIDEN"
    show_needs_to_be_refreshed_label = False  # default

    def __init__(self, *args, plot_creator=None, focus_after_init=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.plot_creator = plot_creator
        self.focus_after_init = focus_after_init
        self.add_class("bamboolib-overflow-visible")
        self.add_tag(self.__class__.__name__)

        self.name_label = widgets.HTML(f"{self.name}").add_class(
            f"bamboolib-width-{LABEL_WIDTH}"
        )
        self.delete_button = CloseButton(
            on_click=lambda button: self.plot_creator.remove_config(self)
        )
        self.needs_to_be_refreshed_label = notification("!", type="warning")

    def set_content(
        self,
        *embeddables,
        show_name_label=False,
        show_delete_button=False,
        show_not_supported_label=False,
        width=None,
        css_class=None,
    ):
        """
        Set the content of the block

        :param *embeddables: unpacked list of embeddable objects (widgets)
        :param show_name_label: bool, if the block should have a name
        :param show_delete_button: bool, if the block can be deleted
        :param show_not_supported_label: bool, if the block is supported
        """
        core_content = widgets.VBox([*embeddables])
        core_content.add_class("bamboolib-overflow-visible")
        if width is not None:
            # disable this for now until we have support for widgets.Layout
            # the intermediate workaround is to use `css_class` kwarg
            pass
            # core_content.layout = widgets.Layout(width=width)
        if css_class is not None:
            core_content.add_class(css_class)

        output = []
        if show_name_label:
            output.append(self.name_label)
        output.append(core_content)
        if show_delete_button:
            output.append(self.delete_button)
        if self.show_needs_to_be_refreshed_label:
            output.append(self.needs_to_be_refreshed_label)
        if show_not_supported_label:
            # TODO: later add an exclamation mark icon that shows the message on hover
            output.append(
                widgets.HTML(
                    f"not supported by {self.plot_creator.get_figure_type_name()}"
                )
            )

        hbox = widgets.HBox(output)
        hbox.add_class("bamboolib-overflow-visible")
        super().set_content(hbox)


class ResultRenderer(PlotCreatorBlock):
    """
    A block that is responsible for rendering the result of the PlotCreator

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.final_code = ""
        self.result_name = ""
        self.result_object = None
        self._current_render_id = 0
        self.result_outlet = widgets.VBox()
        self.code_outlet = widgets.VBox()
        self.code_output = CodeOutput(code="")

        self.big_spacer = widgets.VBox([widgets.HTML("<br>") for i in range(20)])

    def render(self):
        self.set_content(
            self.code_outlet, self.result_outlet, css_class="bamboolib-width-100pct"
        )

    def show_embeddable(self, embeddable):
        self.result_outlet.children = [embeddable]

    def _try_to_render_code(self, render_id, on_exception):
        result = None
        if self._current_render_id == render_id:
            try:
                df_manager = self.plot_creator.df_manager

                # LEGACY: when the live code is not exported, the df in the symbols might not represent the current state
                # thus, we insert the current df state based on its name into the symbols
                # we should delete this logic here as soon as (or if) we remove the live_code_export option
                symbols_with_masked_df = df_manager.symbols.copy()
                symbols_with_masked_df[
                    df_manager.get_current_df_name()
                ] = df_manager.get_current_df()

                figure = exec_code(
                    code=self.final_code,
                    symbols=symbols_with_masked_df,
                    result_name=self.result_name,
                    manipulate_symbols=False,
                )
                # Attention: the following does not work:
                # result = widgets.Output()
                # result.append_display_data(figure)
                result = go.FigureWidget(figure)
            except Exception as exception:
                try:
                    # in case that an error occurs during the exception handling
                    result = on_exception(exception)
                except:
                    # maybe later show a hint that there also was an exception during error handling
                    result = self._get_stacktrace(exception)
                if (result is None) or env.SHOW_RAW_EXCEPTIONS:
                    result = self._get_stacktrace(exception)

        if self._current_render_id == render_id:
            self.result_outlet.children = [result]

    def show_code_result(self, code, result_name, on_exception=lambda exception: None):
        """
        Show the result `result_name` from the passed `code`

        :param code: str of code to be executed
        :param result_name: str of the variable name for the result that should be shown
        """
        self._current_render_id += 1
        render_id = self._current_render_id
        self.final_code = textwrap.dedent(code).strip()
        self.result_name = result_name

        self.result_outlet.children = [widgets.HTML("Loading ..."), self.big_spacer]
        self._render_code_outlet()

        execute_asynchronously(self._try_to_render_code, render_id, on_exception)

    def _get_stacktrace(self, exception):
        output = TracebackOutput()
        output.add_class("bamboolib-output-wrap-text")
        output.content += f"{exception.__class__.__name__}: {exception}"
        output.content += "\n\n\n\n"

        try:
            code = self._get_full_code()
            output.content += "Code that produced the error:\n"
            output.content += "-----------------------------\n"
            output.content += code
            output.content += "\n\n\n\n"
        except:
            pass
        output.content += "Full stack trace:\n"
        output.content += "-----------------------------\n"
        output.content += traceback.format_exc()
        return output

    def _get_full_code(self):
        return self.final_code

    def _render_code_outlet(self):
        # TODO: if the df got transformed but the live code export is not activated, then we should include the transformation code here
        code_string = self._get_full_code()

        copy_button = CopyButton(copy_string=code_string, style="primary")

        def toggle_hide_or_show(button):
            global SHOW_CODE
            SHOW_CODE = not SHOW_CODE
            self._render_code_outlet()

        hide_or_show_button = Button(
            description="Hide code" if SHOW_CODE else "Show code",
            icon="chevron-up" if SHOW_CODE else "chevron-down",
            on_click=toggle_hide_or_show,
        )

        output = [widgets.HBox([copy_button, hide_or_show_button])]
        if SHOW_CODE:
            output.append(self._get_code_widget(code_string))
        self.code_outlet.children = output

    def _get_code_widget(self, code_string):
        self.code_output.code = code_string
        return self.code_output


class DfOutdatedNote(PlotCreatorBlock):
    """
    A notification block that the user interface needs to be refreshed
    because the dependent dataframe did change
    """

    def render(self):
        if self.plot_creator.df_is_outdated:
            button = Button(
                "Refresh UI",
                on_click=lambda _: self.plot_creator.refresh_ui(),
                style="primary",  # warning would be better
            )
            self.set_content(
                notification(
                    "The DataFrame did change which influences the figure and configurations. Therefore, the user interface needs to be refreshed.",
                    type="warning",
                ),
                button,
            )
        else:
            self.set_content()


class ConfigurationSelector(PlotCreatorBlock):
    """
    The block that provides the input/search element for adding new configs to the PlotCreator
    """

    name = "Add property"  # internally, we currently call this config
    # maybe refactor all usages of config to property?
    # However, on a meta level we do not only add properties but also actions
    # So, configuration might be better - let's see which name we will take eventually

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config_type = Multiselect(
            # options=options,
            placeholder="Search properties",
            # focus_after_init=focus_after_init,
            width="xl",
            on_change=self._selected_config,
        )

    def _selected_config(self, _):
        if len(self.config_type.value) == 0:
            return
        config_class = self.config_type.value[0]
        self.config_type.value = []
        self.plot_creator.config_got_selected(config_class)

    def _set_options(self):
        supported_configs = (
            self.plot_creator.get_figure_type().get_all_supported_configs()
        )
        options = [
            config
            for config in supported_configs
            if self.plot_creator.config_can_be_selected_by_user(config)
        ]
        self.config_type.options = [
            {"label": config.name, "value": config, "description": config.description}
            for config in options
        ]

    def render(self):
        self._set_options()
        self.set_content(self.config_type, show_name_label=True)


#########################################################################################################
#########################################################################################################
##################### CodeClass(es)
#########################################################################################################
#########################################################################################################


def str_to_list(value):
    """
    Take a value and return a list of str.
    If the value already is a list of str, then do nothing.
    Otherwise, wrap the string into a list.

    :param value: str or list
    """
    if isinstance(value, list):
        return value
    elif isinstance(value, str):
        return [value]
    else:
        raise ValueError(f"Did expect a str or a list but got {type(value)} instead.")


def list_of_str(instance, attribute, value):
    """
    Validates if all items in the value list are of type str
    :param value: list
    :raises ValueError: if not all items in the value list are of type str
    """
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"All items have to be str but got {type(item)} instead")


# See attrs docs for more details
# https://www.attrs.org/en/stable/overview.html
@attr.s(kw_only=True)
class PlotlyFigureCode:
    """
    The base class for code objects
    This is the source for generating the final code via
    populating the code template with the individual parts like
    `kwargs`, `df_adjustments`, `figure_adjustments`, and `imports`
    """

    kwargs = attr.ib(converter=str_to_list, validator=list_of_str)
    df_adjustments = attr.ib(converter=str_to_list, validator=list_of_str)
    figure_adjustments = attr.ib(converter=str_to_list, validator=list_of_str)
    imports = attr.ib(converter=str_to_list, validator=list_of_str)

    # always create new lists for each instance
    # if we do not do this, there will be weird errors
    # when the user mutates the list (instead of assigning a new list)
    # because all code objects hold the reference to the same default list (for each attribute)
    @kwargs.default
    @df_adjustments.default
    @figure_adjustments.default
    @imports.default
    def _create_new_list(self):
        return []


# alias for making the default name shorter - for now
# external usage of the API should be via
# from plot_creator import PlotlyFigureCode as Code OR
# from plot_creator.plotly_figure import Code

# The benefit of having the PlotlyFigureCode object is that the user can check which attributes are available for this Code object e.g. kwargs, df_adjustments, figure_adjustments, etc

Code = PlotlyFigureCode


#########################################################################################################
#########################################################################################################
##################### Configuration(s)
#########################################################################################################
#########################################################################################################


def config_class_belongs_to_any_family(config_class):
    """
    :param config_class: config class
    :return bool if the config_class belongs to a family
    """
    return (
        hasattr(config_class, "apply_family_state")
        and hasattr(config_class, "config_family")
        and config_class.config_family is not None
    )


def config_classes_belong_to_same_family(class_a, class_b):
    """
    :param class_a: first class
    :param class_b: second class
    :return bool if the two classes belong to the same config family
    """
    return (
        config_class_belongs_to_any_family(class_a)
        and config_class_belongs_to_any_family(class_b)
        and class_a.config_family == class_b.config_family
    )


class ConfigFamilyInterface:
    """
    The config family interface that is required by a class that wants to belong to a certain config_family

    The `config_family` attribute needs to be a valid str
    The `apply_family_state` method needs to be implemented
    """

    config_family = None  # should be overriden

    def apply_family_state(self, config):
        """
        Apply the state of a config from the same family to the current config

        :param config: the other config that belongs to the same family and whose state should be transferred
        """
        raise NotImplementedError


class ConfigFamily(ConfigFamilyInterface):
    """
    Base class for a config family. This can be used as alternative syntax instead of manually setting the config_family attribute

    Example:
    >>> class YAxisConfigFamily(ConfigFamily):
    >>>     pass
    >>> class YAxisWithSingleColumn(YAxisConfigFamily, ...):
    >>>     pass
    >>> class YAxisWithMultipleColumns(YAxisConfigFamily, ...):
    >>>     pass
    """

    def __init_subclass__(config_class):
        config_class.config_family = (
            f"{config_class.__module__}.{config_class.__name__}"
        )
        # make sure that the config_subclasses don't change the config_family to their name
        # because per default, __init_subclass__ is inherited by the subclasses
        def __init_subclass__(subclass):
            pass

        config_class.__init_subclass__ = classmethod(__init_subclass__)


class YAxisConfigFamily(ConfigFamily):
    """
    The config family for setting the yaxis value

    Attention: it requires that every family member implements (or inherits) a `get_columns` method
    that returns a list of str of the column names
    """

    pass

    # needs to have get_columns method - MAYBE enforce this later with ABC?
    # def get_columns(self):
    #     # the get_columns might also be defined on a super class
    #     raise NotImplementedError


class DataframeConfig:
    """
    Base class for configs that depend on the Dataframe and which should update when the df changes
    """

    def update_state_based_on_new_df(self):
        """
        Method that is called when the df changed.
        The config should update its state to make sure that it is consistent with the new df
        e.g. that might mean adjusting the available column options based on what is actually
        available in the df
        """
        raise NotImplementedError

    def get_columns(self):
        """
        Method to return the columns of the dataframe that are used/specified as part of the config
        """
        raise NotImplementedError


class Configuration(PlotCreatorBlock):
    """
    The configuration base class provides methods to work with configurations and their lifecycle.
    All configurations are PlotCreatorBlocks.

    Implementations SHOULD implement the methods `get_code`, `is_valid`.
    In addition, you most likely also want to implement `render`.
    Optionally `init_configuration` can be implemented.

    See examples below for classes that inherit from Configuration.

    Notable attributes:
    name - str with name for the config e.g. shown in layout and search
    description - str with description e.g. shown in the search results
    show_in_config_selector - bool if the config can be selected in the config_selector
    can_be_added_multiple_times - bool if the config can be added multiple times to a figure
    """

    # attributes with their defaults
    name = None
    description = None

    show_in_config_selector = True
    can_be_added_multiple_times = False

    def get_code(self):
        """
        HAS TO BE OVERRIDEN

        :return code object for the config e.g. PlotlyFigureCode
        """
        raise NotImplementedError

    def is_valid(self):
        """
        HAS TO BE OVERRIDEN

        :return bool if the state of the config is valid
        """
        # this could be implemented implicitly within get_code via returning empty code
        # BUT this would not be so clean
        # also, sometimes we want to find (all / the last) valid item(s)
        # and this only works via this separation
        raise NotImplementedError

    # nearly always the user wants to override super().render()

    def init_configuration(self):
        """
        CAN BE OVERRIDEN

        This method is called after the class and their parents were setup.
        It should be used for setting up any initial state
        """
        pass

    def __init_subclass__(subclass):
        super().__init_subclass__()
        if subclass.name is None:
            subclass.name = subclass.__name__
        if subclass.description is None:
            subclass.description = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_tag("Configuration")
        self.init_configuration()

    def set_content(
        self,
        *embeddables,
        show_name_label=None,
        show_delete_button=None,
        show_not_supported_label=None,
        **kwargs,
    ):
        """
        Set the content of the config

        :param *embeddables: unpacked list of embeddable objects (widgets)

        :param show_name_label: bool, optional, if the config should have a name. Default is True.
        :param show_delete_button: bool, optional, if the config shows a delete button. Per default this is decided dynamically based on the fact if the config is required for the current figure or not.
        :param show_not_supported_label: bool, optional, if the config should show a label that it is not supported. Per default this is decided dynamically based on the current figure
        """
        if show_name_label is None:
            show_name_label = True  # default
        if show_not_supported_label is None:
            config_is_not_supported = (
                not self.plot_creator.get_figure_type().supports_config(self)
            )
            show_not_supported_label = config_is_not_supported
        if show_delete_button is None:
            config_is_required = self.plot_creator.get_figure_type().requires_config(
                self
            )
            show_delete_button = not config_is_required
        super().set_content(
            *embeddables,
            show_name_label=show_name_label,
            show_delete_button=show_delete_button,
            show_not_supported_label=show_not_supported_label,
            **kwargs,
        )

    def figure_type_did_change(self):
        """
        This method should be called when the figure type did change.
        """
        # update approach: maybe SUBSTITUTE the config with another similar config

        figure_type = self.plot_creator.get_figure_type()

        figure_does_not_support_config = not figure_type.supports_config(self)

        similar_config_class = (
            figure_type.maybe_get_supported_config_class_from_same_family(self)
        )
        there_is_a_similar_config_that_is_supported_by_the_figure = (
            similar_config_class is not None
        )

        if (
            self._belongs_to_a_config_family()
            and figure_does_not_support_config
            and there_is_a_similar_config_that_is_supported_by_the_figure
        ):
            new_config = similar_config_class(plot_creator=self.plot_creator)
            new_config.apply_family_state(self)
            new_config.render()
            self.plot_creator.replace_config(self, new_config)
        else:
            # when the figure is (not) supported by the config, the rendering will adjust appropriately
            self.render()

    def df_did_change(self):
        """
        This method should be called when the Dataframe did change.
        """
        if self._depends_on_df_state():
            self.show_needs_to_be_refreshed_label = True
            self.render()

    def adjust_to_new_df(self):
        """
        Thid method should be called when the config should adjust its state and layout
        to the new Dataframe
        """
        if self._depends_on_df_state():
            self.update_state_based_on_new_df()
            self.show_needs_to_be_refreshed_label = False
            self.render()

    def _depends_on_df_state(self):
        """
        :return bool if the config depends on the state of the Dataframe
        """
        return issubclass(self.__class__, DataframeConfig)

    def _belongs_to_a_config_family(self):
        """
        :return bool if the config belongs to a config family
        """
        return config_class_belongs_to_any_family(self.__class__)

    @classmethod
    def is_similar_to(cls, config):
        """
        :param config: another config
        :return bool if the current config class is similar to the other config
        """
        if inspect.isclass(config):
            config_class = config
        else:
            config_class = config.__class__

        same_class = config_class is cls
        same_family = config_classes_belong_to_same_family(cls, config_class)

        return same_class or same_family


###################################
##################### Custom configurations that do not follow a special pattern or are not reused too often
###################################


class Sampling(Configuration):
    """
    The configuration that enables the sampling.

    ATTENTION: this is a unique/special configuration
    It is not shown in the config_selector and, in addition,
    the config does never show its name, the delete buton and the not supported label.
    This behavior is specified in render() as part of set_content.

    The only time when this config renders some output is
    when the sampling is active.

    The sampling depends on the number of rows of the Dataframe and the config
    `plotly.row_limit`. The user has the ability to deactivate the sampling.
    """

    show_in_config_selector = False

    def init_configuration(self):
        self.recommend_sampling = self._recommend_sampling()
        self.user_accepts_sampling = True

    def _recommend_sampling(self):
        df = self.plot_creator.df_manager.get_current_df()
        return df.shape[0] > get_option("plotly.row_limit")

    def _remove_sampling(self):
        self.user_accepts_sampling = False
        self.render()
        self.plot_creator.force_figure_update()

    def render(self):
        self.recommend_sampling = self._recommend_sampling()
        if self.user_accepts_sampling and self.recommend_sampling:
            plotly_row_limit = get_option("plotly.row_limit")
            output = widgets.VBox(
                [
                    notification(
                        f"Your dataframe has more than {plotly_row_limit:,} rows. This can lead to long loading times or your plot might never show up. Therefore, we randomly sampled {plotly_row_limit:,} rows. You can remove the sampling. Alternatively, filter or aggregate the data before plotting.",
                        type="warning",
                    ),
                    Button(
                        description="Remove sampling",
                        on_click=lambda _: self._remove_sampling(),
                    ),
                    widgets.HTML("<br>"),
                ]
            )
        else:
            output = widgets.VBox()  # render nothing
        self.set_content(
            output,
            show_name_label=False,
            show_delete_button=False,
            show_not_supported_label=False,
        )

    def get_code(self):
        if self.user_accepts_sampling and self.recommend_sampling:
            code = [
                f""".sample(n={get_option("plotly.row_limit")}, replace=False, random_state={get_option("global.random_seed")}).sort_index()"""
            ]
        else:
            code = []
        return Code(df_adjustments=code)

    def is_valid(self):
        return True


class FigureExportAsStaticImage(Configuration):
    name = "Figure: export as static image"
    description = "Save image as png, jpeg, jpg, svg, pdf, web, eps"
    can_be_added_multiple_times = True

    def init_configuration(self):
        self.info = widgets.HTML(
            "Supported file types are png, jpeg, svg, pdf, webp, eps"
        )
        self.info_enter = widgets.HTML("Press ENTER button to execute")
        # Note: there is no default value because
        # otherwise the figure would always be directly exported to the default name when adding this config
        self.file_name = Text(
            placeholder="File name e.g. fig.png",
            focus_after_init=True,
            width="xl",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

    def render(self):
        self.set_content(self.file_name, self.info_enter, self.info)

    def get_code(self):
        file_name = string_to_code(self.file_name.value)
        return Code(figure_adjustments=f"""{FIGURE}.write_image({file_name})""")

    def is_valid(self):
        return self.file_name.value != ""


class FigureExportAsJSON(Configuration):
    name = "Figure: export as JSON file"
    description = "Save .json file"

    _file_extension = ".json"

    def init_configuration(self):
        self.info = widgets.HTML(f"The file should end with {self._file_extension}")
        self.info_enter = widgets.HTML("Press ENTER button to execute")
        # Note: there is no default value because
        # otherwise the figure would always be directly exported to the default name when adding this config
        self.file_name = Text(
            placeholder=f"File name e.g. fig{self._file_extension}",
            focus_after_init=True,
            width="xl",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

    def render(self):
        self.set_content(self.file_name, self.info_enter, self.info)

    def get_code(self):
        file_name = string_to_code(self.file_name.value)
        code = textwrap.dedent(
            f"""
            import plotly.io as pio
            pio.write_json({FIGURE}, {file_name})
            """
        ).strip()
        return Code(figure_adjustments=code)

    def is_valid(self):
        return self.file_name.value != ""


class FigureExportAsPlotlyFile(FigureExportAsJSON):
    name = "Figure: export as .plotly file"
    description = "Save figure for plotly chart editor"
    _file_extension = ".plotly"


COLOR_SEQUENCE_DEFAULT_THEME = "Default theme"
COLOR_SEQUENCE_CUSTOM_LIST = "Custom hex or css color sequence"


class ColorDiscreteTheme(Configuration):
    name = "Color: *discrete* theme"
    description = "Choose or create theme (palette, sequence)"

    def init_configuration(self):
        self.mode = Singleselect(
            options=[COLOR_SEQUENCE_DEFAULT_THEME, COLOR_SEQUENCE_CUSTOM_LIST],
            value=COLOR_SEQUENCE_DEFAULT_THEME,
            placeholder="Select mode",
            width="xl",
            on_change=lambda _: self._user_changed_the_mode(),
        )

        self.mode_outlet = widgets.VBox()
        self.mode_outlet.add_class("bamboolib-overflow-visible")

        self.theme = Singleselect(
            options=plotly_color_themes.QUALITATIVE_SEQUENCES,
            placeholder="Choose theme",
            set_soft_value=True,
            focus_after_init=self.focus_after_init,
            width="xl",
            on_change=lambda _: self.plot_creator.request_figure_update(),
        )

        self.color_list = ListInput(
            header=widgets.HTML("Create color theme - press ENTER when done"),
            item_class=Text,
            item_is_valid=lambda value: value != "",
            item_kwargs=dict(
                value="",
                placeholder="Color e.g. #228b22 or green",
                width="lg",
                on_submit=lambda _: self.plot_creator.request_figure_update(),
            ),
        )
        # Valid color inputs are a hex code e.g. <b>#ff0000</b>, a CSS color e.g. <b>green</b>, a rgb(a) code e.g. <b>rgb(255, 0, 0)</b>

        self.reverse_scale = widgets.Checkbox(value=False, description="Reverse scale")
        self.reverse_scale.add_class("bamboolib-checkbox")
        self.reverse_scale.observe(
            lambda _: self.plot_creator.request_figure_update(), names="value"
        )

    def _default_theme_is_selected(self):
        return self.mode.value == COLOR_SEQUENCE_DEFAULT_THEME

    def _user_changed_the_mode(self):
        self._update_mode_outlet()
        self.plot_creator.request_figure_update()

    def _update_mode_outlet(self):
        if self._default_theme_is_selected():
            self.mode_outlet.children = [self.theme]
        else:
            self.mode_outlet.children = [self.color_list]

    def render(self):
        self.set_content(self.mode, self.mode_outlet, self.reverse_scale)
        self._update_mode_outlet()

    def get_code(self):
        if self._default_theme_is_selected():
            code = self.theme.value
        else:
            code = self.color_list.value

        reversed = "[::-1]" if self.reverse_scale.value else ""
        return Code(kwargs=f"color_discrete_sequence={code}{reversed}")

    def is_valid(self):
        if self._default_theme_is_selected():
            return True
        else:
            return len(self.color_list.value) > 0


class LineTypeTheme(Configuration):
    name = "Line type: theme"
    description = "Set theme of styles (line dash sequence)"

    # https://plotly.com/javascript/reference/scatter/#scatter-line-dash

    def init_configuration(self):
        self.line_dash_sequence = ListInput(
            focus_after_init=self.focus_after_init,
            item_class=Singleselect,
            item_is_valid=lambda value: True,
            item_kwargs=dict(
                options=PLOTLY_LINESTYLE_OPTIONS,
                placeholder="Select style",
                set_soft_value=True,
                width="lg",
                on_change=lambda _: self.plot_creator.request_figure_update(),
            ),
        )

    def render(self):
        self.set_content(self.line_dash_sequence)

    def get_code(self):
        return Code(kwargs=f"line_dash_sequence={self.line_dash_sequence.value}")

    def is_valid(self):
        return True


class MarkTheme(Configuration):
    name = "Mark: theme"
    description = "Set theme of styles (symbol sequence)"

    # https://plotly.com/javascript/reference/scatter/#scatter-marker-symbol

    def init_configuration(self):
        self.symbol_sequence = ListInput(
            focus_after_init=self.focus_after_init,
            item_class=Singleselect,
            item_is_valid=lambda value: True,
            item_kwargs=dict(
                options=plotly_marker_options.MARKERS,
                placeholder="Select style",
                set_soft_value=True,
                width="lg",
                on_change=lambda _: self.plot_creator.request_figure_update(),
            ),
        )

    def render(self):
        self.set_content(self.symbol_sequence)

    def get_code(self):
        return Code(kwargs=f"symbol_sequence={self.symbol_sequence.value}")

    def is_valid(self):
        return True


COLOR_MAP_BY_CUSTOM_DICT = "Create custom dictionary"
COLOR_MAP_BY_VARIABLE = "Variable with dictionary"


# Thoughts:
# when specifying the values of the dict, we could perform auto-completion for column values
# however, this creates a dependency to the color column config
# when the color column config is not set, we cannot provide auto-completions
# when the color column config is set, we can provide auto-completions
# TODO: when the color column changes, we have to update the auto-completions (and maybe also show that the old values are wrong?)
#   => maybe via a listener to the other config
# solution EASIEST FOR THE START: free text input
#   => most flexibility but also chance for wrong inputs by user
# solution FAVORITE FOR LATER: singleselect that has optional completions and that does accept other values
#   => we dont have to provide options if no color config is set
#   => we can update the options when the color config changes without changing the old values
#   => we can show the user an error when the value is not inside the options
#   => we can show the user an error when no color config is selected
# solution: singleselect that enforces values
#   => we need to update the singleselect when the color column config changes
#   => we cannot show the config when no color config is present => we have to show an error then
#   => BAD we need to find a solution on how to update values when the color config changes
#        => BAD when the user changes the color config back and forth, this would destroy his other inputs
class ColorStyleForDiscreteValue(Configuration):
    """
    A config that allows the user to set a color style for a given discrete value.
    The user can either name the values via inputting key-value pairs for a dictionary OR
    they can specify the variable name of a dictionary.
    """

    name = "Color: style for *discrete* value"
    description = "Set hex or CSS color for individual values (map)"

    def init_configuration(self):
        self.usage_info = notification(
            """
        E.g. set the color <i>red</i> to value <i>male</i> in column <i>Gender</i><br>
        This requires that you added the <b>Color</b> property and selected a column
        """
        )

        self.mode = Singleselect(
            options=[COLOR_MAP_BY_CUSTOM_DICT, COLOR_MAP_BY_VARIABLE],
            value=COLOR_MAP_BY_CUSTOM_DICT,
            placeholder="Select mode",
            width="xl",
            on_change=lambda _: self._user_changed_the_mode(),
        )

        self.mode_outlet = widgets.VBox()
        self.mode_outlet.add_class("bamboolib-overflow-visible")

        self.variable_info = widgets.HTML(
            "Choose a variable that contains a dictionary"
        )
        self.variable = Singleselect(
            # Problem: when the user changes the symbols after the config got rendered, the user will not see the new symbols
            # Solutions:
            # when the symbols change, we have to update the options - how to detect this??
            # OR we allow the user to insert values that are not within the options
            # OR we enable the user to manually update the options e.g. via a refresh button
            options=list(self.plot_creator.df_manager.symbols.keys()),
            placeholder="Choose variable",
            set_soft_value=False,
            width="xl",
            on_change=lambda _: self.plot_creator.request_figure_update(),
        )

        self.color_map = DictInput(
            header=widgets.HTML("Create color dictionary - press ENTER when done"),
            item_class=SideBySideDictItem,
            focus_after_init=self.focus_after_init,
            key_class=Text,
            key_is_valid=lambda value: value != "",
            key_kwargs=dict(
                value="",
                placeholder="Column value",
                width="lg",
                on_submit=lambda _: self.plot_creator.request_figure_update(),
            ),
            value_class=Text,
            value_is_valid=lambda value: value != "",
            value_kwargs=dict(
                value="",
                placeholder="Color e.g. #228b22 or green",
                width="lg",
                on_submit=lambda _: self.plot_creator.request_figure_update(),
            ),
        )
        # Valid color inputs are a hex code e.g. <b>#ff0000</b>, a CSS color e.g. <b>green</b>, a rgb(a) code e.g. <b>rgb(255, 0, 0)</b>

    def _custom_color_map_is_selected(self):
        return self.mode.value == COLOR_MAP_BY_CUSTOM_DICT

    def _user_changed_the_mode(self):
        self._update_mode_outlet()
        self.plot_creator.request_figure_update()

    def _update_mode_outlet(self):
        if self._custom_color_map_is_selected():
            self.mode_outlet.children = [self.color_map]
        else:
            self.mode_outlet.children = [self.variable_info, self.variable]

    def render(self):
        self.set_content(self.usage_info, self.mode, self.mode_outlet)
        self._update_mode_outlet()

    def get_code(self):
        if self._custom_color_map_is_selected():
            value = self.color_map.value  # dict
        else:
            value = self.variable.value  # variable name
        return Code(kwargs=f"color_discrete_map={value}")

    def is_valid(self):
        if self._custom_color_map_is_selected():
            return True
        else:
            return self.variable.value is not None


class LineTypeStyleForValue(Configuration):
    name = "Line type: style for value"
    description = "Set style for individual values (line_dash_map)"

    def init_configuration(self):
        self.line_dash_map = DictInput(
            item_class=SideBySideDictItem,
            focus_after_init=self.focus_after_init,
            key_class=Text,
            key_is_valid=lambda value: value != "",
            key_kwargs=dict(
                value="",
                placeholder="Column value",
                width="lg",
                on_submit=lambda _: self.plot_creator.request_figure_update(),
            ),
            value_class=Singleselect,
            value_is_valid=lambda value: True,
            value_kwargs=dict(
                options=PLOTLY_LINESTYLE_OPTIONS,
                placeholder="Select style",
                set_soft_value=True,
                width="lg",
                on_change=lambda _: self.plot_creator.request_figure_update(),
            ),
        )

    def render(self):
        self.set_content(self.line_dash_map)

    def get_code(self):
        return Code(kwargs=f"line_dash_map={self.line_dash_map.value}")

    def is_valid(self):
        return True


class MarkStyleForValue(Configuration):
    name = "Mark: style for value"
    description = "Set style for individual values (symbol_map)"

    def init_configuration(self):
        self.symbol_map = DictInput(
            item_class=SideBySideDictItem,
            focus_after_init=self.focus_after_init,
            key_class=Text,
            key_is_valid=lambda value: value != "",
            key_kwargs=dict(
                value="",
                placeholder="Column value",
                width="lg",
                on_submit=lambda _: self.plot_creator.request_figure_update(),
            ),
            value_class=Singleselect,
            value_is_valid=lambda value: True,
            value_kwargs=dict(
                options=plotly_marker_options.MARKERS,
                placeholder="Select style",
                set_soft_value=True,
                width="lg",
                on_change=lambda _: self.plot_creator.request_figure_update(),
            ),
        )

    def render(self):
        self.set_content(self.symbol_map)

    def get_code(self):
        return Code(kwargs=f"symbol_map={self.symbol_map.value}")

    def is_valid(self):
        return True


# Open problem:
# It would be great to auto-complete column names here
# However, what do we do then if the df column names change?
# This is a similar issue to ColorStyleForDiscreteValue
# Currently, this is the problem of the user because we just do not perform auto-completion for the column names
class FigureColumnLabels(Configuration):
    name = "Figure: column labels"
    description = "Rename column labels"

    def init_configuration(self):
        self.labels = DictInput(
            header=widgets.HTML("Add new column names - press ENTER when done"),
            item_class=SideBySideDictItem,
            focus_after_init=self.focus_after_init,
            key_class=Text,
            key_kwargs=dict(
                value="",
                placeholder="Old column value",
                width="lg",
                on_submit=lambda _: self.plot_creator.request_figure_update(),
            ),
            key_is_valid=lambda value: value != "",
            value_class=Text,
            value_kwargs=dict(
                value="",
                placeholder="New column name",
                width="lg",
                on_submit=lambda _: self.plot_creator.request_figure_update(),
            ),
            value_is_valid=lambda value: value != "",
        )

    def render(self):
        self.set_content(self.labels)

    def get_code(self):
        return Code(kwargs=f"labels={self.labels.value}")

    def is_valid(self):
        return True


# Additional thoughts:
# the key_class could also provide auto-completion for column names - then we have the same problem like Labels_for_ColumnNames
# the value_class could also be a Multiselect
# however, then we need to handle the case when the dataframe columns or values change
# like with Labels_for_ColumnNames
class FigureCategoryOrders(Configuration):
    name = "Figure: category orders"
    description = "Set *exact* order for column values e.g. in axis or legend"

    def init_configuration(self):
        self.category_orders = DictInput(
            header=widgets.HTML("Order for each column - press ENTER when done"),
            item_class=IndentationDictItem,
            add_button_text="add column",
            focus_after_init=self.focus_after_init,
            key_class=Text,
            key_kwargs=dict(
                value="",
                placeholder="Column name",
                width="lg",
                on_submit=lambda _: self.plot_creator.request_figure_update(),
            ),
            key_is_valid=lambda value: value != "",
            value_class=ListInput,
            value_kwargs=dict(
                add_button_text="add column value",
                item_class=Text,
                item_kwargs=dict(
                    value="",
                    placeholder="Column value",
                    width="lg",
                    on_submit=lambda _: self.plot_creator.request_figure_update(),
                ),
                item_is_valid=lambda value: value != "",
            ),
            # no separate value validation needed because ListInput always returns a valid value
            value_is_valid=lambda value: True,
        )

    def render(self):
        self.set_content(self.category_orders)

    def get_code(self):
        return Code(kwargs=f"category_orders={self.category_orders.value}")

    def is_valid(self):
        return True


class XAxisCategoryOrder(Configuration):
    name = "xAxis: category order"
    description = (
        "Sort values on xAxis alphabetically or by bar height - ascending or descending"
    )
    # synonyms: lexicographically

    def init_configuration(self):
        self.choice = Singleselect(
            options=[
                ("Ascending alphabetically", "category ascending"),
                ("Descending alphabetically", "category descending"),
                ("Ascending by bar height", "total ascending"),
                ("Descending by bar height", "total descending"),
            ],
            focus_after_init=True,
            set_soft_value=True,
            placeholder="Choose option",
            width="lg",
            on_change=lambda _: self.plot_creator.request_figure_update(),
        )

    def render(self):
        self.set_content(self.choice)

    def get_code(self):
        return Code(
            figure_adjustments=f"{FIGURE}.update_xaxes(categoryorder={string_to_code(self.choice.value)})"
        )

    def is_valid(self):
        return True


class XAxisType(Configuration):
    name = "xAxis: type"
    description = "Set type to linear, logarithmic, categorical, or date"

    def init_configuration(self):
        self.choice = Singleselect(
            options=[
                ("Linear", "linear"),
                ("Logarithmic", "log"),
                ("Date", "date"),
                ("Categorical", "category"),
            ],
            focus_after_init=True,
            set_soft_value=True,
            placeholder="Choose option",
            width="lg",
            on_change=lambda _: self.plot_creator.request_figure_update(),
        )

    def render(self):
        self.set_content(self.choice)

    def get_code(self):
        return Code(
            figure_adjustments=f"{FIGURE}.update_xaxes(type={string_to_code(self.choice.value)})"
        )

    def is_valid(self):
        return True


class ShapeDrawRectangle(Configuration):
    name = "Shape: draw rectangle"
    description = "Add rectangle as geometric overlay on top of the figure"
    can_be_added_multiple_times = True

    default_opacity = 0.8

    def init_configuration(self):
        self.x_from = Text(
            value="0",
            placeholder="from",
            focus_after_init=True,
            width="xxs",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.x_to = Text(
            value="1",
            placeholder="to",
            width="xxs",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.y_from = Text(
            value="0",
            placeholder="from",
            width="xxs",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.y_to = Text(
            value="1",
            placeholder="to",
            width="xxs",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.fillcolor = Text(
            value="green",
            placeholder="fillcolor",
            width="sm",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.opacity = Text(
            value=f"{self.default_opacity}",
            placeholder="opacity",
            width="xxs",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

    def render(self):
        x_line = widgets.HBox(
            [widgets.HTML("x from"), self.x_from, widgets.HTML("to"), self.x_to]
        )
        y_line = widgets.HBox(
            [widgets.HTML("y from"), self.y_from, widgets.HTML("to"), self.y_to]
        )
        color_line = widgets.HBox(
            [self.fillcolor, widgets.HTML("with opacity"), self.opacity]
        )
        self.set_content(x_line, y_line, color_line)

    def get_code(self):
        x_from = self.x_from.value
        x_to = self.x_to.value
        y_from = self.y_from.value
        y_to = self.y_to.value
        opacity = self.opacity.value
        # Attention: fillcolor needs to be a string in the code
        # all the other arguments are numbers
        fillcolor = string_to_code(self.fillcolor.value)

        has_valid = lambda config: self.plot_creator.has_similar_and_valid_config(
            config
        )

        if has_valid(FacetRow) or has_valid(FacetColumn):
            code_str = textwrap.dedent(
                f"""
                for row_idx, row_figs in enumerate({FIGURE}._grid_ref):
                    for col_idx, col_fig in enumerate(row_figs):
                        {FIGURE}.add_shape(type='rect', x0={x_from}, x1={x_to}, y0={y_from}, y1={y_to}, fillcolor={fillcolor},
                                           opacity={opacity}, xref='x', yref='y', layer='below', row=row_idx+1, col=col_idx+1)
            """
            ).strip()
        else:
            # Attention: first dedent, then strip in order to preserve the relative whitespace between first and second line
            # when done the other way around, strip will delete all whitespaces before the start of the first line
            # but the second line will keep all whitespace and thus, the second line will have more whitespaces
            code_str = textwrap.dedent(
                f"""
                {FIGURE}.add_shape(type='rect', x0={x_from}, x1={x_to}, y0={y_from}, y1={y_to}, fillcolor={fillcolor},
                                   opacity={opacity}, xref='x', yref='y', layer='below')
            """
            ).strip()
        return Code(figure_adjustments=code_str)

    def is_valid(self):
        # maybe later add validation for the inputs e.g. turn them into float or integer inputs
        return True


class ShapeDrawLine(Configuration):
    name = "Shape: draw line"
    description = "Add line as geometric overlay on top of the figure"
    can_be_added_multiple_times = True

    default_opacity = 0.8

    def init_configuration(self):
        self.x_from = Text(
            value="0",
            placeholder="from",
            focus_after_init=True,
            width="xxs",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.x_to = Text(
            value="1",
            placeholder="to",
            width="xxs",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.y_from = Text(
            value="0",
            placeholder="from",
            width="xxs",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.y_to = Text(
            value="1",
            placeholder="to",
            width="xxs",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.color = Text(
            value="green",
            placeholder="color",
            width="sm",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.opacity = Text(
            value=f"{self.default_opacity}",
            placeholder="opacity",
            width="xxs",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.linestyle = Singleselect(
            options=PLOTLY_LINESTYLE_OPTIONS,
            placeholder="Choose style",
            set_soft_value=True,
            width="xxs",
            on_change=lambda _: self.plot_creator.request_figure_update(),
        )

        self.linewidth = Text(
            value="1",
            placeholder="line width",
            width="xxs",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

    def render(self):
        x_line = widgets.HBox(
            [widgets.HTML("x from"), self.x_from, widgets.HTML("to"), self.x_to]
        )
        y_line = widgets.HBox(
            [widgets.HTML("y from"), self.y_from, widgets.HTML("to"), self.y_to]
        )
        color_line = widgets.HBox(
            [self.color, widgets.HTML("with opacity"), self.opacity]
        )
        linestyle_line = widgets.HBox(
            [self.linestyle, widgets.HTML("with width"), self.linewidth]
        )
        linestyle_line.add_class("bamboolib-overflow-visible")
        self.set_content(x_line, y_line, color_line, linestyle_line)

    def get_code(self):
        x_from = self.x_from.value
        x_to = self.x_to.value
        y_from = self.y_from.value
        y_to = self.y_to.value
        opacity = self.opacity.value
        linewidth = self.linewidth.value
        # Attention: color and linestyle need to be a string in the code
        # all the other arguments are numbers
        color = string_to_code(self.color.value)
        linestyle = string_to_code(self.linestyle.value)

        has_valid = lambda config: self.plot_creator.has_similar_and_valid_config(
            config
        )

        if has_valid(FacetRow) or has_valid(FacetColumn):
            code_str = textwrap.dedent(
                f"""
                for row_idx, row_figs in enumerate({FIGURE}._grid_ref):
                    for col_idx, col_fig in enumerate(row_figs):
                        {FIGURE}.add_shape(type='line', x0={x_from}, x1={x_to}, y0={y_from}, y1={y_to}, opacity={opacity},
                                            line=dict(color={color}, width={linewidth}, dash={linestyle}),
                                            xref='x', yref='y', layer='above', row=row_idx+1, col=col_idx+1)
            """
            ).strip()
        else:
            # Attention: first dedent, then strip in order to preserve the relative whitespace between first and second line
            # when done the other way around, strip will delete all whitespaces before the start of the first line
            # but the second line will keep all whitespace and thus, the second line will have more whitespaces
            code_str = textwrap.dedent(
                f"""
                {FIGURE}.add_shape(type='line', x0={x_from}, x1={x_to}, y0={y_from}, y1={y_to}, opacity={opacity},
                                    line=dict(color={color}, width={linewidth}, dash={linestyle}),
                                    xref='x', yref='y', layer='above')
            """
            ).strip()
        return Code(figure_adjustments=code_str)

    def is_valid(self):
        # maybe later add validation for the inputs e.g. turn them into float or integer inputs
        return True


class AnyAxisRotateAxisLabels(Configuration):
    """
    Config base class for rotating axis labels

    Children should provide
    axis_name: str
    axis_code: str
    """

    # Attention: name is set dynamically in __init_subclass__
    description = "Rotate text of axis marks (tickangle)"

    def __init_subclass__(subclass):
        super().__init_subclass__()
        subclass.name = f"{subclass.axis_name}: rotate axis labels"

    def init_configuration(self):
        self.input = Text(
            value="",
            placeholder="Rotation angle e.g. 90 or -90",
            focus_after_init=True,
            width="xl",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )
        self.usage_info = widgets.HTML(
            "Angle can range from -360 to 360. Press ENTER when done"
        )

    def render(self):
        self.set_content(self.input, self.usage_info)

    def get_code(self):
        return Code(
            figure_adjustments=f"{FIGURE}.update_{self.axis_code}(tickangle={self.input.value})"
        )

    def is_valid(self):
        try:
            return -360 <= int(self.input.value) <= 360
        except:
            return False


class XAxisRotateAxisLabels(AnyAxisRotateAxisLabels):
    axis_name = "xAxis"
    axis_code = "xaxes"


class YAxisRotateAxisLabels(AnyAxisRotateAxisLabels):
    axis_name = "yAxis"
    axis_code = "yaxes"


class ZAxisRotateAxisLabels(AnyAxisRotateAxisLabels):
    axis_name = "zAxis"
    axis_code = "zaxes"


class AnyAxisLinearScale(Configuration):
    """
    Config base class for setting the scale of an axis to linear

    Children should provide
    axis_name: str
    axis_code: str
    """

    # Attention: name is set dynamically in __init_subclass__
    description = "Set axis to be in linear scale (type)"

    def __init_subclass__(subclass):
        super().__init_subclass__()
        subclass.name = f"{subclass.axis_name}: linear scale"

    def init_configuration(self):
        self.input = widgets.Checkbox(value=True, description="Use linear scale")
        self.input.add_class("bamboolib-checkbox")
        self.input.observe(
            lambda _: self.plot_creator.request_figure_update(), names="value"
        )

    def render(self):
        self.set_content(self.input)

    def get_code(self):
        return Code(
            figure_adjustments=f"{FIGURE}.update_{self.axis_code}(type='linear')"
        )

    def is_valid(self):
        return self.input.value


class XAxisLinearScale(AnyAxisLinearScale):
    axis_name = "xAxis"
    axis_code = "xaxes"


class YAxisLinearScale(AnyAxisLinearScale):
    axis_name = "yAxis"
    axis_code = "yaxes"


class ZAxisLinearScale(AnyAxisLinearScale):
    axis_name = "zAxis"
    axis_code = "zaxes"


class AnyAxisLogScale(Configuration):
    """
    Config base class for setting the scale of an axis to log

    Children should provide
    axis_name: str
    axis_code: str
    """

    # Attention: name is set dynamically in __init_subclass__
    description = "Set axis to be in logarithmic scale (type)"

    def __init_subclass__(subclass):
        super().__init_subclass__()
        subclass.name = f"{subclass.axis_name}: log scale"

    def init_configuration(self):
        self.input = widgets.Checkbox(value=True, description="Use log scale")
        self.input.add_class("bamboolib-checkbox")
        self.input.observe(
            lambda _: self.plot_creator.request_figure_update(), names="value"
        )

    def render(self):
        self.set_content(self.input)

    def get_code(self):
        return Code(
            figure_adjustments=f"{FIGURE}.update_{self.axis_code}(type='log', tickformat='.1e')"
        )

    def is_valid(self):
        return self.input.value


class XAxisLogScale(AnyAxisLogScale):
    axis_name = "xAxis"
    axis_code = "xaxes"


class YAxisLogScale(AnyAxisLogScale):
    axis_name = "yAxis"
    axis_code = "yaxes"


class ZAxisLogScale(AnyAxisLogScale):
    axis_name = "zAxis"
    axis_code = "zaxes"


class AnyAxisDistanceBetweenTicks(Configuration):
    """
    Config base class for setting the interval between ticks of an axis

    Children should provide
    axis_name: str
    axis_code: str
    """

    # Attention: name is set dynamically in __init_subclass__
    description = "Set interval between axis ticks (dtick)"

    def __init_subclass__(subclass):
        super().__init_subclass__()
        subclass.name = f"{subclass.axis_name}: distance between ticks"

    def init_configuration(self):
        self.input = Text(
            value="",
            placeholder="Distance value e.g. 100 or 0.1",
            focus_after_init=True,
            width="xl",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

    def render(self):
        self.set_content(self.input)

    def get_code(self):
        return Code(
            figure_adjustments=f"{FIGURE}.update_{self.axis_code}(dtick={self.input.value})"
        )

    def is_valid(self):
        try:
            float(self.input.value)
            return True
        except:
            return False


class XAxisDistanceBetweenTicks(AnyAxisDistanceBetweenTicks):
    axis_name = "xAxis"
    axis_code = "xaxes"


class YAxisDistanceBetweenTicks(AnyAxisDistanceBetweenTicks):
    axis_name = "yAxis"
    axis_code = "yaxes"


class ZAxisDistanceBetweenTicks(AnyAxisDistanceBetweenTicks):
    axis_name = "zAxis"
    axis_code = "zaxes"


class AnyAxisTitle(Configuration):
    """
    Config base class for setting the title of an axis

    Children should provide
    axis_name: str
    axis_code: str
    """

    # Attention: name, default_value are set dynamically in __init_subclass__
    description = "Set title of axis (title_text)"

    def __init_subclass__(subclass):
        super().__init_subclass__()
        subclass.name = f"{subclass.axis_name}: title"
        subclass.default_value = f"{subclass.axis_name} title"

    def init_configuration(self):
        self.input = Text(
            value=self.default_value,
            placeholder="Title",
            focus_after_init=True,
            width="xl",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )
        self.usage_info = widgets.HTML("Press ENTER when done.")

    def render(self):
        self.set_content(self.input, self.usage_info)

    def get_code(self):
        title = string_to_code(self.input.value)
        return Code(
            figure_adjustments=f"{FIGURE}.update_{self.axis_code}(title_text={title})"
        )

    def is_valid(self):
        # also allow empty string when the user wants to remove the axis title
        return True


class XAxisTitle(AnyAxisTitle):
    axis_name = "xAxis"
    axis_code = "xaxes"


class YAxisAxisTitle(AnyAxisTitle):
    axis_name = "yAxis"
    axis_code = "yaxes"


class ZAxisAxisTitle(AnyAxisTitle):
    axis_name = "zAxis"
    axis_code = "zaxes"


class FigureAutoSize(Configuration):
    name = "Figure: auto-size"
    description = "Toggle plotly autoscaling of figure size when resizing the browser window (autosize)"

    def init_configuration(self):
        self.input = widgets.Checkbox(value=False, description="Use auto-size")
        self.input.add_class("bamboolib-checkbox")
        self.input.observe(
            lambda _: self.plot_creator.request_figure_update(), names="value"
        )

    def render(self):
        self.set_content(self.input)

    def get_code(self):
        return Code(
            figure_adjustments=f"{FIGURE}.update_layout(autosize={self.input.value})"
        )

    def is_valid(self):
        return True


class LegendTitle(Configuration):
    name = "Legend: title"
    description = "Set title text for legend"

    def init_configuration(self):
        self.input = Text(
            value="Legend title",
            placeholder="Title",
            focus_after_init=True,
            width="xl",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )
        self.usage_info = widgets.HTML("Press ENTER when done.")

    def render(self):
        self.set_content(self.input, self.usage_info)

    def get_code(self):
        title = string_to_code(self.input.value)
        return Code(
            figure_adjustments=f"{FIGURE}.update_layout(legend_title_text={title})"
        )

    def is_valid(self):
        # also allow empty string when the user wants to remove the axis title
        return True


class XAxisRangeSlider(Configuration):
    name = "xAxis: range slider"
    description = "Show a range slider"

    def init_configuration(self):
        self.input = widgets.Checkbox(value=True, description="Show range slider")
        self.input.add_class("bamboolib-checkbox")
        self.input.observe(
            lambda _: self.plot_creator.request_figure_update(), names="value"
        )

    def render(self):
        self.set_content(self.input)

    def get_code(self):
        return Code(
            figure_adjustments=f"{FIGURE}.update_layout(xaxis_rangeslider_visible={self.input.value})"
        )

    def is_valid(self):
        return True


class XAxisDefaultDateRangeSelectors(Configuration):
    name = "xAxis: date range selectors"
    description = "Show range selectors e.g. 1 month, 6 months, 1 year, YTD, all"

    def init_configuration(self):
        self.input = widgets.Checkbox(
            value=True, description="Show date range selectors"
        )
        self.input.add_class("bamboolib-checkbox")
        self.input.observe(
            lambda _: self.plot_creator.request_figure_update(), names="value"
        )

    def render(self):
        self.set_content(self.input)

    def get_code(self):
        return Code(
            figure_adjustments=textwrap.dedent(
                f"""
            {FIGURE}.update_layout(xaxis_rangeselector_buttons=list([
                            dict(label="1m", count=1, step="month", stepmode="backward"),
                            dict(label="6m", count=6, step="month", stepmode="backward"),
                            dict(label="YTD", count=1, step="year", stepmode="todate"),
                            dict(label="1y", count=1, step="year", stepmode="backward"),
                            dict(step="all")
                        ]))
                                                """
            ).strip()
        )

    def is_valid(self):
        return self.input.value


class CandlestickProperties(DataframeConfig, Configuration):
    name = "Candlestick properties"
    description = (
        ""  # won't be shown because the config is required in CandlestickChart
    )

    def init_configuration(self):
        columns = self.get_options()

        def create_singleselect(default, focus_after_init=False):
            return Singleselect(
                options=columns,
                value=default,  # try to set value if it is the same as the default
                placeholder=f"{default} column, required",
                # Attention: do not set set_soft_value to True because
                # then update_state_based_on_new_df might fail if there are no options
                set_soft_value=False,
                width="xl",
                focus_after_init=focus_after_init,
                on_change=lambda _: self.plot_creator.request_figure_update(),
            )

        self.date_column = create_singleselect(default="Date")
        self.open_column = create_singleselect(default="Open")
        self.high_column = create_singleselect(default="High")
        self.low_column = create_singleselect(default="Low")
        self.close_column = create_singleselect(default="Close")

    def render(self):
        self.set_content(
            self.date_column,
            self.open_column,
            self.high_column,
            self.low_column,
            self.close_column,
        )

    def get_code(self):
        date_column = string_to_code(self.date_column.value)
        open_column = string_to_code(self.open_column.value)
        high_column = string_to_code(self.high_column.value)
        low_column = string_to_code(self.low_column.value)
        close_column = string_to_code(self.close_column.value)

        return Code(
            figure_adjustments=textwrap.dedent(
                f"""
            {FIGURE}.add_trace(go.Candlestick(
                            x={DF_OLD}[{date_column}], open={DF_OLD}[{open_column}], high={DF_OLD}[{high_column}],
                            low={DF_OLD}[{low_column}], close={DF_OLD}[{close_column}]))
                                                """
            ).strip()
        )

    def is_valid(self):
        return all(
            [
                column.value is not None
                for column in [
                    self.date_column,
                    self.open_column,
                    self.high_column,
                    self.low_column,
                    self.close_column,
                ]
            ]
        )

    def get_options(self):
        return list(self.plot_creator.df_manager.get_current_df().columns)

    def update_state_based_on_new_df(self):
        options = self.get_options()

        for singleselect in [
            self.date_column,
            self.open_column,
            self.high_column,
            self.low_column,
            self.close_column,
        ]:
            singleselect.options = options

    def get_columns(self):
        # when plot creator wants to know which columns are used
        # can be added later via reading from the singleselects above
        return []


###################################
##################### HTML hint
###################################


class HTMLHint(Configuration):
    """
    Config base class for showing a hint that contains HTML.
    The config does not produce any code.

    Children should provide
    name: str
    description: str, optional
    html: str
    """

    html = "TO BE OVERRIDEN"

    def render(self):
        self.set_content(widgets.HTML(self.html))

    def get_code(self):
        return Code()

    def is_valid(self):
        # make sure that the HTML hint will not trigger the "is required" logic when used as required_config
        return True


class TreemapHint(HTMLHint):
    name = "Treemap: hint"
    html = """
        <p>Per default the sector size is the row count for each cluster.</p>
        <p>You can click on clusters to zoom in and click on the top to zoom out.</p>
    """


class TreemapAggregationFunctionHint(HTMLHint):
    name = "Treemap: aggregation function"
    description = "Use min, mean, max, median as groupby function"
    html = """
        <p>A treemap does not support aggregation functions like min, mean, max or median.</p>
        <p>The sector size is calculated either via the row count or the sum of the <b>sector size</b> column.</p>
        <p>Maybe you can achieve your goal with a box plot or a bar chart?</p>
    """


###################################
##################### FakeDoorDemandTest
###################################


class FakeDoorDemandTest(HTMLHint):
    """
    Config base class for creating a fake door demand test
    Read more about "fake doors" in the book "Inspired - how to create products customers love"

    Children should provide:
    name: str
    description: str
    """

    # maybe later: log when a user wanted to enter a fake door

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        feature_name = self.name
        self.html = f"""Currently, '<b>{feature_name}</b>' is not yet supported.<br>
        If you need this feature, please contact us via<br>
        <a href="mailto:bamboolib-feedback@databricks.com?subject=Feature request '{feature_name}'&body=Hi, I would like to request the plotting feature '{feature_name}'. It is important to me because ..." target="_blank">bamboolib-feedback@databricks.com</a>"""


class Animation_DemandTest(FakeDoorDemandTest):
    name = "Figure: add animation"
    description = "Add one or more animations"


###################################
##################### MinMaxRange
###################################


class AnyDimensionMinMaxRangeKwarg(Configuration):
    """
    Config base class for setting the min/max range for a dimension

    Children should provide
    name: str
    description: str
    kwarg: str
    """

    kwarg = "TO BE OVERRIDEN"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.min_number = Text(
            placeholder="min e.g. 0 or 0.1",
            focus_after_init=True,
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.max_number = Text(
            placeholder="max e.g. 5 or 12.2",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

        self.range_box = widgets.HBox([self.min_number, self.max_number])

        self.usage_info = widgets.HTML(
            "You need to set min and max. Press ENTER when done."
        )

    def render(self):
        self.set_content(self.range_box, self.usage_info)

    def get_code(self):
        return Code(
            kwargs=f"{self.kwarg}=({self.min_number.value}, {self.max_number.value})"
        )

    def is_valid(self):
        try:
            float(self.min_number.value)
            float(self.max_number.value)
            return True
        except:
            return False


class XAxisMinMaxRange(AnyDimensionMinMaxRangeKwarg):
    name = "xAxis: min & max range"
    description = "Set the minimum and maximum values of the axis"
    kwarg = "range_x"


class YAxisMinMaxRange(AnyDimensionMinMaxRangeKwarg):
    name = "yAxis: min & max range"
    description = "Set the minimum and maximum values of the axis"
    kwarg = "range_y"


class ZAxisMinMaxRange(AnyDimensionMinMaxRangeKwarg):
    name = "zAxis: min & max range"
    description = "Set the minimum and maximum values of the axis"
    kwarg = "range_z"


class ColorContinuousThemeRange(AnyDimensionMinMaxRangeKwarg):
    name = "Color: continuous theme range"
    description = "Set the minimum and maximum values of color scale"
    kwarg = "range_color"


###################################
##################### textfield
###################################


class TextfieldKwarg(Configuration):
    """
    A config base class for kwarg configs that require a text input

    Children should provide
    name: str
    description: str
    kwarg: str
    placeholder: str

    Optional:
    value: str
    has_string_value: bool if the input value should be interpreted as string or raw code
    """

    kwarg = "TO BE OVERRIDEN"

    placeholder = "TO BE OVERRIDEN"
    value = ""
    has_string_value = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.textfield = Text(
            value=self.value,
            placeholder=self.placeholder,
            focus_after_init=True,
            width="xl",
            on_submit=lambda _: self.plot_creator.request_figure_update(),
        )

    def render(self):
        self.set_content(self.textfield)

    def get_code(self):
        # Observation: this code is very similar to SingleselectKwarg
        # maybe we want to refactor this at some point if this becomes even more common
        if self.has_string_value:
            value = string_to_code(self.textfield.value)
        else:
            value = self.textfield.value
        return Code(kwargs=f"{self.kwarg}={value}")

    def is_valid(self):
        return self.textfield.value != ""


##################### value should be interpreted as positive integer


class PositiveIntegerKwarg(TextfieldKwarg):
    """
    A config base class for kwarg configs that specify a positive integer

    Children should provide
    name: str
    description: str
    kwarg: str
    placeholder: str

    Optional:
    value: str
    """

    def is_valid(self):
        try:
            return int(self.textfield.value) > 0
        except:
            return False


class FigureWidth(PositiveIntegerKwarg):
    name = "Figure: width"
    description = "Set plot width in pixel (size)"
    kwarg = "width"
    placeholder = "Width in pixel e.g. 400"


class FigureHeight(PositiveIntegerKwarg):
    name = "Figure: height"
    kwarg = "height"
    description = "Set plot height in pixel (size)"
    placeholder = "Height in pixel e.g. 600"
    value = "600"


class FigureNumberOfBins(PositiveIntegerKwarg):
    name = "Figure: number of bins"
    description = "Set the number of bins"
    kwarg = "nbins"
    placeholder = "Positive integer e.g. 10"


class XAxisNumberOfBins(FigureNumberOfBins):
    name = "xAxis: number of bins"
    description = "Set the number of bins"
    kwarg = "nbinsx"


class YAxisNumberOfBins(FigureNumberOfBins):
    name = "yAxis: number of bins"
    description = "Set the number of bins"
    kwarg = "nbinsy"


class MarkMaxSize(PositiveIntegerKwarg):
    name = "Mark: max size"
    description = "Set the maximum size of a marker"
    kwarg = "size_max"
    placeholder = "Positive integer e.g. 20"
    value = "20"


class FacetColumnWrap(PositiveIntegerKwarg):
    name = "Facet: column wrap"
    description = "Limit maximum number of columns in a row"
    kwarg = "facet_col_wrap"
    placeholder = "Number of columns e.g. 3"
    value = "3"


class TreemapMaxDepth(PositiveIntegerKwarg):
    name = "Treemap: max depth"
    description = "Set the number of hierarchies to display at once"
    kwarg = "maxdepth"
    placeholder = "Maximal depth e.g. 3"
    value = "3"


##################### value should be interpreted as float


class ColorContinuousThemeMidpoint(TextfieldKwarg):
    name = "Color: continuous theme midpoint"
    description = "Set the midpoint of the continuous color scale"
    kwarg = "color_continuous_midpoint"
    placeholder = "Number of midpoint e.g. 3.5"

    def is_valid(self):
        try:
            return float(self.textfield.value)
        except:
            return False


##################### value should be interpreted as float in [0, 1]


class FloatBetween0And1Kwarg(TextfieldKwarg):
    """
    A config base class for kwarg configs that specify a float between 0 and 1

    Children should provide
    name: str
    description: str
    kwarg: str
    placeholder: str

    Optional:
    value: str
    """

    def is_valid(self):
        try:
            return 0 <= float(self.textfield.value) <= 1
        except:
            return False


class ColorOpacity(FloatBetween0And1Kwarg):
    name = "Color: opacity"
    description = "Set opacity of plot markers (points, bars, etc.)"
    kwarg = "opacity"
    placeholder = "Number between 0 and 1 e.g. 0.3"


class FacetRowSpacing(FloatBetween0And1Kwarg):
    name = "Facet: row spacing"
    description = "During faceting: set space between rows"
    kwarg = "facet_row_spacing"
    placeholder = "Number between 0 and 1 e.g. 0.02"
    value = "0.02"


class FacetColumnSpacing(FloatBetween0And1Kwarg):
    name = "Facet: column spacing"
    description = "During faceting: set space between columns"
    kwarg = "facet_col_spacing"
    placeholder = "Number between 0 and 1 e.g. 0.03"
    value = "0.03"


##################### value should be interpreted as string


class StringTextfieldKwarg(TextfieldKwarg):
    """
    A config base class for kwarg configs that specify a string

    Children should provide
    name: str
    description: str
    kwarg: str
    placeholder: str

    Optional:
    value: str
    """

    has_string_value = True


class FigureTitle(StringTextfieldKwarg):
    name = "Figure: title"
    description = "Set figure title"
    kwarg = "title"
    placeholder = "Figure title"


class TrendlineColor(StringTextfieldKwarg):
    name = "Trendline: color"
    description = "Set the trendline color"
    kwarg = "trendline_color_override"
    placeholder = "CSS color e.g. green or #DC143C"
    value = ""


###################################
##################### singleselect any - has subgroups for other types
###################################


class SingleselectKwarg(Configuration):
    """
    A config base class for kwarg configs that specify a singleselect

    Children should provide
    name: str
    description: str
    kwarg: str
    get_options: method that returns a list of options for a Singleselect

    Optional:
    placeholder: str
    default_value: any
    has_string_value: bool, default: False
    """

    kwarg = "TO BE OVERRIDEN"

    placeholder = "Choose option"
    has_string_value = False
    default_value = None

    # TODO: add this as requirement via abc
    def get_options(self):
        raise NotImplementedError

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.singleselect = Singleselect(
            options=self.get_options(),
            placeholder=self.placeholder,
            # Attention: do not set set_soft_value to True because
            # then update_state_based_on_new_df might fail if there are no options
            set_soft_value=False,
            width="xl",
            focus_after_init=self.focus_after_init,
            on_change=lambda _: self.plot_creator.request_figure_update(),
        )
        if self.default_value is not None:
            self.singleselect.value = self.default_value

    def render(self):
        self.set_content(self.singleselect)

    def get_code(self):
        # TODO: maybe we can pull that differentiation down
        # and create a to_code() method that handles the data type of the value
        # alternatively, the singleselect might do this implicitly in the future as part of __format__
        if self.has_string_value:
            value = string_to_code(self.singleselect.value)
        else:
            value = self.singleselect.value
        return Code(kwargs=f"{self.kwarg}={value}")

    def is_valid(self):
        return self.singleselect.value is not None

    def apply_family_state(self, config):
        self.singleselect.value = config.singleselect.value


DISCRETE_COLOR_SCALE = "discrete"
CONTINUOUS_COLOR_SCALE = "continuous"

# Attention: this is not a classical kwarg config because it does
# return code for a df_adjustment instead of kwargs
class ColorScaleType(SingleselectKwarg):
    name = "Color: scale type"
    description = "Discrete or continuous color scale"

    def get_options(self):
        return [DISCRETE_COLOR_SCALE, CONTINUOUS_COLOR_SCALE]

    def get_code(self):
        color_config = self.plot_creator.maybe_get_similar_config(Color)
        color_column = color_config.get_columns()[0]
        if self.singleselect.value == DISCRETE_COLOR_SCALE:
            dtype_dict = {color_column: "string"}
        else:  # continuous
            dtype_dict = {color_column: "float"}
        return Code(df_adjustments=f".astype({dtype_dict})")

    def is_valid(self):
        valid_value = self.singleselect.value is not None
        color_column_exists = self.plot_creator.has_similar_and_valid_config(Color)
        return color_column_exists and valid_value

    def get_color_scale_type(self):
        return self.singleselect.value


class GenericColorTheme(SingleselectKwarg):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.reverse_scale = widgets.Checkbox(value=False, description="Reverse scale")
        self.reverse_scale.add_class("bamboolib-checkbox")
        self.reverse_scale.observe(
            lambda _: self.plot_creator.request_figure_update(), names="value"
        )

    def render(self):
        self.set_content(self.singleselect, self.reverse_scale)


class ColorContinuousTheme(GenericColorTheme):
    name = "Color: *continuous* theme"
    description = "Set theme of scale (palette)"

    def get_options(self):
        return plotly_color_themes.CONTINUOUS_SCALES

    def get_code(self):
        kwarg = "color_continuous_scale"
        reversed = "_r" if self.reverse_scale.value else ""
        theme = string_to_code(f"{self.singleselect.value}{reversed}")

        return Code(kwargs=f"{kwarg}={theme}")


class BoxNotchStyle(SingleselectKwarg):
    name = "Box: notch style"
    description = "Display box with notches or not"
    kwarg = "notched"

    def get_options(self):
        return [("Show straight box", False), ("Show notches", True)]


class FigureAddBoxPlotToViolinPlot(SingleselectKwarg):
    name = "Figure: add box plot"
    description = "Add box plot to violin"
    kwarg = "box"

    def get_options(self):
        return [("Do not show box plot", False), ("Show box plot inside violins", True)]


class FigureShowDataPoints(SingleselectKwarg):
    name = "Figure: show data points"
    description = "Show ouliers, no data points or all data points"
    kwarg = "points"

    def get_options(self):
        return [
            ("Only show outliers", "'outliers'"),
            ("Show all points", "'all'"),
            ("Show no points", False),
        ]


class BarNormalizeValues(SingleselectKwarg):
    name = "Bar: normalize values"
    description = "Display bar heights as fraction (0 to 1) or percent (0 to 100)"
    kwarg = "barnorm"

    def get_options(self):
        return [
            ("No normalization", None),
            ("Fraction", "'fraction'"),
            ("Percentage", "'percent'"),
        ]


class FigureNormalizeGroups(SingleselectKwarg):
    name = "Figure: normalize groups"
    description = "Display groups as fraction (0 to 1) or percent (0 to 100)"
    kwarg = "groupnorm"

    def get_options(self):
        return [
            ("No normalization", None),
            ("Fraction", "'fraction'"),
            ("Percentage", "'percent'"),
        ]


class Trendline(SingleselectKwarg):
    name = "Trendline"
    description = "Show a trendline (linear or non-linear)"
    kwarg = "trendline"

    def get_options(self):
        return [
            ("No trendline", None),
            ("OLS: ordinary least squares", "'ols'"),
            ("LoWeSS: locally weighted scatterplot smoothing line", "'lowess'"),
        ]


class HistogramNormalization(SingleselectKwarg):
    name = "Histogram normalization"
    description = "Normalize bar heights"
    kwarg = "histnorm"

    def get_options(self):
        return [
            ("No normalization", None),
            ("Percentage", "'percent'"),
            ("Probability", "'probability'"),
            ("Density", "'density'"),
            ("Probability density", "'probability density'"),
        ]


class TreemapSectorSizeDisplayMode(SingleselectKwarg):

    name = "Sector size: display mode"
    description = "Calculate size of clusters relative to current level or relative to the total sum (branchvalues)"
    kwarg = "branchvalues"

    def get_options(self):
        return [
            ("Relative to current level (fill)", "'total'"),
            ("Relative to total sum", "'remainder'"),
        ]


###################################
##################### singleselect boolean
###################################


class BooleanKwarg(SingleselectKwarg):
    """
    A config base class for kwarg configs that specify a boolean

    Children should provide
    name: str
    description: str
    kwarg: str

    Optional:
    default_value: bool
    """

    placeholder = "Choose state"

    def get_options(self):
        return [("True", True), ("False", False)]


class CumulativeSumOfValues(BooleanKwarg):
    name = "Cumulative: sum values"
    description = "Show cumulative sum of values"
    kwarg = "cumulative"


class LineAddMarkers(BooleanKwarg):
    # Attention: it does not return kwarg code but figure_adjustments code
    name = "Line: add markers"
    description = "Add markers to data points"
    default_value = True

    def get_code(self):
        return Code(figure_adjustments=f"{FIGURE}.update_traces(mode='lines+markers')")

    def is_valid(self):
        return bool(self.singleselect.value)


###################################
##################### singleselect string
###################################


class SingleselectStringKwarg(SingleselectKwarg):
    """
    A config base class for kwarg configs that specify a string value from options

    Children should provide
    name: str
    description: str
    kwarg: str
    get_options: method that returns a list of str options for a Singleselect

    Optional:
    placeholder: str
    default_value: str
    """

    has_string_value = True


class FigureTheme(SingleselectStringKwarg):
    name = "Figure: theme"
    description = "Set plotly figure theme (template)"
    kwarg = "template"
    placeholder = "Choose template"

    def get_options(self):
        # https://plot.ly/python/templates/#theming-and-templates
        return [
            "ggplot2",
            "seaborn",
            "plotly",
            "plotly_white",
            "plotly_dark",
            "presentation",
            "xgridoff",
            "none",
        ]


class LineShapeInterpolation(SingleselectStringKwarg):
    name = "Line shape: interpolation"
    description = "Smoothen line plot"
    kwarg = "line_shape"

    def get_options(self):
        return ["linear", "spline"]


class FigureRenderMode(SingleselectStringKwarg):
    name = "Figure: render mode"
    description = "Set render mode"
    kwarg = "render_mode"

    def get_options(self):
        return ["auto", "svg", "webgl"]


class BarOrientation(SingleselectStringKwarg):
    name = "Bar: orientation"
    description = "Display bars vertically or horizontally"
    kwarg = "orientation"

    def get_options(self):
        return [("horizontal", "h"), ("vertical", "v")]


class BarDisplayMode(SingleselectStringKwarg):
    name = "Bar: display mode"
    description = "Set how bars are displayed e.g. stacked or side-by-side (barmode)"
    kwarg = "barmode"
    config_family = "barmode"

    def get_options(self):
        return ["relative", "overlay", "group"]


class AnyPlotColorGroupMode(SingleselectStringKwarg):
    """
    A config base class for setting the group mode for a figure

    Children should provide
    kwarg: str
    """

    name = "Color: group mode"

    def get_options(self):
        return [("Separate groups", "group"), ("Overlay groups", "overlay")]


class StripPlotColorGroupMode(AnyPlotColorGroupMode):
    kwarg = "stripmode"


class BoxPlotColorGroupMode(AnyPlotColorGroupMode):
    kwarg = "boxmode"


class ViolinPlotColorGroupMode(AnyPlotColorGroupMode):
    kwarg = "violinmode"


class FigureMarginalDistribution(SingleselectStringKwarg):
    name = "Figure: marginal distribution"
    description = "Add a marginal distribution to the plot"
    kwarg = "marginal"

    def get_options(self):
        return [
            ("Histogram", "histogram"),
            ("Box plot", "box"),
            ("Violin plot", "violin"),
            ("Rug plot", "rug"),
        ]


class XAxisMarginalDistribution(FigureMarginalDistribution):
    name = "xAxis: marginal distribution"
    description = "Add a marginal distribution of the x values"
    kwarg = "marginal_x"


class YAxisMarginalDistribution(FigureMarginalDistribution):
    name = "yAxis: marginal distribution"
    description = "Add a marginal distribution of the y values"
    kwarg = "marginal_y"


class HistogramAggregationFunction(SingleselectStringKwarg):
    name = "Histogram: aggregation function"
    description = "Apply aggregation function to bins (default: count)"
    kwarg = "histfunc"

    def get_options(self):
        return ["count", "sum", "avg", "min", "max"]


###################################
##################### Single column
###################################


class SingleDataframeColumnKwarg(DataframeConfig, SingleselectStringKwarg):
    """
    A config base class for kwarg configs that specifies a single column from the Dataframe

    Children should provide
    name: str
    description: str
    kwarg: str

    Optional:
    placeholder: str
    default_value: str
    """

    placeholder = "Choose column"

    def get_options(self):
        return list(self.plot_creator.df_manager.get_current_df().columns)

    def update_state_based_on_new_df(self):
        self.singleselect.options = self.get_options()

    def get_columns(self):
        return [self.singleselect.value]


class YAxisWithSingleColumn(YAxisConfigFamily, SingleDataframeColumnKwarg):
    name = "yAxis"
    description = "Set *single* column to be displayed on yAxis"
    kwarg = "y"

    def apply_family_state(self, config):
        columns = config.get_columns()
        if len(columns) == 0:
            pass
        else:
            self.singleselect.value = columns[0]


class XAxis(SingleDataframeColumnKwarg):
    name = "xAxis"
    description = "Set column to be displayed on xAxis"
    kwarg = "x"
    config_family = "xaxis"


class XAxisWithMaybeSortColumn(XAxis):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sort_column = widgets.Checkbox(value=True, description="Sort column")
        self.sort_column.add_class("bamboolib-checkbox")
        self.sort_column.observe(
            lambda _: self.plot_creator.request_figure_update(), names="value"
        )

    def render(self):
        self.set_content(self.singleselect, self.sort_column)

    def get_code(self):
        code_object = super().get_code()

        if self.sort_column.value:
            x_column = self.singleselect.value
            code_object.df_adjustments += [
                f".sort_values(by={[x_column]}, ascending=[True])"
            ]
        return code_object


class ZAxis(SingleDataframeColumnKwarg):
    name = "zAxis"
    description = "Set column to be displayed on zAxis"
    kwarg = "z"


class LineGroup(SingleDataframeColumnKwarg):
    name = "Line group"
    description = "Group lines if they have the same column value"
    kwarg = "line_group"


class Color(SingleDataframeColumnKwarg):
    name = "Color"
    description = "Add colors to plot based on column values"
    kwarg = "color"
    config_family = "color"


class MarkShape(SingleDataframeColumnKwarg):
    name = "Mark: shape"
    description = "Set marker shape based on column values"
    kwarg = "symbol"


class MarkSize(SingleDataframeColumnKwarg):
    name = "Mark: size"
    description = "Set size for markers based on column values"
    kwarg = "size"


class LineType(SingleDataframeColumnKwarg):
    name = "Line type"
    description = "Set dash style based on column values (line_dash)"
    kwarg = "line_dash"


class HoverTitle(SingleDataframeColumnKwarg):
    name = "Hover: title"
    description = "Set title in hover box based on column values (hover_name)"
    kwarg = "hover_name"


class MarkTextLabel(SingleDataframeColumnKwarg):
    name = "Mark: text label"
    description = "Add values of a column as text label to markers"
    kwarg = "text"


class FacetRow(SingleDataframeColumnKwarg):
    name = "Facet row"
    description = "Create vertical subplots based on column values"
    kwarg = "facet_row"


class FacetColumn(SingleDataframeColumnKwarg):
    name = "Facet column"
    description = "Create horizontal subplots based on column values"
    kwarg = "facet_col"


class XAxisErrorBar(SingleDataframeColumnKwarg):
    name = "xAxis: error bar"
    description = "Create error bar based on column values"
    kwarg = "error_x"


class XAxisNegativeErrorBar(SingleDataframeColumnKwarg):
    name = "xAxis: negative error bar"
    description = "Create error bar in negative direction based on column values"
    kwarg = "error_x_minus"


class YAxisErrorBar(SingleDataframeColumnKwarg):
    name = "yAxis: error bar"
    description = "Create error bar based on column values"
    kwarg = "error_y"


class YAxisNegativeErrorBar(SingleDataframeColumnKwarg):
    name = "yAxis: negative error bar"
    description = "Create error bar in negative direction based on column values"
    kwarg = "error_y_minus"


class ZAxisErrorBar(SingleDataframeColumnKwarg):
    name = "zAxis: error bar"
    description = "Create error bar based on column values"
    kwarg = "error_z"


class ZAxisNegativeErrorBar(SingleDataframeColumnKwarg):
    name = "zAxis: negative error bar"
    description = "Create error bar in negative direction based on column values"
    kwarg = "error_z_minus"


class PiechartSectorValue(SingleDataframeColumnKwarg):
    name = "Pie chart: sector value"
    description = "Set column that corresponds to the pie chart's sectors values"
    kwarg = "values"


class PiechartSectorLabel(SingleDataframeColumnKwarg):
    name = "Pie chart: sector label"
    description = "Set column with names for the sector labels"
    kwarg = "names"


class TreemapSectorSize(SingleDataframeColumnKwarg):
    name = "Treemap: sector size"
    description = (
        "Set column that is SUMMED for calculating the size of the sectors (values)"
    )
    kwarg = "values"


###################################
##################### Multiple columns
###################################


class MultipleDataframeColumnsKwarg(DataframeConfig, Configuration):
    """
    A config base class for kwarg configs that specify multiple columns from a Dataframe

    Children should provide
    name: str
    description: str
    kwarg: str

    Optional:
    placeholder: str
    default_value: list of str
    """

    kwarg = "TO BE OVERRIDEN"
    default_value = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.columns = Multiselect(
            options=self.get_options(),
            placeholder="Choose columns",
            width="xl",
            focus_after_init=self.focus_after_init,
            on_change=lambda _: self.plot_creator.request_figure_update(),
        )
        if self.default_value is not None:
            self.columns.value = self.default_value

    def render(self):
        self.set_content(self.columns)

    def get_code(self):
        return Code(kwargs=f"{self.kwarg}={self.columns.value}")

    def is_valid(self):
        return len(self.columns.value) > 0

    def get_options(self):
        return list(self.plot_creator.df_manager.get_current_df().columns)

    def update_state_based_on_new_df(self):
        self.columns.options = self.get_options()

    def get_columns(self):
        return self.columns.value


class YAxisWithMultipleColumns(YAxisConfigFamily, MultipleDataframeColumnsKwarg):

    name = "yAxis"
    description = "Set column(s) to be displayed on yAxis"
    kwarg = "y"

    def get_code(self):
        columns_count = len(self.columns.value)
        if columns_count == 1:
            # this fixes a plotly bug because the chart behaves differently if we pass a column kwarg as list or value e.g. for y-axis
            column = string_to_code(self.columns.value[0])
            return Code(kwargs=f"{self.kwarg}={column}")
        else:  # columns_count > 1:
            return Code(kwargs=f"{self.kwarg}={self.columns.value}")
        # columns_count <1 can never happen because config is not valid in this case

    def apply_family_state(self, config):
        self.columns.value = config.get_columns()


class HoverInfoColumns(MultipleDataframeColumnsKwarg):
    name = "Hover: info columns"
    description = "Column values that will appear in hover info as data"
    kwarg = "hover_data"

    def get_code(self):
        if self.columns.value is []:
            return Code()
        elif ALL_COLUMNS in self.columns.value:
            return Code(
                kwargs=f"{self.kwarg}={list(self.plot_creator.df_manager.get_current_df().columns)}"
            )
        else:
            return Code(kwargs=f"{self.kwarg}={self.columns.value}")

    def get_options(self):
        all_columns = [("[All columns in dataframe]", ALL_COLUMNS)]
        single_columns = [
            (name, name)
            for name in self.plot_creator.df_manager.get_current_df().columns
        ]
        return all_columns + single_columns


class FigureSelectColumns(MultipleDataframeColumnsKwarg):
    # this is an exception where the name contains a verb ("select")
    # usually the name only contains descriptive nouns
    name = "Figure: select columns"
    description = "Select subset of columns that is displayed (dimensions)"
    kwarg = "dimensions"


class TreemapHierarchy(MultipleDataframeColumnsKwarg):
    name = "Treemap: hierarchy"
    description = "Set columns for the nesting order of the clustering (path)"
    kwarg = "path"
