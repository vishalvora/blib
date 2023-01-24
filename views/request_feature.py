# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets

from bamboolib.helper import TabViewable, notification


# A TabViewable is used on purpose because we want to open the view only on the side.
# We could also use a ViewPlugin but those are usually EXPECTED to open in full width.
class RequestFeature(TabViewable):
    """
    A view to request a feature
    """

    def render(self):
        self.set_title("Not found what you're looking for?")

        self.set_content(
            notification(
                """
                Let us know so that we can build it for you!<br>
                <br>

                Send us an email to <b><a href="mailto:bamboolib-feedback@databricks.com?subject=Did not find what I was looking for&body=I used bamboolib and searched for [PLEASE FILL IN] because I wanted to do [PLEASE FILL IN].%0D%0A %0D%0AFor example: I searched for 'drop NA' because I wanted to 'delete missing values'%0D%0A %0D%0A %0D%0A">bamboolib-feedback@databricks.com</a></b>
                """
            )
        )
