from collections import OrderedDict


class SizeLimitedDict(OrderedDict):
    def __init__(self, *args, **kwargs):
        self._limit = kwargs["size"] if "size" in kwargs else None
        OrderedDict.__init__(self, *args, **kwargs)

    def __setitem__(self, key, value):
        OrderedDict.__setitem__(self, key, value)
        self.limit()

    def limit(self):
        if self._limit is not None:
            while len(self) > self._limit:
                self.popitem(last=False)
