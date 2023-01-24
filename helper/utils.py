# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

from IPython.display import display
from pathlib import Path
import ipywidgets as widgets
import pandas as pd
import numpy as np
import datetime
import hashlib
# import analytics  # deactivated via removing import
import textwrap
import sys

from bamboolib import _environment as env
from bamboolib.setup.file_logger import file_logger

import bamboolib.config as config

# Attention: auth cannot be imported here due to circular import dependencies
# from bamboolib._authorization import auth

# Some symbols here are imported from gui_outlets
from bamboolib.widgets import CopyButton, CloseButton, BackButton, Text, Button


DF_OLD = "old_df__bamboolib_template_name"
DF_NEW = "new_df__bamboolib_template_name"

QUALTRICS_SURVEY_LINK_HREF = (
    "https://databricks.sjc1.qualtrics.com/jfe/form/SV_0UnuGyKmVO3pNVI"
)


def safe_cast(value, to_type, default=None):
    """
    Try to cast value to data type to_type. If casting doesn't work, use default value.

    :param value: any basic data type, most likely string.
    :param to_type: function used to cast value, e.g. int, float, str, ...
    """
    try:
        return to_type(value)
    except (ValueError, TypeError):
        return default


def list_to_string(list_, quoted=True):
    """
    Convert a list to a string.

    If quoted=True, quote all elements in list explicitely.
    """
    list_ = [str(item) for item in list_]  # eg this converts boolean lists
    if quoted:
        list_ = [f"'{item}'" for item in list_]
    return ", ".join(list_)


def execute_asynchronously(blocking_function, *args, **kwargs):
    """
    Enables a function to be called asynchronously (i.e. without blocking the main thread).
    """

    if env.DEACTIVATE_ASYNC_CALLS:
        blocking_function(*args, **kwargs)
    else:
        from threading import Thread

        t = Thread(target=blocking_function, args=args, kwargs=kwargs, daemon=True)
        t.start()


### activation logic and helper from edaviz ###


def notification(message, type="info"):
    """
    Create a notification. Important

    :param message: string message to display to user.
    :param type: string. Is one of ["info", "success", "warning", "error"].
    """
    ui = (
        '<div class="bamboolib-notification bamboolib-notification-%s">' "%s" "</div>"
    ) % (type, message)
    return widgets.HTML(ui)


def collapsible_notification(title, body, collapsed=True, type="info"):
    """
    A notification that can be collapsed.

    Example use case: You want to display a detailed help text to user without overcrowding the screen.

    :param title: string text visible to the user all the time.
    :param body: string text vivible to user only if notification isn't collapsed.
    :param collapsed: boolean. Shall notification be collapsed when displayed?
    :param type_: string. One of ["info", "success", "warning", "error"]

    :return: ipywidgets.Accordion that contains the warning text.
    """

    output = widgets.Accordion(children=[notification(body, type=type)])
    output.set_title(0, title)
    output.add_class("bamboolib-collapsible-notification")
    output.add_class(f"bamboolib-collapsible-notification-{type}")

    if collapsed:
        output.selected_index = None

    return output


def activate_license(email="", key="", _notification_embeddable=None):
    """
    Creates the license activation window where user enters email address and license key and
    agrees to our EULA.

    :return: ipywidgets.VBox containing all input widgets and submit button.
    """

    from bamboolib._authorization import auth
    from bamboolib.widgets import Text, BrowserCheck

    click_here_for_a_trial_license = """<a href="https://bamboolib.8080labs.com/trial/" target=_blank class="bamboolib-link">Click here</a> for a trial license."""
    header = widgets.HTML(
        f"""
        <h2>Activate bamboolib Pro</h2>
        Thank you for using bamboolib! It seems like you need a Pro license.<br>
        Still evaluating? {click_here_for_a_trial_license}<br>
        <br>
        """
    )

    input_email = Text(value=email, placeholder="Email")

    input_license_key = Text(value=key, placeholder="License key")

    input_submit = Button(
        description="Submit",
        disabled=True,
        style="primary",
        tooltip="Submit",
        icon="check",
    )

    input_accept_eula = widgets.Checkbox(
        value=False, description="", disabled=False, indent=False
    ).add_class("bamboolib-width-15px")
    accept_eula_text_and_link = widgets.HTML(
        (
            "I read and accept the "
            '<a href="https://bamboolib.com/eula" target=_blank class="bamboolib-link">'
            "terms and conditions"
            "</a>"
        )
    )

    input_content = widgets.VBox(
        [
            input_email,
            input_license_key,
            widgets.HBox([input_accept_eula, accept_eula_text_and_link]),
            widgets.HBox([input_submit]),
        ]
    )

    outlet = widgets.VBox()

    def show_loader():
        outlet.children = [widgets.HTML("Loading ...")]

    def click_submit(button):
        key = input_license_key.value.strip(" \t\n\r")
        email = input_email.value.strip(" \t\n\r")

        show_loader()
        embeddable = auth.activate(email, key)
        outlet.children = [embeddable]

    input_submit.on_click(click_submit)

    def enable_submit_button(value):
        input_submit.disabled = not value["new"]

    input_accept_eula.observe(enable_submit_button, "value")

    shown_elements = []
    if _notification_embeddable is not None:
        shown_elements.append(_notification_embeddable)
    shown_elements += [BrowserCheck(), header, input_content]
    outlet.children = shown_elements
    return outlet


# Attention: We don't add a dict type to symbols to make sure patching it to be a custom type
# won't break the code.
def get_dataframe_variable_names(df, symbols) -> list:
    """
    From all variables, get the ones that point to the dataframe df.

    Note: could be multiple if df was copied by reference.

    :param symbols: dict that contains all existing variable names.

    :return: list with the variable names that point to df.
    """
    return [
        key for key in symbols.keys() if df is symbols[key] and not key.startswith("_")
    ]


# TODO: later might derive the original_df_name from the code cell and not from the symbols?
def guess_dataframe_name(df: pd.DataFrame, symbols) -> str:
    """
    Based on the current symbols, guess which one is the dataframe the user is currently working with.
    """
    names = get_dataframe_variable_names(df, symbols)
    if len(names) == 0:  # if we could not find the df name
        # we use YOUR_DF because this string is used for code exports
        # and this is the quick fix so that the user realizes that this is not the real df name
        return "YOUR_DF"
        # MAYBE: add a warning that we could not find the real variable name?
    else:
        # We need to guess when more variables point to the same df.
        return names[0]


def _get_user_id(email=None, key=None):
    """Get the ID of our user."""
    from bamboolib._authorization import auth

    if email is None:
        email = auth.get_user_email()
    if key is None:
        key = auth.get_license_key()
    return f"{key};{email}"


def maybe_message_segment(message, details={}):
    """Send a message to segment if logging was allowed."""
    if env.LOG_USER_BEHAVIOR:
        pass
    else:
        return

    if config.is_in_confidential_mode():
        return
    from bamboolib._authorization import auth

    user_id = _get_user_id()
    # analytics.track(user_id, message, details)  # deactivated via removing import


def maybe_identify_segment(email, key):
    """Identify segment if logging was allowed."""
    if env.LOG_USER_BEHAVIOR:
        pass
    else:
        return

    if config.is_in_confidential_mode():
        return
    user_id = _get_user_id(email, key)

    # # deactivated via removing import
    # analytics.identify(
    #     user_id,
    #     {"email": email, "license_key": key, "created_at": datetime.datetime.now()},
    # )


def log_base(
    class_,
    category="No category",
    view="No view",
    action="No action",
    level="all",
    **kwargs,
):
    """
    Log base function.

    :param class_: string for the high-level log category, can be e.g. "bam_action_v1" or
        "setup_action_v1" (see the wrapper functions of log_base below for all kinds of class_).
    :param category: string for a wrapper-specific category. E.g. in log_action(), category can be
        "general", "viz", "export", "transformation", among others.
    :param view: string or object. The view from which the event as been logged, e.g. "Wrangler", "HistoryView",
        "PlotCreator". If view is an object (e.g. when we log TransormationPlugin classes), we
        overwrite it by the name of the class that is logged.
    :param action: string. The action that is logged, e.g. "filter", "drop columns", "click 'Show static HTML' button".
    """
    from bamboolib._authorization import auth
    from bamboolib import __version__ as version

    if not isinstance(view, str):
        # we assume, a class instance was passed as "self"

        try:
            kwargs = {**kwargs, **view.get_metainfos()}
        except:
            pass  # instance did not have .get_metainfos() method

        try:
            view = view.__class__.__name__
        except:
            view = "view.__class__.__name__ missing"

    kwargs["category"] = category
    kwargs["view"] = view
    kwargs["action"] = action
    # all < fine < rough < critical < none  # may be tuned via license?
    kwargs["log_level"] = level

    kwargs["local_datetime"] = str(datetime.datetime.now())

    # general information about the user and the bamboolib setup

    kwargs["email"] = auth.get_user_email()
    kwargs["license_key"] = auth.get_license_key()
    kwargs["license_type"] = auth.get_license_type()
    kwargs["license_logic"] = auth.get_license_logic()
    kwargs["version"] = version
    # fingerprint is calculcated inline because we dont want to expose the calculation
    user_path = Path.home()
    os_platform = sys.platform
    fingerprint = f"{os_platform};;;{user_path}"
    kwargs["machine_hash"] = hashlib.md5(fingerprint.encode()).hexdigest()[:10]

    maybe_message_segment(class_, kwargs)

    if env.DEBUG_LOGS:
        display({class_: kwargs})  # for debug


def log_databricks_funnel_event(description):
    from bamboolib._authorization import auth

    can_log = env.DBUTILS is not None
    if can_log and auth.is_databricks():
        env.DBUTILS.entry_point.getLogger().logDriverEvent({'eventType': 'bamboolib_funnel_v0', 'status': description, 'error': 'None'})
        # How to verify in Databricks: use the cluster's webterminal
        # cat /databricks/driver/logs/usage.json | grep bamboolib_funnel_v0


def log_view(*args, level="fine", **kwargs):
    """Log views."""
    log_base("view_v1", *args, level=level, **kwargs)


def log_action(*args, **kwargs):
    """Log a concrete action, e.g. transformation."""
    log_base("bam_action_v1", *args, **kwargs)


def log_setup(*args, **kwargs):
    """Log a setup event, e.g. license activation."""
    log_base("setup_action_v1", *args, **kwargs)


def log_error(*args, error=None, **kwargs):
    """Log an error."""
    if error is not None:
        kwargs["error_type"] = type(error).__name__
    log_base("error_v1", *args, **kwargs)


def log_jupyter_action(*args, **kwargs):
    """Log a jupyter action, e.g. displaying a dataframe."""
    log_base("jupyter_action_v1", *args, **kwargs)


def return_styled_df_as_widget(styled_df):
    """
    Return a styled pandas DataFrame as an ipywidgets.

    :param styled_df: styled pandas.DataFrame.

    :return: ipywidgets.HTML
    """
    # add CSS classes so that the normal Jupyter styles will be applied

    # class for Jupyter Notebook
    output_html = styled_df._repr_html_().replace(
        "<table", "<table class='rendered_html'"
    )

    # classes for Jupyter Lab including additional div because Lab has another hierarchy
    output_html = output_html.replace(
        "<table", "<div class='jp-RenderedHTMLCommon jp-RenderedHTML'><table"
    )
    output_html = output_html.replace("</table>", "</table></div>")
    return widgets.HTML(output_html)


def replace_code_placeholder(code, old_df_name=None, new_df_name=None):
    """
    Replace placeholders for the user's dataframe with the strings given in old_df_name and new_df_name.

    :param old_df_name: string or None. The name of the dataframe the user worked with so far.
    :param new_df_name: string or None. The new name the user gives her dataframe.

    :return: string. The code with the placeholders being replaced.
    """
    if old_df_name is not None:
        code = code.replace(DF_OLD, old_df_name)
    if new_df_name is not None:
        code = code.replace(DF_NEW, new_df_name)
    return code


def exec_code(
    code,
    symbols={},
    result_name=None,
    manipulate_symbols=False,
    return_result=True,
    add_result_to_user_symbols=True,
    masked_symbols={},
    add_pandas_and_numpy=True,
):
    """
    Internal function for executing code.

    ATTENTION:
    - If manipulate_symbols is True, we might add or change variables in the symbol environment.
    - If manipulate_symbols if False, we will copy the symbols in order to make sure that the original environment is only used for referencing variables but it will never get manipulated
    """
    user_symbols = symbols
    if manipulate_symbols:
        exec_symbols = symbols
    else:
        exec_symbols = symbols.copy()

    if add_pandas_and_numpy:
        exec_symbols["pd"] = pd
        exec_symbols["np"] = np

    for name in masked_symbols:
        exec_symbols[name] = masked_symbols[name]

    code = textwrap.dedent(code)
    # use this instead of `exec(code, {}, exec_symbols)` to fix an error in nested list comprehension
    exec(code, exec_symbols, exec_symbols)

    if result_name is not None:
        result = exec_symbols[result_name]
        if add_result_to_user_symbols:
            user_symbols[result_name] = result
        if return_result:
            return result


def string_to_code(string):
    """
    For a given string object, it returns the code string that would result in the same string object, when the code is executed/evaluated
    e.g. for "hello" it would return "'hello'" because eval("'hello'") == "hello"

    Currently, the code string is written with single quotes e.g. 'hello' for consistency
    because our default code export for string lists is handled by python's string interpolation and that uses single quotes e.g. "['a', 'b']"
    Later, we might change that to double quotes if we also write our own list_to_code function that handles string lists with double quotes
    """
    # escape backspaces
    # assumption: backspace is used as a literal and not as escape character
    # thus we need to escape it in order to prevent the interpretation as escape character by python
    string = string.replace("\\", "\\\\")
    # escape quote
    string = string.replace("'", "\\'")
    return f"'{string}'"


def VSpace(size: str) -> widgets.HTML:
    """Create an empty HTML div that adds vertical space to the frontend."""
    size_to_pixel_mapping = {
        "sm": "4",
        "md": "8",
        "lg": "12",
        "xl": "16",
        "xxl": "20",
        "xxxl": "24",
    }
    try:
        pixel = size_to_pixel_mapping[size]
    except KeyError:
        raise Exception(f"size must be one of {size_to_pixel_mapping.keys()}")

    return widgets.HTML(f"<div style='height:{pixel}px;'></div>")


def set_license(encrypted_string):
    """
    User exposed funtion to set the license themselves.

    We use that function e.g. when the user works in an offline sandbox and hence cannot activate the license
    from the UI (which would require internet). He then usually activates the license in an online environment,
    reads the license file under ~/.bamboolib/LICENSE, and activates bamboolib in the sandbox
    by calling:

    set_license(<content of ~/.bamboolib/LICENSE>), e.g.
    set_license("yhhekh...hfkljeh")
    """
    from bamboolib._authorization import auth

    auth.set_license(encrypted_string)


class AuthorizedPlugin:
    """
    This class should be inherited from when adding TransformationPlugins within the core library.
    Otherwise, the plugin counts towards the free limit of the user.

    Sample Usage:
    >>> class MyTransformation(AuthorizedPlugin, TransformationPlugin)
    """

    pass
