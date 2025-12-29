# COO Assistant

An AI-powered Chief Operating Officer assistant built with Claude.

## Overview

This system enables Claude to act as your COO by:

- **Monitoring operations** across your organization
- **Synthesizing information** from multiple tools and sources
- **Proactively alerting** you to risks and opportunities
- **Preparing materials** for meetings and reviews
- **Supporting decisions** with context and analysis

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed system design.

## Quick Start

```bash
# Clone and setup
git clone <repo>
cd coo-assistant

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run the Slack bot
python -m src.integrations.slack_bot
```

## Configuration

### Required Environment Variables

```env
ANTHROPIC_API_KEY=sk-ant-...
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=...
SLACK_APP_TOKEN=xapp-...
```

### Organizational Context

Edit `config/org_context.example.json` and save as `config/org_context.json`:

```json
{
  "company": {
    "name": "Your Company",
    "industry": "...",
    ...
  }
}
```

## Architecture

```
src/
├── agents/           # Specialized AI agents
│   ├── base.py       # Base agent class
│   ├── strategy.py   # Strategy & OKR agent
│   └── orchestrator.py  # Multi-agent orchestration
├── memory/           # Context and memory management
│   └── context_store.py  # Knowledge base
├── integrations/     # External tool integrations
│   └── slack_bot.py  # Slack interface
└── api/              # REST API endpoints
```

## Usage Examples

### Via Slack

```
@coo-bot What's the status of our Q1 OKRs?

@coo-bot Prepare the weekly ops review

@coo-bot What decisions have we made about the EU expansion?
```

### Via CLI (Claude Code)

```bash
# Using Claude Code with this project's context
claude "What blockers should I address this week?"
```

## Extending the System

### Adding a New Agent

1. Create a new file in `src/agents/` (e.g., `people.py`)
2. Inherit from `BaseAgent`
3. Implement `system_prompt` and `available_tools`
4. Register in `orchestrator.py`

### Adding Integrations

Use MCP (Model Context Protocol) servers for tool integrations:

```python
# In your Claude Code config (~/.claude.json)
{
  "mcpServers": {
    "linear": {
      "command": "npx",
      "args": ["@anthropics/mcp-linear"]
    }
  }
}
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy src/

# Linting
ruff check src/
```

## License

MIT
