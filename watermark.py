import os
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.core import *

class WatermarkPluginLayer(QgsPluginLayer):
  LAYER_TYPE="OpenALAQS"

  def __init__(self):
    QgsPluginLayer.__init__(self, WatermarkPluginLayer.LAYER_TYPE, WatermarkPluginLayer.LAYER_TYPE)
    self.setValid(True)

  def draw(self, rendererContext):
    image = QImage(os.path.dirname(__file__) + "/icon.png")
    if not (image is None):
        painter = rendererContext.painter()
        painter.save()
        painter.drawImage(10, 10, image)
        painter.restore()
        return True

    self.setValid(False)
    return False