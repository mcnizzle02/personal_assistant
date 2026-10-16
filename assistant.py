# assistant.py - the chat loop that connects you, Claude, and the tools
from dotenv import load_dotenv
import anthropic
from tools import setup_database, TOOL_DEFINITIONS, run_tool

load_dotenv()                  # loads ANTHROPIC_API_KEY from your .env file
client = anthropic.Anthropic() # picks up the key automatically
MODEL = "claude-sonnet-5-5"

SYSTEM_PROMPT = """You are Lee's personal assistant. You help him manage tasks and notes.
Keep replies short, because they will eventually be sent as text messages.
Use your tools whenever Lee asks about tasks or notes. Never guess a task ID."""


def chat():
    setup_database()
    messages = []   # the conversation history; Claude has no memory between calls
    print("Assistant ready. Type 'quit' to exit.\n")

    while True:                                 # OUTER LOOP: one pass per thing you type
        user_input = input("You: ").strip()
        if user_input.lower() in ("quit", "exit"):
            break
        if not user_input:
            continue
        messages.append({"role": "user", "content": user_input})

        while True:                             # INNER LOOP: keep going while Claude uses tools
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break                           # Claude is done and has a final answer

            # Claude asked for one or more tools: run them and send back the results
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    print(f"  [tool: {block.name} {block.input}]")
                    result = run_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,   # tells Claude which request this answers
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})

        reply = "".join(b.text for b in response.content if b.type == "text")
        print(f"\nAssistant: {reply}\n")


if __name__ == "__main__":
    chat()