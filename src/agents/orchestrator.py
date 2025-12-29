"""
Agent Orchestrator - Routes requests to appropriate specialized agents.
"""

import asyncio
from dataclasses import dataclass
from typing import Optional
import anthropic

from .base import AgentContext, AgentResponse, AgentType
from .strategy import StrategyAgent


@dataclass
class COORequest:
    """Incoming request to the COO system."""
    user_id: str
    query: str
    channel: str  # slack, web, cli, email
    context: dict
    priority: str = "normal"


@dataclass
class COOResponse:
    """Response from the COO system."""
    response_text: str
    agent_contributions: list[AgentResponse]
    actions_to_approve: list[dict]
    suggested_follow_ups: list[str]


class AgentOrchestrator:
    """
    Orchestrates requests across specialized agents.
    Uses Claude to classify intent and route appropriately.
    """

    def __init__(self):
        self.client = anthropic.Anthropic()
        self.agents = {
            AgentType.STRATEGY: StrategyAgent(),
            # AgentType.PEOPLE: PeopleAgent(),
            # AgentType.PROCESS: ProcessAgent(),
            # AgentType.FINANCE: FinanceAgent(),
        }

    async def process_request(self, request: COORequest) -> COOResponse:
        """Main entry point for processing COO requests."""

        # Step 1: Classify the request
        classification = await self._classify_request(request)

        # Step 2: Gather context
        context = await self._build_context(request, classification)

        # Step 3: Route to appropriate agent(s)
        agent_responses = await self._route_to_agents(
            classification["agents_needed"],
            context,
        )

        # Step 4: Synthesize responses
        final_response = await self._synthesize_response(
            request,
            agent_responses,
        )

        return final_response

    async def _classify_request(self, request: COORequest) -> dict:
        """Use Claude to classify the request and determine routing."""

        classification_prompt = f"""Analyze this COO assistant request and classify it.

Request: {request.query}
Channel: {request.channel}
Context: {request.context}

Respond with a JSON object containing:
- "agents_needed": list of agent types to involve (strategy, people, process, finance)
- "intent": brief description of what the user wants
- "urgency": low, medium, high
- "requires_multi_agent": boolean if multiple agents should collaborate
- "suggested_approach": brief description of how to handle this

Only include agents that are truly necessary. Most requests need 1-2 agents."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{"role": "user", "content": classification_prompt}],
        )

        # Parse the response (simplified - would use structured output in production)
        import json
        try:
            result = json.loads(response.content[0].text)
        except json.JSONDecodeError:
            # Default classification
            result = {
                "agents_needed": ["strategy"],
                "intent": "general query",
                "urgency": "medium",
                "requires_multi_agent": False,
            }

        return result

    async def _build_context(
        self,
        request: COORequest,
        classification: dict,
    ) -> AgentContext:
        """Build the context object for agent processing."""
        from datetime import datetime

        # In production, this would:
        # 1. Query vector DB for relevant documents
        # 2. Fetch org context from database
        # 3. Load session memory
        # 4. Get user permissions

        return AgentContext(
            user_query=request.query,
            org_context={
                "company": "Example Corp",
                "current_quarter": "Q1-2025",
                "team_count": 5,
            },
            session_memory=[],
            relevant_documents=[],
            current_date=datetime.now().isoformat(),
            user_permissions=["read", "recommend"],
        )

    async def _route_to_agents(
        self,
        agents_needed: list[str],
        context: AgentContext,
    ) -> list[AgentResponse]:
        """Route request to appropriate agents, potentially in parallel."""

        tasks = []
        for agent_name in agents_needed:
            try:
                agent_type = AgentType(agent_name)
                if agent_type in self.agents:
                    agent = self.agents[agent_type]
                    tasks.append(agent.process(context))
            except ValueError:
                continue  # Skip unknown agent types

        if not tasks:
            # Default to strategy agent
            tasks.append(self.agents[AgentType.STRATEGY].process(context))

        # Run agents in parallel
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions
        valid_responses = [r for r in responses if isinstance(r, AgentResponse)]

        return valid_responses

    async def _synthesize_response(
        self,
        request: COORequest,
        agent_responses: list[AgentResponse],
    ) -> COOResponse:
        """Synthesize multiple agent responses into a coherent answer."""

        if len(agent_responses) == 1:
            # Single agent - use response directly
            ar = agent_responses[0]
            return COOResponse(
                response_text=ar.response_text,
                agent_contributions=agent_responses,
                actions_to_approve=ar.actions_suggested,
                suggested_follow_ups=ar.follow_up_questions,
            )

        # Multiple agents - synthesize with Claude
        synthesis_prompt = f"""You are synthesizing responses from multiple COO agents.

Original Request: {request.query}

Agent Responses:
{self._format_agent_responses(agent_responses)}

Create a unified response that:
1. Combines insights from all agents coherently
2. Highlights any conflicting recommendations
3. Prioritizes the most actionable information
4. Maintains a clear, executive-friendly tone"""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": synthesis_prompt}],
        )

        # Collect all actions and follow-ups
        all_actions = []
        all_follow_ups = []
        for ar in agent_responses:
            all_actions.extend(ar.actions_suggested)
            all_follow_ups.extend(ar.follow_up_questions)

        return COOResponse(
            response_text=response.content[0].text,
            agent_contributions=agent_responses,
            actions_to_approve=all_actions,
            suggested_follow_ups=list(set(all_follow_ups)),
        )

    def _format_agent_responses(self, responses: list[AgentResponse]) -> str:
        """Format agent responses for synthesis prompt."""
        formatted = []
        for r in responses:
            formatted.append(f"[{r.agent_type.value.upper()} AGENT]\n{r.response_text}\n")
        return "\n---\n".join(formatted)
