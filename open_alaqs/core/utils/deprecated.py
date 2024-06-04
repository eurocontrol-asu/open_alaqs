import warnings
from typing import Callable, Optional


def deprecated(message: Optional[str]) -> Callable:
    """Mark a function as deprecated and optionally pass a message.

    Args:
        message (str, optional): Optional message to the deprecation warning
    """

    def deprecated_decorator(func):
        def deprecated_func(*args, **kwargs):
            warnings.warn(
                "{} is a deprecated function. {}".format(func.__name__, message),
                category=DeprecationWarning,
                stacklevel=2,
            )
            warnings.simplefilter("default", DeprecationWarning)
            return func(*args, **kwargs)

        return deprecated_func

    return deprecated_decorator
