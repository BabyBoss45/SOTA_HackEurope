# -*- coding: utf-8 -*-
"""
SOTA Agents - Multi-Agent System on Solana
"""

from .hackathon.agent import HackathonAgent, create_hackathon_agent
from .competitor_fun.agent import CompetitorFunAgent, create_competitor_fun_agent

__all__ = [
    "HackathonAgent",
    "create_hackathon_agent",
    "CompetitorFunAgent",
    "create_competitor_fun_agent",
]
