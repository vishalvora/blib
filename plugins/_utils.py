# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import bamboolib.plugins._registry as PluginRegistry


def create_plugin_base_class(cls):  # cls is e.g. TransformationPlugin
    """
    Class decorator for creating a plugin base class.
    All classes that inherit from a plugin base class will be registered as plugins for the base class.

    Example:
    >>> @create_plugin_base_class
    >>> class TransformationPlugin(Transformation):
    >>>     pass
    TransformationPlugin is now a base class and can be used via inheritance, like so:
    >>> class SelectColumns(TransformationPlugin):
    >>>     pass
    SelectColumns is now registered as a plugin of TransformationPlugin:
    >>> TransformationPlugin.get_plugins()  # [SelectColumns]
    """

    def __init_subclass__(subclass):  # subclass is e.g. SelectColumnsTransformation
        super(cls, subclass).__init_subclass__()

        # e.g. PluginRegistry.register(TransformationPlugin, SelectColumns)
        PluginRegistry.register(cls, subclass)

    # Attention: we need to turn __init_subclass__ into a class method
    # so that it receives the subclass argument.
    # Otherwise, no argument will be passed
    cls.__init_subclass__ = classmethod(__init_subclass__)

    def get_plugins():
        return PluginRegistry.get_plugins(cls)

    cls.get_plugins = get_plugins
    return cls


# INFO: (in case that we will have the idea again later on)
# We cannot refactor the decorator as Mixin (with __init_subclass__)
# because the mixin cannot know the name of its own original class name
# during the __init_subclass__ call
# It only knows that its own name is one of subclass.__bases__ but not which one
