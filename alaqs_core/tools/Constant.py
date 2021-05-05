from __future__ import print_function
from __future__ import absolute_import
from builtins import object

try:
    from . import __init__
except:
    import __init__

def constant(f):
    def fset(self, value):
        raise SyntaxError
    def fget(self):
        return f()
    return property(fget, fset)

class Constant(object):
    @constant
    def EPSILON():
        return 1e-4
CONST = Constant()

if __name__ == "__main__":
    CONST = Constant()
    # fix_print_with_import
    print(CONST.EPSILON)
