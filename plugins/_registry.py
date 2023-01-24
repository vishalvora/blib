# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).


# each plugin type has its own list with the full names of the plugins, e.g.:
# {
#     "TransformationPlugin": ["SelectColumnsTransformation", ...],
#     ...
# }
_all_plugin_types = {}

# a dict for all plugins with the structure plugin_name:plugin_class, e.g.:
# {
#     "SelectColumnsTransformation": SelectColumnsTransformation,
#     ...
# }
_all_plugins = {}


# Info/Extension for later:
# instead of passing the plugin_base_class, the user might later also be allowed
# to set and get plugins via a string if we want this
# this would add some decoupling which has pros and cons
# currently, we are turning the plugin_base_class into a unique string
# for its plugin_type based on the module and class name


def get_plugins(plugin_base_class):
    """
    Get all plugins for a given plugin base class
    """
    plugin_type = _get_full_class_name(plugin_base_class)
    plugins_list = _all_plugin_types.get(plugin_type, [])
    return [_all_plugins[plugin_name] for plugin_name in plugins_list]


def _preprocess_plugin_class(plugin_class):
    """
    Preprocess steps to make sure that the plugin_class is a valid plugin, e.g.
    - make sure that the plugin_class has a `name` that is not None
    """
    if plugin_class.name is None:
        plugin_class.name = plugin_class.__name__


def _get_plugin_list(plugin_base_class):
    plugin_type = _get_full_class_name(plugin_base_class)
    if plugin_type in _all_plugin_types:
        # use existing plugins_list for the plugin_type
        plugins_list = _all_plugin_types[plugin_type]
    else:
        # create and add new plugins_list for the plugin_type
        plugins_list = []
        _all_plugin_types[plugin_type] = plugins_list
    return plugins_list


def register(plugin_base_class, plugin_class, index=None, before=None, after=None):
    """
    Register plugin e.g. `register(TransformationPlugin, MyTransformation)`

    Optionally, you can provide information where the plugin should be inserted.
    Using ONE kwarg of `index`, `before`, or `after`

    :param plugin_base_class: class e.g. TransformationPlugin
    :param plugin_class: class e.g. MyTransformation
    :param index: int, optional. Insert the plugin class at this index position (starting at 0) e.g. `register(TransformationPlugin, MyTransformation, index=0)`
    :param before: class, optional. Insert the plugin class BEFORE another plugin class e.g. `register(TransformationPlugin, MyTransformation, before=AnotherTransformation)`
    :param after: class, optional. Insert the plugin class AFTER another plugin class e.g. `register(TransformationPlugin, MyTransformation, after=AnotherTransformation)`
    """

    _preprocess_plugin_class(plugin_class)

    plugins_list = _get_plugin_list(plugin_base_class)
    plugin_name = _get_full_class_name(plugin_class)

    if plugin_name in _all_plugins:
        pass  # No further auth check needed because the plugin was already added once

        # Remove existing plugin_name from list because it will be added again below
        plugins_list.remove(plugin_name)
    else:
        # Check if user is allowed (authorized) to register the plugin
        # This code is inline so that it is harder to override for an attacker
        from IPython.display import display
        from bamboolib._authorization import auth
        from bamboolib.helper import AuthorizedPlugin, notification

        def is_authorized(plugin_class):
            if issubclass(plugin_class, AuthorizedPlugin):
                return True

            if auth.has_unlimited_plugins():
                return True

            return False

        if is_authorized(plugin_class):
            pass
        else:
            display(
                notification(
                    f"Could not register plugin <b>{plugin_class.__name__}</b> because this is a Pro feature. If you want to use plugins, please <a href='https://bamboolib.com/pricing/' target='_blank'>get a Pro license</a>",
                    type="error",
                )
            )
            return  # abort registration process

    # add the plugin_name at the correct position in the list of items for the plugin_type
    if index is not None:
        plugins_list.insert(index, plugin_name)
    elif before is not None:
        other_plugin_name = _get_full_class_name(before)
        other_index = plugins_list.index(other_plugin_name)
        plugins_list.insert(other_index, plugin_name)
    elif after is not None:
        other_plugin_name = _get_full_class_name(after)
        other_index = plugins_list.index(other_plugin_name)
        plugins_list.insert(other_index + 1, plugin_name)
    else:
        plugins_list.append(plugin_name)

    # finally, actually add the plugin_class
    _all_plugins[plugin_name] = plugin_class


def _get_full_class_name(cls):
    """
    Turn a class into a unique string based on its module and name.
    """
    return f"{cls.__module__}.{cls.__name__}"
