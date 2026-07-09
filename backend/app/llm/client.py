import anthropic

from app.config import settings

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def call_with_tool(
    system: str,
    user_message: str,
    tool_schema: dict,
    required_keys: list[str] | None = None,
    max_retries: int = 1,
) -> dict:
    """
    Force the model to respond via a single tool call and return its input dict.

    Claude's `required` list in input_schema is advisory, not enforced - the model
    can still omit a field. If required_keys is given, we check for them and, on a
    miss, send one corrective follow-up turn asking the model to re-call the tool
    with the missing fields included, before giving up with a clear error.
    """
    messages = [{"role": "user", "content": user_message}]

    for attempt in range(max_retries + 1):
        response = _client.messages.create(
            model=settings.model,
            max_tokens=2000,
            system=system,
            messages=messages,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_schema["name"]},
        )

        tool_block = next(
            (b for b in response.content if b.type == "tool_use" and b.name == tool_schema["name"]),
            None,
        )
        if tool_block is None:
            raise ValueError("Model did not return the expected tool call")

        result = tool_block.input
        missing = [k for k in (required_keys or []) if k not in result]
        if not missing:
            return result

        if attempt == max_retries:
            raise ValueError(
                f"Model response missing required field(s) {missing} after "
                f"{max_retries + 1} attempt(s). Raw result: {result}"
            )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": (
                        f"Missing required field(s): {', '.join(missing)}. "
                        "Call the tool again and include every required field this time."
                    ),
                }
            ],
        })

    raise ValueError("Unreachable")


def call_text(system: str, user_message: str) -> str:
    """Plain text generation, e.g. for drafting concept file body content."""
    response = _client.messages.create(
        model=settings.model,
        max_tokens=1500,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()