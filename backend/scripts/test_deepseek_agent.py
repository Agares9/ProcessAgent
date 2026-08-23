import asyncio

from app.config import get_settings
from app.llm.client import ChatMessage
from app.llm.deepseek import DeepSeekClient


async def main() -> None:
    settings = get_settings()
    print("key_set=", bool(settings.deepseek_api_key))
    print("base_url=", settings.deepseek_base_url)
    print("model=", settings.deepseek_model)
    client = DeepSeekClient(settings)
    reply = await client.complete(
        [ChatMessage.user("Reply with exactly: pong")],
        temperature=0.0,
        max_tokens=8,
    )
    print("reply=", reply)


if __name__ == "__main__":
    asyncio.run(main())
