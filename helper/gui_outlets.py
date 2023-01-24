# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import time
import traceback
import ipywidgets as widgets

import bamboolib._environment as env
from bamboolib.helper.error import BamboolibError
from bamboolib.helper.utils import (
    CloseButton,
    BackButton,
    log_view,
    log_error,
    notification,
)
from bamboolib.widgets import TracebackOutput

# All windows and modals etc are considered outlets because
# those are elements that should be displayed and, thus,
# widgets can be shown to the user (without display) via adding
# them to an outlet


class Window(widgets.VBox):
    """
    The window base class.
    It serves as an outlet which can have a title and content.
    The window can be shown and hidden.
    The window supports adding a stack of multiple embeddables and the user can go back
    to previous embeddables.
    """

    def __init__(
        self,
        embeddable_content=widgets.VBox([]),
        on_show=lambda: None,
        on_hide=lambda: None,
        title="",
        show_header=True,
        css_classes=["bamboolib-window"],
    ):
        """
        :param embeddable_content: ipywidget object
        :param on_show: callable that is called when the window is shown
        :param on_hide: callable that is called when the window is hidden
        :param title: str for the window title
        :param show_header: bool, if the header of the window should be shown
        :param css_classes: list of str, css classes that should be added to the window
        """
        super().__init__()
        self.on_show = on_show
        self.on_hide = on_hide
        self.show_header = show_header

        self._registered_modals = []
        self._view_stack = []
        self._is_visible = False
        self._last_viewable = None

        for css_class in css_classes:
            self.add_class(css_class)

    def set_title(self, title):
        """
        Set the title for the current view in the window!

        :param title: str
        """
        self._maybe_add_default_view()
        self._view_stack[-1]["title"] = title
        self._render_view()

    def set_content(self, embeddable_content):
        """
        Set the content for the current view in the window!

        :param embeddable_content: a single ipywidgets object
        """
        self._maybe_add_default_view()
        self._view_stack[-1]["content"] = embeddable_content
        self._render_view()

    def _render_view(self):
        children = []

        if self.show_header:
            children.append(self._create_view_header())
        children.append(self._view_stack[-1]["content"])
        children += self._registered_modals

        self.children = children

    def _go_back(self):
        if len(self._view_stack) > 1:
            self._view_stack.pop()
            self._last_viewable = self._view_stack[-1].get("view", None)
            self._render_view()

    def _create_view_header(self):
        middle = widgets.HTML(f"<h4>{self._view_stack[-1]['title']}</h4>")

        close_button = CloseButton()
        close_button.on_click(
            lambda _: log_view("views", self._last_viewable, "click close button")
        )
        close_button.on_click(lambda button: self.hide())
        start = widgets.HTML("")
        if len(self._view_stack) > 1:
            start = BackButton()
            start.on_click(
                lambda _: log_view("views", self._last_viewable, "click back button")
            )
            start.on_click(lambda button: self._go_back())
        end = close_button

        header = widgets.Box([start, middle, end])
        header.add_class("bamboolib-window-header")
        return header

    def show(self):
        """
        NEEDS TO BE IMPLEMENTED BY A CHILD

        Command that the window should be shown.
        Children need to implement the method in order to add or remove the
        appropriate CSS classes. Afterwards, they should call `super().show()`
        e.g. see FullParentModal
        """
        self.add_class("bamboolib-active-window")
        self._is_visible = True
        self.on_show()

    def hide(self):
        """
        NEEDS TO BE IMPLEMENTED BY A CHILD

        Command that the window should be hidden.
        Children need to implement the method in order to add or remove the
        appropriate CSS classes. Afterwards, they should call `super().hide()`
        e.g. see FullParentModal
        """
        self.remove_class("bamboolib-active-window")
        self._is_visible = False
        self._reset_view_stack_history()
        self.on_hide()

    def _reset_view_stack_history(self):
        self._view_stack = []

    def register_modal(self, modal):
        """
        :param modal: Modal object that should be added to the window
        """
        self._registered_modals.append(modal)

    def _maybe_add_default_view(self):
        # this ensures that there is a view on the _view_stack
        if len(self._view_stack) == 0:
            self._add_default_view()

    def _add_default_view(self):
        self._view_stack.append({"view": None, "title": "", "content": widgets.VBox()})

    def show_view(self, view):
        """
        Show a single view in the Window. This removes all other views from the view stack.
        If you want to keep the history of previous views, use `push_view`

        :param view: embeddable view that should be shown
        """
        self._reset_view_stack_history()

        self._add_default_view()
        self._view_stack[-1]["view"] = view
        self._last_viewable = view

    def push_view(self, view):
        """
        Show a view in the Window by pushing it onto the view stack.
        This means that the user can go back to show older views.
        If you don't want to keep the history of previous views, use `show_view`

        :param view: embeddable view that should be shown
        """
        self._view_stack.append({"view": view, "title": "", "content": widgets.VBox()})
        self._last_viewable = view

    def does_display(self, viewable):
        """
        :param viewable: embeddable viewable that might be displayed
        :return bool, if the viewable is currently shown in the window. Attention: even if the viewable is shown as the latest view on the view stack, it might still be obscured by a modal.
        """
        if len(self._view_stack) == 0:
            return False
        else:
            return self._view_stack[-1]["view"] == viewable

    def is_visible(self):
        """
        :return bool, if the window is visible
        """
        return self._is_visible


class WindowToBeOverriden(Window):
    """
    This class is just a placeholder for another window.
    It serves as a reminder in the code that the value needs to be overriden by a real window
    that is actually displayed somewhere.
    The WindowToBeOverriden is never displayed somewhere, so the user cannot see it.
    However, some viewables need a valid outlet before they receive their actual window
    """

    pass


class LoaderModal(widgets.VBox):
    """
    A modal that shows a loading sign
    """

    def __init__(self):
        super().__init__()
        self.children = [widgets.HTML("Loading ...")]
        self.add_class("bamboolib-loader-modal")

    def show(self):
        """Show the modal"""
        self.add_class("bamboolib-active-modal")
        self.add_class("bamboolib-active-window")

    def hide(self):
        """Hide the modal"""
        self.remove_class("bamboolib-active-modal")
        self.remove_class("bamboolib-active-window")


class ErrorModal(Window):
    """
    A modal that is meant to show errors
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_class("bamboolib-full-modal")

    def show(self):
        """Show the modal"""
        self.add_class("bamboolib-active-modal")
        super().show()  # calls method from window e.g. for callbacks

    def hide(self):
        """Hide the modal"""
        self.remove_class("bamboolib-active-modal")
        super().hide()  # calls method from window e.g. for callbacks


class WindowWithLoaderAndErrorModal(Window):
    """
    A window base class that additionally provides a loader and error modal
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.__loader_modal__ = LoaderModal()
        self.register_modal(self.__loader_modal__)

        self.__error_modal__ = ErrorModal(
            title="There is a tiny error", on_hide=lambda: self.hide_error_modal()
        )
        self.register_modal(self.__error_modal__)

    def show_loader(self):
        """Show the loader modal"""
        self.__loader_modal__.show()

    def hide_loader(self):
        """Hide the loader modal"""
        self.__loader_modal__.hide()

    def show_error_modal(self, embeddable):
        """
        Show an embeddable within the error modal
        :param embeddable: that contains the error
        """
        self.add_class("bamboolib-min-height-for-error-modal")
        self.__error_modal__.set_content(embeddable)
        self.__error_modal__.show()
        time.sleep(1)
        self.__loader_modal__.hide()

    def hide_error_modal(self):
        """Hide the error modal"""
        self.remove_class("bamboolib-min-height-for-error-modal")


# read more about decorated instance methods here:
# https://stackoverflow.com/questions/14745223/python-member-function-decorators-use-instance-as-a-parameter
def show_loader_and_maybe_error_modal(execute_function):
    """
    This method should be used for decorating `execute` functions of Viewable objects
    that have a WindowWithLoaderAndErrorModal as `outlet`

    :param execute_function: the execute function of the object
    """

    def create_notification_from_bambooliberror(exception):
        """
        Create a notification object based on an bamboolib error
        """
        return notification(str(exception), type="error")

    def create_stacktrace(self, exception):
        """
        Create the stacktrace output for a given exception
        """
        output = TracebackOutput()
        output.add_class("bamboolib-output-wrap-text")
        output.content += f"{exception.__class__.__name__}: {exception}"
        output.content += "\n\n\n\n"

        try:
            code = self.get_final_code()
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

    def safe_execution(self, *args, **kwargs):
        """
        Execute the given `execute_function` with its args and kwargs, catch all errors
        and show them in the error modal.
        Also, a loader is shown as long as the function is executing.
        """
        try:
            self.outlet.show_loader()
            hide_outlet = execute_function(self, *args, **kwargs)
            self.outlet.hide_loader()
            if hide_outlet:
                self.outlet.hide()
        except Exception as exception:
            log_error("catched error", self, "show error modal", error=exception)
            if env.SHOW_RAW_EXCEPTIONS:
                output = create_stacktrace(self, exception)
            else:
                output = self.get_exception_message(exception)
                if output:
                    pass  # show the output from the custom exception message
                elif isinstance(exception, BamboolibError):
                    output = create_notification_from_bambooliberror(exception)
                else:
                    output = create_stacktrace(self, exception)
            self.outlet.show_error_modal(output)

    def raise_error_if_requirements_are_not_met(self):
        """Validate if the self object supports the decorator"""
        if not hasattr(self, "outlet"):
            raise Exception(f"{self} does not have an outlet")

        if not (
            hasattr(self.outlet, "show_loader")
            and hasattr(self.outlet, "hide_loader")
            and hasattr(self.outlet, "show_error_modal")
        ):
            raise Exception(
                f"The outlet of {self} does not support showing loaders and error_modals"
            )

        if not hasattr(self, "get_exception_message"):
            raise Exception(
                f"The object does not have a 'get_exception_message' method"
            )

    # async exection enables another feature: the user can abort transformations
    # we implement this via just not accepting the result of the execution any more once it finishes
    # similar to the AutoComplete logic
    def async_execution(self, *args, **kwargs):
        """
        Execute the `execute_function` asynchronously within a `safe_execution`
        that catches all exceptions and shows them in the error modal.
        Also, a loader is shown as long as the `execute_function` is executed.
        """
        raise_error_if_requirements_are_not_met(self)

        from threading import Timer

        delay_in_sec = 0.01
        t = Timer(delay_in_sec, safe_execution, [self, *args], kwargs)
        t.start()

    return async_execution


class FullParentModal(WindowWithLoaderAndErrorModal):
    """
    A modal that spans the full size of its parent window
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_class("bamboolib-full-modal")

    def show(self):
        self.add_class("bamboolib-active-modal")
        super().show()

    def hide(self):
        self.remove_class("bamboolib-active-modal")
        super().hide()


class SideWindow(WindowWithLoaderAndErrorModal):
    """
    A modal that spans only the right side of its parent window
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_class("bamboolib-side-window")

    def show(self):
        self.add_class("bamboolib-active-side-window")
        super().show()

    def hide(self):
        self.remove_class("bamboolib-active-side-window")
        super().hide()


class TabWindow(WindowWithLoaderAndErrorModal):
    """
    The window that is used in combination with a TabSection.
    It follows the API of WindowWithLoaderAndErrorModal and provides additional methods like
    `df_did_change`, `tab_got_selected`.

    Attention: In contrast to a normal Window, TabWindow does not get displayed (see details in TabSection).
    Therefore, setting CSS classes on this class won't have an effect.
    The TabWindow itself also has an outlet and classes etc must be set on the outlet.
    """

    # To some extent, the TabWindow behaves more like a Viewable. Maybe refactor this in the future?
    def __init__(self, tab_section, tab_viewable, tab, outlet):
        super().__init__()
        self.tab_section = tab_section
        self.tab_viewable = tab_viewable
        self.tab = tab
        self.outlet = outlet

    def set_title(self, title):
        self.tab.title = title

    def set_content(self, embeddable_content):
        self.outlet.children = [embeddable_content] + self._registered_modals

    def df_did_change(self):
        """
        Method that should be called when the Dataframe did change.
        """
        self.tab_viewable.df_did_change()

    def tab_got_selected(self):
        """
        Method that should be called when the tab got selected
        """
        self.tab_viewable.tab_got_selected()

    def show(self):
        """
        Show the current TabWindow in the tabs. This is like activating an existing tab
        """
        self.tab_section.activate_tab(self)

    def hide(self):
        """
        Hide is implemented as removing the tab of the TabWindow
        """
        self.tab_section.remove_tab(self)

    def show_view(self, view):
        # The TabWindow just registers itself but it does not add a separate view.
        # This seems like the TabWindow is the Viewable itself
        self.tab_section.register_window(self)

    def push_view(self, view):
        # there is currently no way for going back and thus it is the same as show_view
        # usually, push_view allows the user to pop the view via the UI
        self.show_view(view)

    def does_display(self, viewable):
        return True

    def register_modal(self, modal):
        self._registered_modals.append(modal)

    def is_visible(self):
        # might be interpreted like `is active tab`?
        raise NotImplementedError

    def show_error_modal(self, embeddable):
        self.outlet.add_class("bamboolib-min-height-for-error-modal")
        super().show_error_modal(embeddable)

    def hide_error_modal(self):
        self.outlet.remove_class("bamboolib-min-height-for-error-modal")
        super().hide_error_modal()
