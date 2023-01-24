import re
import ipywidgets as widgets
from bamboolib.plugins import TransformationPlugin, DF_OLD, Text, BamboolibError
from bamboolib.helper import notification

FORBIDDEN_CHARACTERS = """?! "'-%$&\<\>\\/§`*+#;:.^"""
OVERWRITE_TABLE_LABEL = "Overwrite table if it already exists"
OVERWRITE_SCHEMA_LABEL = "Overwrite existing table schema"


class DatabricksWriteToDatabaseTable(TransformationPlugin):

    name = "Databricks: Write to database table"
    description = "Export your table to a Databricks database table"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.database = Text(
            description="Database - leave empty for default database",
            placeholder="Database",
            value="",
            focus_after_init=True,
            width="xl",
            execute=self,
        )
        self.table = Text(description="Table", value="", width="xl", execute=self)
        self.overwrite_existing_table = widgets.Checkbox(
            value=False, description=OVERWRITE_TABLE_LABEL
        )
        self.overwrite_existing_table.add_class("bamboolib-checkbox")

        self.overwrite_schema = widgets.Checkbox(
            value=False, description=OVERWRITE_SCHEMA_LABEL
        )
        self.overwrite_schema.add_class("bamboolib-checkbox")

    # FYI: this logic is very similar to DatabricksDatabaseTableLoader
    def is_valid_transformation(self):
        if self.table.value == "":
            raise BamboolibError(
                "The table name is empty. Please enter the name of the table"
            )

        for input in [self.database, self.table]:
            for character in list(FORBIDDEN_CHARACTERS):
                if character in input.value:
                    if character == " ":
                        character = "whitespace"

                    input_description = input.description
                    if input is self.database:
                        input_description = "database"
                    else:  # input is self.table
                        input_description = "table"

                    raise BamboolibError(
                        f"""
                    The {input_description} name contains a <b>{character}</b> character. This is not allowed.<br>
                    Please remove the character and make sure that neither the Database nor the Table name contain any of the following characters:<br>
                    <b>{FORBIDDEN_CHARACTERS}</b>
                    """
                    )
        return True

    def get_exception_message(self, exception):
        if "'spark' is not defined" in str(exception):
            return notification(
                f"It seems like you are not within Databricks. This feature only works within the Databricks platform.",
                type="error",
            )

        if all(s in str(exception) for s in ["Database", "not found"]):
            return notification(
                """It seems like the database does not exist yet.<br>
                Please write to a database that already exists or create a new database.""",
                type="error",
            )

        if re.compile("Table(.+)already exists").match(str(exception)):
            return notification(
                f"The table already exists. If you want to overwrite the existing table, please select the <b>{OVERWRITE_TABLE_LABEL}</b> option.",
                type="error",
            )

        if all(
            s in str(exception)
            for s in ["Found invalid character", "in the column names"]
        ):
            return notification(
                """There are invalid characters e.g. " ,;{}()\\n\\t=" in the column names.<br>
                Please remove the invalid characters via renaming the column names.<br>
                <br>
                If you are interested in the Private Preview of arbitrary column name support in Delta tables please contact Databricks.""",
                type="error",
            )

        if "A schema mismatch detected when writing to the Delta table" in str(
            exception
        ):
            return notification(
                f"""The existing table has a different schema than your current table.<br>
                If you want to overwrite the schema, please select the <b>{OVERWRITE_SCHEMA_LABEL}</b> option.<br>
                <br>
                <br>
                <b>You can compare the schemas as part of the following error message:</b>
                {str(exception)}""",
                type="error",
            )
        return None

    def render(self):
        self.set_title("Databricks: Write to database table")
        self.set_content(
            self.database,
            self.table,
            self.spacer,
            self.overwrite_existing_table,
            self.overwrite_schema,
        )

    def get_code(self):
        overwrite = '.mode("overwrite")' if self.overwrite_existing_table.value else ""
        merge_schema = (
            '.option("mergeSchema", "true")' if self.overwrite_schema.value else ""
        )
        database_prefix = f"{self.database.value}." if self.database.value != "" else ""
        return f"""spark.createDataFrame({DF_OLD}).write{overwrite}{merge_schema}.saveAsTable("{database_prefix}{self.table.value}")"""
