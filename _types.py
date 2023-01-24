# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


# Traitlets checks whether Widget modules are functions. For that, it uses
# inspect.isfunction(), which doesn't allow cython functions out of the box.
# Thus, we need to extend inspect.isfunction() to also accept cython functions.
# For that, we cythonize this file here at distribution and get the type of
# the cythonized function _f at runtime.


def _f():
    pass


CyFunctionType = type(_f)
