"""
Base agent implementation for COO Assistant.
Each specialized agent inherits from this base class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from enum import Enum
import anthropic


class AgentType(Enum):
    STRATEGY = "strategy"
    PEOPLE = "people"
    PROCESS = "process"
    FINANCE = "finance"


@dataclass
class AgentContext:
    """Context passed to agents for decision-making."""
    user_query: str
    org_context: dict[str, Any]
    session_memory: list[dict]
    relevant_documents: list[str]
    current_date: str
    user_permissions: list[str]


@dataclass
class AgentResponse:
    """Standardized response from agents."""
    agent_type: AgentType
    response_text: str
    confidence: float
    actions_suggested: list[dict]
    sources_used: list[str]
    follow_up_questions: list[str]
    requires_human_approval: bool = False


class BaseAgent(ABC):
    """Base class for all COO specialized agents."""

    def __init__(self, agent_type: AgentType, model: str = "claude-sonnet-4-20250514"):
        self.agent_type = agent_type
        self.model = model
        self.client = anthropic.Anthropic()

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the specialized system prompt for this agent."""
        pass

    @property
    @abstractmethod
    def available_tools(self) -> list[dict]:
        """Return the tools this agent can use."""
        pass

    async def process(self, context: AgentContext) -> AgentResponse:
        """Process a request with this agent's specialization."""
        messages = self._build_messages(context)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=self.system_prompt,
            tools=self.available_tools,
            messages=messages,
        )

        return self._parse_response(response)

    def _build_messages(self, context: AgentContext) -> list[dict]:
        """Build the message array for Claude."""
        messages = []

        # Add session memory as prior conversation
        for memory_item in context.session_memory[-10:]:  # Last 10 exchanges
            messages.append(memory_item)

        # Add the current query with context
        user_message = f"""
Current Date: {context.current_date}

Organizational Context:
{self._format_org_context(context.org_context)}

Relevant Documents:
{self._format_documents(context.relevant_documents)}

User Query: {context.user_query}
"""
        messages.append({"role": "user", "content": user_message})

        return messages

    def _format_org_context(self, org_context: dict) -> str:
        """Format organizational context for the prompt."""
        lines = []
        for key, value in org_context.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines) if lines else "No additional context available."

    def _format_documents(self, documents: list[str]) -> str:
        """Format retrieved documents for the prompt."""
        if not documents:
            return "No relevant documents found."
        return "\n---\n".join(documents[:5])  # Limit to 5 most relevant

    def _parse_response(self, response) -> AgentResponse:
        """Parse Claude's response into structured format."""
        # Extract text content
        text_content = ""
        actions = []

        for block in response.content:
            if block.type == "text":
                text_content = block.text
            elif block.type == "tool_use":
                actions.append({
                    "tool": block.name,
                    "input": block.input,
                })

        return AgentResponse(
            agent_type=self.agent_type,
            response_text=text_content,
            confidence=0.85,  # Could be enhanced with self-evaluation
            actions_suggested=actions,
            sources_used=[],
            follow_up_questions=[],
            requires_human_approval=len(actions) > 0,
        )
