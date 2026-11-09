# # import asyncio
# # from decimal import Decimal
# # from app.adapters.gemini_adapter import GeminiAdapter
# # from dotenv import load_dotenv

# # load_dotenv()

# # async def test():
# #     adapter = GeminiAdapter()

# #     result = await adapter.dispatch(
# #         prompt="Reply with exactly: Gemini adapter works",
# #         model_name="gemini-3.1-flash-lite",
# #         cost_per_input_token=Decimal("0.0000001"),
# #         cost_per_output_token=Decimal("0.0000004"),
# #     )

# #     print("Status:", result.status)
# #     print("Response:", result.response_text)
# #     print("Input tokens:", result.input_token_count)
# #     print("Output tokens:", result.output_token_count)
# #     print("Latency:", result.latency_ms, "ms")
# #     print("Estimated cost:", result.estimated_cost)
# #     print("Error:", result.error_message)

# # asyncio.run(test())
# import asyncio
# from decimal import Decimal
# from dotenv import load_dotenv
# from app.adapters.ollama_adapter import OllamaAdapter

# load_dotenv(".env", override=True)

# async def test():
#     result = await OllamaAdapter().dispatch(
#         prompt="Reply with exactly: Ollama adapter works",
#         model_name="qwen2.5:3b",
#         cost_per_input_token=Decimal("0.0000001"),
#         cost_per_output_token=Decimal("0.0000004"),
#     )

#     print("Status:", result.status)
#     print("Response:", result.response_text)
#     print("Input tokens:", result.input_token_count)
#     print("Output tokens:", result.output_token_count)
#     print("Latency:", result.latency_ms, "ms")
#     print("Estimated cost:", result.estimated_cost)
#     print("Error:", result.error_message)

# asyncio.run(test())
import asyncio
from decimal import Decimal
from dotenv import load_dotenv
from app.adapters.groq_adapter import GroqAdapter

load_dotenv(".env", override=True)

async def test():
    result = await GroqAdapter().dispatch(
        prompt="Reply with exactly: Groq adapter works",
        model_name="openai/gpt-oss-20b",
        cost_per_input_token=Decimal("0.0000001"),
        cost_per_output_token=Decimal("0.0000004"),
    )

    print("Status:", result.status)
    print("Response:", result.response_text)
    print("Input tokens:", result.input_token_count)
    print("Output tokens:", result.output_token_count)
    print("Latency:", result.latency_ms, "ms")
    print("Estimated cost:", result.estimated_cost)
    print("Error:", result.error_message)

asyncio.run(test())