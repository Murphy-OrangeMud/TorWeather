class ExitSelectionError(Exception):

    """
    Represents an error during selection of exit relays.
    """

    pass


class PathSelectionError(Exception):

    """
    Represents an error during selection of a path for a circuit.
    """

    pass


class SOCKSv5Error(Exception):

    """
    Represents an error while negotiating SOCKSv5.
    """

    pass
