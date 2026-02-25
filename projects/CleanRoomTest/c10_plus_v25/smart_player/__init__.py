"""
Smart Player Package
=====================
AI-driven game navigation using screen classification + navigation graphs.

Components:
  - classifier:      Screen type classification (hash cache + Claude Vision)
  - nav_graph:        Navigation graph (screen transitions)
  - navigator:        Smart navigation engine (recognize -> decide -> execute)
  - popup_handler:    Popup/tutorial detection + dismissal
  - mission_router:   Mission -> target screen mapping
  - smart_capture:    Orchestrator for 10-mission capture sessions
"""

from smart_player.classifier import ScreenClassifier, ScreenClassification
from smart_player.nav_graph import NavigationGraph, NavNode, NavEdge, NavAction
from smart_player.navigator import SmartNavigator
from smart_player.popup_handler import PopupHandler
from smart_player.mission_router import MissionRouter
from smart_player.smart_capture import smart_capture, build_nav_graph
