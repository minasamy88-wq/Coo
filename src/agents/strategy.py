"""
Strategy Agent - Handles OKRs, initiatives, roadmaps, and strategic planning.
"""

from .base import BaseAgent, AgentType


class StrategyAgent(BaseAgent):
    """Agent specialized in strategic operations and planning."""

    def __init__(self):
        super().__init__(AgentType.STRATEGY)

    @property
    def system_prompt(self) -> str:
        return """You are the Strategy Agent within an AI COO system. Your role is to:

1. MONITOR strategic initiatives and OKR progress
2. IDENTIFY risks, blockers, and misalignments early
3. SYNTHESIZE information across teams for executive visibility
4. RECOMMEND prioritization and resource allocation changes
5. PREPARE strategic communications and status updates

Key Responsibilities:
- Track OKR progress and flag items that are off-track
- Analyze project dependencies and identify bottlenecks
- Prepare weekly/monthly executive summaries
- Suggest agenda items for leadership meetings
- Draft strategic communications

Decision Framework:
- Always tie recommendations back to company OKRs
- Consider resource constraints and team capacity
- Highlight trade-offs explicitly
- Provide confidence levels for predictions
- Flag when human judgment is needed

Output Style:
- Be concise and action-oriented
- Lead with the most important information
- Use bullet points for clarity
- Quantify impact when possible
- Suggest next steps explicitly"""

    @property
    def available_tools(self) -> list[dict]:
        return [
            {
                "name": "get_okr_status",
                "description": "Retrieve current OKR status and progress",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "quarter": {"type": "string", "description": "Quarter to check (e.g., Q1-2025)"},
                        "team": {"type": "string", "description": "Optional team filter"},
                    },
                    "required": ["quarter"],
                },
            },
            {
                "name": "get_project_status",
                "description": "Get status of active projects and initiatives",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "project_id": {"type": "string", "description": "Optional specific project"},
                        "status_filter": {
                            "type": "string",
                            "enum": ["all", "at_risk", "blocked", "on_track"],
                        },
                    },
                },
            },
            {
                "name": "create_status_report",
                "description": "Generate a status report document",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "report_type": {
                            "type": "string",
                            "enum": ["weekly", "monthly", "board"],
                        },
                        "include_sections": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["report_type"],
                },
            },
            {
                "name": "flag_risk",
                "description": "Flag a strategic risk for attention",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                        "affected_okrs": {"type": "array", "items": {"type": "string"}},
                        "recommended_action": {"type": "string"},
                    },
                    "required": ["title", "severity"],
                },
            },
        ]
