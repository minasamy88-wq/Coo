"""
Slack Bot Integration for COO Assistant.
Handles incoming messages and commands from Slack.
"""

import os
import asyncio
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from ..agents.orchestrator import AgentOrchestrator, COORequest


# Initialize Slack app
app = AsyncApp(
    token=os.environ.get("SLACK_BOT_TOKEN"),
    signing_secret=os.environ.get("SLACK_SIGNING_SECRET"),
)

# Initialize COO orchestrator
orchestrator = AgentOrchestrator()


@app.event("app_mention")
async def handle_mention(event: dict, say, client) -> None:
    """Handle @coo-bot mentions in channels."""
    user_id = event["user"]
    channel = event["channel"]
    text = event["text"]
    thread_ts = event.get("thread_ts", event["ts"])

    # Remove the bot mention from the text
    query = text.split(">", 1)[-1].strip() if ">" in text else text

    # Show typing indicator
    await client.reactions_add(
        channel=channel,
        timestamp=event["ts"],
        name="thinking_face",
    )

    try:
        # Process through COO system
        request = COORequest(
            user_id=user_id,
            query=query,
            channel="slack",
            context={"channel": channel, "thread": thread_ts},
        )

        response = await orchestrator.process_request(request)

        # Format response for Slack
        blocks = format_response_blocks(response)

        await say(
            blocks=blocks,
            text=response.response_text,  # Fallback text
            thread_ts=thread_ts,
        )

        # Remove thinking indicator
        await client.reactions_remove(
            channel=channel,
            timestamp=event["ts"],
            name="thinking_face",
        )
        await client.reactions_add(
            channel=channel,
            timestamp=event["ts"],
            name="white_check_mark",
        )

    except Exception as e:
        await say(
            text=f"Sorry, I encountered an error: {str(e)}",
            thread_ts=thread_ts,
        )


@app.command("/coo")
async def handle_slash_command(ack, respond, command: dict) -> None:
    """Handle /coo slash commands."""
    await ack()

    user_id = command["user_id"]
    query = command["text"]

    request = COORequest(
        user_id=user_id,
        query=query,
        channel="slack",
        context={"type": "slash_command"},
    )

    response = await orchestrator.process_request(request)

    # Respond ephemerally first (only visible to user)
    await respond(
        text=response.response_text,
        response_type="ephemeral",
    )


@app.action("approve_action")
async def handle_action_approval(ack, body, client) -> None:
    """Handle approval of suggested actions."""
    await ack()

    action_id = body["actions"][0]["value"]
    user_id = body["user"]["id"]

    # In production, execute the approved action
    # action = get_pending_action(action_id)
    # result = await execute_action(action, approved_by=user_id)

    await client.chat_postMessage(
        channel=body["channel"]["id"],
        thread_ts=body["message"]["ts"],
        text=f"Action approved and executed by <@{user_id}>",
    )


@app.action("reject_action")
async def handle_action_rejection(ack, body, client) -> None:
    """Handle rejection of suggested actions."""
    await ack()

    action_id = body["actions"][0]["value"]
    user_id = body["user"]["id"]

    await client.chat_postMessage(
        channel=body["channel"]["id"],
        thread_ts=body["message"]["ts"],
        text=f"Action rejected by <@{user_id}>",
    )


def format_response_blocks(response) -> list[dict]:
    """Format COO response as Slack blocks."""
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": response.response_text,
            },
        },
    ]

    # Add action buttons if there are pending actions
    if response.actions_to_approve:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Suggested Actions:*",
            },
        })

        for i, action in enumerate(response.actions_to_approve[:3]):
            action_id = f"action_{i}"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"• {action.get('tool', 'Action')}: {action.get('input', {})}",
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Approve"},
                    "style": "primary",
                    "action_id": "approve_action",
                    "value": action_id,
                },
            })

    # Add follow-up suggestions
    if response.suggested_follow_ups:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "*You might also ask:* "
                    + " | ".join(response.suggested_follow_ups[:3]),
                }
            ],
        })

    return blocks


async def start_slack_bot() -> None:
    """Start the Slack bot."""
    handler = AsyncSocketModeHandler(
        app,
        os.environ.get("SLACK_APP_TOKEN"),
    )
    await handler.start_async()


if __name__ == "__main__":
    asyncio.run(start_slack_bot())
