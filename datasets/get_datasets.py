# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

"""
Exposes a bunch of toy data sets for the user to play with and for testing.
"""

import pandas as pd

from bamboolib._path import BAMBOOLIB_LIBRARY_ROOT_PATH

# the name 'titanic_csv' is also exported to the user, thus it is not CAPITAL like a constant
titanic_csv = BAMBOOLIB_LIBRARY_ROOT_PATH / "datasets" / "titanic.csv"
# the name 'sales_csv' is also exported to the user, thus it is not CAPITAL like a constant
sales_csv = BAMBOOLIB_LIBRARY_ROOT_PATH / "datasets" / "sales.csv"


def get_sales_df(**kwargs):
    return pd.read_csv(sales_csv)


def get_titanic_df(**kwargs):
    return pd.read_csv(titanic_csv)


def get_ports_df(**kwargs):
    return pd.DataFrame(
        data={
            "Embarked": ["S", "C", "Q"],
            "PortName": ["Southampton", "Cherbourg", "Queenstown"],
        }
    )


# We use this function to show that bamboolib also works on 1 mio rows datasets
def get_1mio_rows_titanic_df(**kwargs):
    df = get_titanic_df()
    df = pd.concat([df for i in range(0, 1211)])  # expand df to 1 mio rows
    df = df.reset_index().drop(columns=["index"])
    return df
