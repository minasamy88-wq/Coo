"""
Context Store - Manages organizational context and memory for the COO system.
Uses vector embeddings for semantic search and retrieval.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import json
import hashlib


@dataclass
class Document:
    """A document in the knowledge base."""
    id: str
    content: str
    doc_type: str  # policy, meeting_notes, decision, playbook
    metadata: dict = field(default_factory=dict)
    embedding: Optional[list[float]] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class Decision:
    """Record of a decision made with the COO system."""
    id: str
    timestamp: datetime
    context: str
    options_considered: list[str]
    decision_made: str
    rationale: str
    participants: list[str]
    outcome: Optional[str] = None
    outcome_recorded_at: Optional[datetime] = None


@dataclass
class SessionMemory:
    """Memory from a conversation session."""
    session_id: str
    user_id: str
    started_at: datetime
    messages: list[dict] = field(default_factory=list)
    summary: Optional[str] = None
    action_items: list[str] = field(default_factory=list)


class ContextStore:
    """
    Central store for organizational context and memory.

    In production, this would be backed by:
    - PostgreSQL for structured data
    - Pinecone/Weaviate for vector search
    - Redis for session caching
    """

    def __init__(self):
        # In-memory stores (replace with database in production)
        self._documents: dict[str, Document] = {}
        self._decisions: dict[str, Decision] = {}
        self._sessions: dict[str, SessionMemory] = {}
        self._org_context: dict[str, Any] = {}

    # --- Organizational Context ---

    def set_org_context(self, key: str, value: Any) -> None:
        """Set an organizational context value."""
        self._org_context[key] = {
            "value": value,
            "updated_at": datetime.now().isoformat(),
        }

    def get_org_context(self, key: Optional[str] = None) -> Any:
        """Get organizational context. If key is None, return all."""
        if key is None:
            return {k: v["value"] for k, v in self._org_context.items()}
        return self._org_context.get(key, {}).get("value")

    def load_org_context_from_file(self, filepath: str) -> None:
        """Load organizational context from a JSON file."""
        with open(filepath, "r") as f:
            data = json.load(f)
            for key, value in data.items():
                self.set_org_context(key, value)

    # --- Document Management ---

    def add_document(
        self,
        content: str,
        doc_type: str,
        metadata: Optional[dict] = None,
    ) -> Document:
        """Add a document to the knowledge base."""
        doc_id = hashlib.sha256(content.encode()).hexdigest()[:16]

        doc = Document(
            id=doc_id,
            content=content,
            doc_type=doc_type,
            metadata=metadata or {},
        )

        # In production, compute embedding here
        # doc.embedding = self._compute_embedding(content)

        self._documents[doc_id] = doc
        return doc

    def search_documents(
        self,
        query: str,
        doc_type: Optional[str] = None,
        limit: int = 5,
    ) -> list[Document]:
        """
        Search documents by semantic similarity.

        In production, this would:
        1. Compute query embedding
        2. Vector similarity search in Pinecone/Weaviate
        3. Return top-k results
        """
        # Simplified keyword search (replace with vector search)
        results = []
        query_lower = query.lower()

        for doc in self._documents.values():
            if doc_type and doc.doc_type != doc_type:
                continue
            if query_lower in doc.content.lower():
                results.append(doc)

        return results[:limit]

    # --- Decision Memory ---

    def record_decision(
        self,
        context: str,
        options: list[str],
        decision: str,
        rationale: str,
        participants: list[str],
    ) -> Decision:
        """Record a decision for future reference."""
        dec_id = hashlib.sha256(
            f"{context}{decision}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        dec = Decision(
            id=dec_id,
            timestamp=datetime.now(),
            context=context,
            options_considered=options,
            decision_made=decision,
            rationale=rationale,
            participants=participants,
        )

        self._decisions[dec_id] = dec
        return dec

    def record_decision_outcome(self, decision_id: str, outcome: str) -> None:
        """Record the outcome of a previous decision."""
        if decision_id in self._decisions:
            self._decisions[decision_id].outcome = outcome
            self._decisions[decision_id].outcome_recorded_at = datetime.now()

    def search_decisions(
        self,
        query: str,
        limit: int = 5,
    ) -> list[Decision]:
        """Search past decisions for relevant context."""
        results = []
        query_lower = query.lower()

        for dec in self._decisions.values():
            if (
                query_lower in dec.context.lower()
                or query_lower in dec.decision_made.lower()
            ):
                results.append(dec)

        # Sort by timestamp, most recent first
        results.sort(key=lambda d: d.timestamp, reverse=True)
        return results[:limit]

    # --- Session Memory ---

    def create_session(self, user_id: str) -> SessionMemory:
        """Create a new conversation session."""
        session_id = hashlib.sha256(
            f"{user_id}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        session = SessionMemory(
            session_id=session_id,
            user_id=user_id,
            started_at=datetime.now(),
        )

        self._sessions[session_id] = session
        return session

    def add_message_to_session(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        """Add a message to a session."""
        if session_id in self._sessions:
            self._sessions[session_id].messages.append({
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat(),
            })

    def get_session_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Get messages from a session."""
        if session_id not in self._sessions:
            return []

        messages = self._sessions[session_id].messages
        if limit:
            return messages[-limit:]
        return messages

    def summarize_session(self, session_id: str, summary: str) -> None:
        """Store a summary of the session."""
        if session_id in self._sessions:
            self._sessions[session_id].summary = summary

    # --- Context Building ---

    def build_agent_context(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        Build comprehensive context for agent processing.

        This is the main method called by the orchestrator to gather
        all relevant context for a request.
        """
        context = {
            "org_context": self.get_org_context(),
            "relevant_documents": [],
            "relevant_decisions": [],
            "session_memory": [],
        }

        # Retrieve relevant documents
        docs = self.search_documents(query, limit=3)
        context["relevant_documents"] = [
            {"id": d.id, "type": d.doc_type, "content": d.content[:500]}
            for d in docs
        ]

        # Retrieve relevant past decisions
        decisions = self.search_decisions(query, limit=3)
        context["relevant_decisions"] = [
            {
                "context": d.context,
                "decision": d.decision_made,
                "rationale": d.rationale,
                "outcome": d.outcome,
            }
            for d in decisions
        ]

        # Include session memory if available
        if session_id:
            context["session_memory"] = self.get_session_messages(
                session_id, limit=10
            )

        return context


# Singleton instance
_context_store: Optional[ContextStore] = None


def get_context_store() -> ContextStore:
    """Get the singleton context store instance."""
    global _context_store
    if _context_store is None:
        _context_store = ContextStore()
    return _context_store
