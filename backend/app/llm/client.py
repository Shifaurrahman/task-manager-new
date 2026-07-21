import json

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


def call_agentic(
    system: str,
    user_message: str,
    tools: list[dict],
    tool_handlers: dict,
    final_tool_name: str,
    required_keys: list[str] | None = None,
    max_turns: int = 6,
) -> dict:
    """
    Multi-turn agentic loop: the model can freely choose to call any tool in
    `tools` (e.g. a retrieval tool like search_concepts) as many times as it
    wants, getting real results back each time, before finally calling
    `final_tool_name` (e.g. extract_concepts) to produce its structured answer.

    Unlike call_with_tool(), tool_choice is NOT forced here - the model decides
    which tool to call each turn, which is what lets it "pull" context on
    demand instead of having everything pushed into the prompt upfront.

    tool_handlers: dict mapping tool name -> callable(tool_input: dict) -> Any.
    Every tool in `tools` except final_tool_name must have a handler here.

    max_turns guards against the model looping on retrieval calls forever
    without ever reaching the final tool.
    """
    messages = [{"role": "user", "content": user_message}]

    for turn in range(max_turns):
        response = _client.messages.create(
            model=settings.model,
            max_tokens=2000,
            system=system,
            messages=messages,
            tools=tools,
        )

        tool_blocks = [b for b in response.content if b.type == "tool_use"]

        if not tool_blocks:
            # Model responded with plain text instead of a tool call - nudge it.
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": f"Please respond by calling one of the available tools, ending with {final_tool_name}.",
            })
            continue

        final_call = next((b for b in tool_blocks if b.name == final_tool_name), None)
        if final_call:
            result = final_call.input
            missing = [k for k in (required_keys or []) if k not in result]
            if not missing:
                return result

            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": final_call.id,
                        "content": (
                            f"Missing required field(s): {', '.join(missing)}. "
                            f"Call {final_tool_name} again and include every required field this time."
                        ),
                    }
                ],
            })
            continue

        # Otherwise, execute whichever retrieval/lookup tool(s) the model asked for.
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in tool_blocks:
            print(f"[TOOL CALL] {block.name}({block.input})")   
            handler = tool_handlers.get(block.name)
            if handler is None:
                output = f"Error: no handler registered for tool '{block.name}'"
            else:
                try:
                    output = json.dumps(handler(block.input))
                    print(f"[TOOL RESULT] {output[:300]}")
                except Exception as e:
                    output = f"Error running tool '{block.name}': {e}"
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": output,
            })
        messages.append({"role": "user", "content": tool_results})

    raise ValueError(
        f"Model did not call {final_tool_name} within {max_turns} turns. "
        "It may be stuck looping on retrieval calls."
    )


def call_text(system: str, user_message: str) -> str:
    """Plain text generation, e.g. for drafting concept file body content."""
    response = _client.messages.create(
        model=settings.model,
        max_tokens=1500,
        system=system,
        messages=[{"role": "user", "content": user_message}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()