# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

# REMOVED BECAUSE WE DONT WANT TO HAVE OUTPUT WIDGETS DEPENDENCIES

import ipywidgets as widgets

from bamboolib.helper import Viewable


class DisplayOutput(Viewable):
    """
    A view to display the output/representation of an object

    :param object_: the object that should be displayed
    :param notification: a widget with an optional notification
    """

    def __init__(self, object_, notification=widgets.HTML(""), **kwargs):
        super().__init__(**kwargs)
        self.output = widgets.Output()
        self.output.append_display_data(object_)
        self.notification = notification

    def render(self):
        self.set_title("Display output")
        self.set_content(self.notification, self.output)
