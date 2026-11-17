"""Action Desk: rule-model voting desk over real exchange daily candles."""
from cryptoscope.desk.engine import build_desk
from cryptoscope.desk.feed import DeskFeed

__all__ = ["build_desk", "DeskFeed"]
