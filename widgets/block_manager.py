# Copyright (c) Databricks Inc.
# Distributed under the terms of the DB License (see https://databricks.com/db-license-source
# for more information).

import ipywidgets as widgets


class BlockManager(widgets.VBox):
    """
    A BlockManager is used to display and manage multiple Blocks.
    It is an alternative to using a widgets.VBox as widget outlet for plain ipywidgets.
    It provides a more convenient API than adding and removing widgets from a widgets.VBox.
    """

    def __init__(self, *args, **kwargs):
        super().__init__()
        self._blocks = []

    def add_block(self, block, index=None, after=None, before=None):
        """
        Add a block at a certain index or after/before another Block.

        :param block: The block that should be added
        :param index: the index as int
        :param after: another Block
        :param before: another Block
        """
        if after is not None:
            index = self._blocks.index(after) + 1
        if before is not None:
            index = self._blocks.index(before)
        if index is None:  # add to the bottom
            index = len(self._blocks)
        self._blocks.insert(index, block)
        block.render()
        self.render()

    def get_all_blocks(self, tags=None):
        """
        Returns all blocks - optionally filtered by a/certain tag/s

        :param tags: str or list of str
        :return: a list of Blocks
        """
        if tags is not None:
            if isinstance(tags, str):
                tags = [tags]
            return [block for block in self._blocks if block.has_tags(tags)]
        else:
            return self._blocks

    def get_block(self, tags):
        """
        Return the (first) Block that has a/certain tag/s

        :param tags: str or list of str
        :return: a Block
        """
        results = self.get_all_blocks(tags=tags)
        if len(results) != 1:
            raise ValueError(f"There is no block with the tags {tags}")
        else:
            return results[0]

    def delete_block(self, block, render=True):
        """
        Delete a given Block - and maybe skip rendering

        :param block: the Block that should be deleted
        :param render: boolean if the BlockManager should render itself afterwards or not
        """
        try:
            self._blocks.remove(block)
            if render:
                self.render()
        except:
            # when the user is working too fast, he might trigger this multiple times
            # this behavior might lead to an ValueError if the item does not exist any more
            return

    def replace_block(self, old_block, new_block):
        """
        Replace an old Block with a new Block

        :param old_block: the Block that gets replaced
        :param new_block: the Block that is replacing the old Block
        """
        old_index = self._blocks.index(old_block)
        self.delete_block(old_block, render=False)
        self._blocks.insert(old_index, new_block)
        self.render()

    def render(self):
        """
        Render the user interface of the BlockManager to show the current state.
        This only has an effect, if the BlockManager is already displayed in Jupyter.
        """
        self.children = self._blocks


class Block(widgets.VBox):
    """
    A Block is a widget that is meant to be used in combination with a BlockManager.
    In addition to a normal widget, a Block can have zero, one or multiple tags and it exposes a `set_content` method.
    A class that inherits from Block needs to implement the `render` method.
    """

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.tags = []

    def render(self):
        raise NotImplementedError

    def set_content(self, *content):
        """
        Set one or multiple widgets as content for the Block.

        Example:
        >>> my_block.set_content(widget1)
        >>> my_block.set_content(widget1, widget2, widget3)

        :param content: an unpacked list of widgets
        """
        self.children = content

    def add_tag(self, tag):
        """
        Add a string tag to the block

        :param tag: str
        """
        self.tags.append(tag)

    def get_tags(self):
        """
        Get all the tags of the Block

        :return: a list of str
        """
        return self.tags

    def has_tags(self, tags):
        """
        Answers the question: Does the Block has all the mentioned tags?

        :param tags: list of str
        :return: boolean if the Block has all the tags
        """
        return all([tag in self.get_tags() for tag in tags])
