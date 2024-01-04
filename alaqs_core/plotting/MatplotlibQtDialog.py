import matplotlib

matplotlib.use("Qt5Agg")

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.backends.qt_compat import QtWidgets


class MatplotlibQtDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(MatplotlibQtDialog, self).__init__(parent)
        # QtGui.QWidget.__init__(self,parent)

        self._figure = plt.figure()
        self._axes = self._figure.add_subplot(111)
        self._plot = None
        # self._axes.hold(False)

        self._canvas = FigureCanvas(self._figure)
        self._canvas.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
        )
        self._canvas.updateGeometry()
        # layout.setStyleSheet("background:white")

        self._toolbar = NavigationToolbar(self._canvas, parent=self)

        self._closeButton = QtWidgets.QPushButton("Close")
        self._closeButton.clicked.connect(self.close)

        # layout
        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self._toolbar)
        layout.addWidget(self._canvas)
        layout.addWidget(self._closeButton)
        self.setLayout(layout)

    def plot(self, *args, **kw):
        self._plot = self._axes.plot(*args, **kw)
        self._canvas.draw()
        return self._plot

    def getAxes(self):
        # return plt.gca()
        return plt.gca()

    def getFigure(self):
        # return plt.gcf()
        return self._figure

    def getCanvas(self):
        return self._canvas

    def getPlt(self):
        return plt


# if __name__ == '__main__':
#     import sys
#
#     app = QtWidgets.QApplication(sys.argv)
#
#     main = MatplotlibQtDialog()
#     main.show()
#
#     sys.exit(app.exec_())
