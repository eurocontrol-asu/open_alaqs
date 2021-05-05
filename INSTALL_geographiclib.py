#must be executed from QGIS Python console as QGIS is shipped with own python

from future import standard_library
standard_library.install_aliases()
if __name__ == "__main__":
    import os
    import urllib.request, urllib.parse, urllib.error
    import tempfile

    #Get path of PIP install script
    pip_path = os.path.join(tempfile.gettempdir(), "get-pip.py")

    #Download file to temp directory
    #urllib.urlretrieve("https://raw.github.com/pypa/pip/master/contrib/get-pip.py", pip_path)
    urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", pip_path)

    #Run PIP install script
    os.system('python %s' % (pip_path))

    #Use PIP to install geographiclib
    os.system('python -m pip install -U geographiclib')

    #http://matplotlib.org/users/customizing.html
    #fix bug in QGIS 2.x: Default matplotlib backend is TkAgg, but tkinter not installed
    import matplotlib
    matplotlib.rcParams['backend'] = "Qt5Agg"