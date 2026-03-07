"""
Simulation node — placeholder for future what-if / simulation features.
"""

import logging

logger = logging.getLogger(__name__)


def handle_simulation(user_message: str, chat_summary: str) -> dict:
    """Placeholder for simulation intent. Returns a not-yet-available message."""
    logger.info("  [SIMULATION] Placeholder hit — feature not yet implemented")
    return {
        "message": "Simulation features are coming soon! This will support what-if scenarios, "
                   "backward planning from target dates, and impact analysis. "
                   "In the meantime, I can help you with scheduling, filters, and dashboard data.",
        "actions": [],
    }
