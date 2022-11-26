import collections
import functools
import types

from typing import TypeVar, Callable


# from jaraco.functools 3.5.2
def save_method_args(method):
    args_and_kwargs = collections.namedtuple('args_and_kwargs', 'args kwargs')

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        attr_name = '_saved_' + method.__name__
        attr = args_and_kwargs(args, kwargs)
        setattr(self, attr_name, attr)
        return method(self, *args, **kwargs)

    return wrapper


# from jaraco.functools 3.5.2
CallableT = TypeVar("CallableT", bound=Callable[..., object])


def method_cache(
    method: CallableT,
    cache_wrapper: Callable[
        [CallableT], CallableT
    ] = functools.lru_cache(),  # type: ignore[assignment]
) -> CallableT:
    def wrapper(self: object, *args: object, **kwargs: object) -> object:
        # it's the first call, replace the method with a cached, bound method
        bound_method: CallableT = types.MethodType(  # type: ignore[assignment]
            method, self
        )
        cached_method = cache_wrapper(bound_method)
        setattr(self, method.__name__, cached_method)
        return cached_method(*args, **kwargs)

    # Support cache clear even before cache has been created.
    wrapper.cache_clear = lambda: None  # type: ignore[attr-defined]

    return (  # type: ignore[return-value]
        _special_method_cache(method, cache_wrapper) or wrapper
    )


def _special_method_cache(method, cache_wrapper):
    """
    Because Python treats special methods differently, it's not
    possible to use instance attributes to implement the cached
    methods.

    Instead, install the wrapper method under a different name
    and return a simple proxy to that wrapper.

    https://github.com/jaraco/jaraco.functools/issues/5
    """
    name = method.__name__
    special_names = '__getattr__', '__getitem__'
    if name not in special_names:
        return

    wrapper_name = '__cached' + name

    def proxy(self, *args, **kwargs):
        if wrapper_name not in vars(self):
            bound = types.MethodType(method, self)
            cache = cache_wrapper(bound)
            setattr(self, wrapper_name, cache)
        else:
            cache = getattr(self, wrapper_name)
        return cache(*args, **kwargs)

    return proxy
