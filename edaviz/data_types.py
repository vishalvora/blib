# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


def is_dtype_timedelta(series, **kwargs):
    return series.dtype.kind == "m"


def is_binary(series, **kwargs):
    return series.value_counts().count() == 2


def is_numeric(series, **kwargs):
    is_integer = series.dtype.kind == "i"
    is_float = series.dtype.kind == "f"
    return is_integer or is_float


def is_object(series, **kwargs):
    return series.dtype.kind == "O"
