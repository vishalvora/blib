# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

"""Global environment variables that we only want to set internally."""

LICENSES_SERVER = "https://v1.licenses.bamboolib.com"
# LICENSES_SERVER = "http://localhost:3000"


# https://stackoverflow.com/questions/1977362/how-to-create-module-wide-variables-in-python
import sys

# 'this' is a reference to the module instance itself
this = sys.modules[__name__]
# we use 'this' in order to assign attributes to the module itself

# False is default in production
this.TESTING_MODE = False
this.DEACTIVATE_ASYNC_CALLS = False
this.SHOW_RAW_EXCEPTIONS = False

this.DEBUG_CODE = False

this.LOG_USER_BEHAVIOR = False
this.DEBUG_LOGS = False

this.DBUTILS = None
try:
    from __main__ import dbutils  # available within Databricks
    this.DBUTILS = dbutils
except:
    pass
