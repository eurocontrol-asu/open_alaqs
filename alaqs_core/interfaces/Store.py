from collections import OrderedDict

from open_alaqs.alaqs_core.alaqslogging import get_logger
from open_alaqs.alaqs_core.tools import conversion

logger = get_logger(__name__)


class Store:
    """
        Abstract container for objects of any type
    """
    def __init__(self, initValues=None, defaultValues=None, ordered=False):
        if initValues is None:
            initValues = {}
        if defaultValues is None:
            defaultValues = {}

        self._objects = OrderedDict() if ordered else {}
        self._default = defaultValues if defaultValues else {}

        self.initDefaultValues()
        self.initValues(initValues)

    def initDefaultValues(self):
        self._objects.update(self._default)

    def initValues(self, val):
        if isinstance(val, Store):
            val = val.getObjects()
        self._objects.update(val)

    def hasKey(self, key):
        return (key in self._objects)

    def isinKey(self, str_):
        if len([key for key in list(self._objects.keys()) if str_ in key])>0:
            return True
        else:
            return False

    def addObject(self, key, val):
        if not self.hasKey(key):
            self.setObject(key, val)
        else:
            self.setObject(key, self.getObject(key) + val)

    def getObject(self, key):
        return self._objects[key] if self.hasKey(key) else None

    def getObjects(self):
        return self._objects

    def setObject(self, key, obj):
        self._objects[key] = obj

    def removeObject(self, key):
        return self._objects.pop(key)

    def __add__(self, other):
        """ add self to  other, e.g. Store() + Store() """
        if not isinstance(other, type(self)):
            raise TypeError(f"cannot add '{str(type(other))}'"
                            f" to '{str(type(self))}' objects")
        values = {}
        for key_ in list(self.getObjects().keys()):
            values[key_] = self.getObject(key_)
            if other.hasKey(key_):
                if conversion.convertToFloat(values[key_]) is None or\
                        conversion.convertToFloat(other.getObject(key_)) is None:
                    values[key_] = None
                else:
                    values[key_] += other.getObject(key_)
        for key__ in list(other.getObjects().keys()):
            if key__ not in values:
                values[key__] = other.getObject(key__)
        return type(self)(values)

    def __iadd__(self, other):
        ''' inplace add self to other, e.g. Store() + 2. '''
        if not isinstance(other, type(self)):
            raise TypeError("cannot add '%s' to '%s' objects" % (type(other), type(self)))
        for key_ in list(self.getObjects().keys()):
            if other.hasKey(key_):
                if conversion.convertToFloat(self.getObject(key_)) is None or conversion.convertToFloat(other.getObject(key_)) is None:
                    self.setObject(key_, None)
                else:
                    self.setObject(key_, self.getObject(key_)+other.getObject(key_))

        for key__ in list(other.getObjects().keys()):
            if not self.hasKey(key__):
                self.setObject(key__, other.getObject(key__))
        return self

    def __radd__(self, other):
        ''' reverse add self to other, e.g. Store() * 2. '''
        #python's "sum" method starts with a 0
        if other == 0:
            return type(self)(self)
        return type(self)(self + other)

    def __sub__(self, other):
        return  type(self)(self + (-1.*other))

    def __rsub__(self, other):
        return type(self)(self + (-1.*other))

    def __isub__(self, other):
        self.__iadd__(-1.*other)

    def __mul__(self, other):
        ''' multiply self with other, e.g. Store() * 2. '''
        if not conversion.convertToFloat(other) is None:#check if 'other' is numerical value, i.e. can be converted to a float
            values = {}
            for key in list(self.getObjects().keys()):
                if conversion.convertToFloat(self.getObject(key)) is None:
                    values[key] = None
                else:
                    values[key] = self.getObject(key)*other

            return type(self)(values)
        elif isinstance(other, type(self)): #multiply 'Store' objects with 'Store' objects
            values = {}
            for key_ in list(self.getObjects().keys()):
                values[key_] = self.getObject(key_)
                if other.hasKey(key_):
                    if conversion.convertToFloat(self.getObject(key_)) is None or conversion.convertToFloat(other.getObject(key_)) is None:
                        values[key_] = None
                    else:
                        values[key_] *= other.getObject(key_)
            return type(self)(values)
        else:
            raise TypeError("cannot add '%s' to '%s' objects" % (type(other), type(self)))

    def __rmul__(self, other):
        ''' multiply other with self, e.g. 2.*Store() '''
        return type(self)(self*other)

    def __imul__(self, other):
        ''' inplace multiply self with other, e.g. Store() * 2. '''
        if not conversion.convertToFloat(other) is None:#check if 'other' is numerical value, i.e. can be converted to a float
            for key_ in list(self.getObjects().keys()):
                if conversion.convertToFloat(self.getObject(key_)) is None:
                    self.setObject(key_, None)
                else:
                    self.setObject(key_, self.getObject(key_)*other)
            return self
        elif isinstance(other, type(self)): #multiply 'Store' objects with 'Store' objects
            for key_ in list(self.getObjects().keys()):
                if other.hasKey(key_):
                    if conversion.convertToFloat(self.getObject(key_)) is None or conversion.convertToFloat(other.getObject(key_)) is None:
                        self.setObject(key_, None)
                    else:
                        self.setObject(key_, self.getObject(key_)*other.getObject(key_))
            return self
        else:
            raise TypeError("cannot multiply '%s' to '%s' objects" % (type(other), type(self)))

    def __div__(self, other):
        ''' divide self with other, e.g. Store()/2. '''
        if not conversion.convertToFloat(other) is None:#check if 'other' is numerical value, i.e. can be converted to a float
            values = {}
            for key in list(self.getObjects().keys()):
                if conversion.convertToFloat(self.getObject(key)) is None:
                    values[key]=None
                else:
                    values[key] = self.getObject(key)/other

            return type(self)(values)
        elif isinstance(other, type(self)): #multiply 'Store' objects with 'Store' objects
            values = {}
            for key_ in list(self.getObjects().keys()):
                values[key_] = self.getObject(key_)
                if other.hasKey(key_):
                     #exclude division by 0.
                    if other.getObject(key_) and not (conversion.convertToFloat(self.getObject(key_)) is None or conversion.convertToFloat(other.getObject(key_)) is None):
                        values[key_] /= other.getObject(key_)
                    else:
                        values[key_] = None
            return type(self)(values)
        else:
            raise TypeError("cannot divide '%s' by '%s' objects" % (type(other), type(self)))

    def __rdiv__(self, other):
        raise NotImplementedError

    def __idiv__(self, other):
        ''' inplace divide self with other, e.g. Store() / 2. '''
        if not conversion.convertToFloat(other) is None:#check if 'other' is numerical value, i.e. can be converted to a float
            for key_ in list(self.getObjects().keys()):
                if other and not (conversion.convertToFloat(key_) is None):
                    self.setObject(key_, self.getObject(key_)/other)
                else:
                    self.setObject(key_, None)
            return self
        elif isinstance(other, type(self)): #divide 'Store' objects with 'Store' objects
            for key_ in list(self.getObjects().keys()):
                if other.hasKey(key_):
                    #exclude zeros and non digits
                    if other.getObject(key_) and not (conversion.convertToFloat(self.getObject(key_)) is None or conversion.convertToFloat(other.getObject(key_)) is None):
                        self.setObject(key_, self.getObject(key_)/other.getObject(key_))
                    else:
                        self.setObject(key_, None)
            return self
        else:
            raise TypeError("cannot multiply '%s' to '%s' objects" % (type(other), type(self)))

    def __abs__(self):
        values = {}
        for key_ in list(self.getObjects().keys()):
            if not conversion.convertToFloat(self.getObject(key_)) is None:
                values[key_] = abs(self.getObject(key_))
            else:
                values[key_] = self.getObject(key_)
        return type(self)(values)