"""
Navigation Module
==================
Screen classification, navigation graph, popup handling, smart navigation.
Ported from C10+ smart_player with adapted imports.
"""

from .classifier import ScreenClassifier, ScreenClassification
from .nav_graph import NavigationGraph, NavNode, NavEdge, NavAction
from .popup_handler import PopupHandler
from .screen_navigator import ScreenNavigator, NavigationState

__all__ = [
    "ScreenClassifier",
    "ScreenClassification",
    "NavigationGraph",
    "NavNode",
    "NavEdge",
    "NavAction",
    "PopupHandler",
    "ScreenNavigator",
    "NavigationState",
]
