from bamboolib.plugins import TransformationPlugin, DF_OLD, DF_NEW, BamboolibError
from bamboolib.helper import string_to_code
from bamboolib.widgets import Singleselect

class ExplodeNestedColumns(TransformationPlugin):

    name = "Explode nested column"
    description = "Given a column that contains a list as value: creates rows for every list element"
    # Transform a single row into many rows for every nested list item

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.column = Singleselect(
            options=list(self.df_manager.get_current_df().columns),
            placeholder="Choose column",
            set_soft_value=False,
            width="xl",
            focus_after_init=True,
        )

    def render(self):
        self.set_title("Explode nested column")
        self.set_content(self.column, self.rename_df_group)

    def is_valid_transformation(self):
        if self.column.value is None:
            raise BamboolibError("It seems like you did not select a column")
        return True

    def get_description(self):
        return "Explode nested column"

    def get_code(self):
        column_name = string_to_code(self.column.value)
        return f"{DF_NEW} = {DF_OLD}.explode({column_name}, ignore_index=True)"
