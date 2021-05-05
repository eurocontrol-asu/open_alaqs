__author__ = 'Dennis Klingebiel'

import os
import sys

# Add the alaqs core directory to system path
# alaqs_core_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__))))
alaqs_core_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

if not alaqs_core_path in sys.path:
    sys.path.append(alaqs_core_path)