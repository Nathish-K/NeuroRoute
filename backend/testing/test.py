# # # # # import asyncio
# # # # # from decimal import Decimal
# # # # # from app.adapters.gemini_adapter import GeminiAdapter
# # # # # from dotenv import load_dotenv

# # # # # load_dotenv()

# # # # # async def test():
# # # # #     adapter = GeminiAdapter()

# # # # #     result = await adapter.dispatch(
# # # # #         prompt="Reply with exactly: Gemini adapter works",
# # # # #         model_name="gemini-3.1-flash-lite",
# # # # #         cost_per_input_token=Decimal("0.0000001"),
# # # # #         cost_per_output_token=Decimal("0.0000004"),
# # # # #     )

# # # # #     print("Status:", result.status)
# # # # #     print("Response:", result.response_text)
# # # # #     print("Input tokens:", result.input_token_count)
# # # # #     print("Output tokens:", result.output_token_count)
# # # # #     print("Latency:", result.latency_ms, "ms")
# # # # #     print("Estimated cost:", result.estimated_cost)
# # # # #     print("Error:", result.error_message)

# # # # # asyncio.run(test())
# # # # import asyncio
# # # # from decimal import Decimal
# # # # from dotenv import load_dotenv
# # # # from app.adapters.ollama_adapter import OllamaAdapter

# # # # load_dotenv(".env", override=True)

# # # # async def test():
# # # #     result = await OllamaAdapter().dispatch(
# # # #         prompt="Reply with exactly: Ollama adapter works",
# # # #         model_name="qwen2.5:3b",
# # # #         cost_per_input_token=Decimal("0.0000001"),
# # # #         cost_per_output_token=Decimal("0.0000004"),
# # # #     )

# # # #     print("Status:", result.status)
# # # #     print("Response:", result.response_text)
# # # #     print("Input tokens:", result.input_token_count)
# # # #     print("Output tokens:", result.output_token_count)
# # # #     print("Latency:", result.latency_ms, "ms")
# # # #     print("Estimated cost:", result.estimated_cost)
# # # #     print("Error:", result.error_message)

# # # # asyncio.run(test())
# # # import asyncio
# # # from decimal import Decimal
# # # from dotenv import load_dotenv
# # # from app.adapters.groq_adapter import GroqAdapter

# # # load_dotenv(".env", override=True)

# # # async def test():
# # #     result = await GroqAdapter().dispatch(
# # #         prompt="Reply with exactly: Groq adapter works",
# # #         model_name="openai/gpt-oss-20b",
# # #         cost_per_input_token=Decimal("0.0000001"),
# # #         cost_per_output_token=Decimal("0.0000004"),
# # #     )

# # #     print("Status:", result.status)
# # #     print("Response:", result.response_text)
# # #     print("Input tokens:", result.input_token_count)
# # #     print("Output tokens:", result.output_token_count)
# # #     print("Latency:", result.latency_ms, "ms")
# # #     print("Estimated cost:", result.estimated_cost)
# # #     print("Error:", result.error_message)

# # # # asyncio.run(test())
# # # from app.intelligence.complexity import tokenise, count_tokens

# # # text = "Elon musk is the richest man in the world. He is the founder of SpaceX and Tesla."

# # # print("Tokens:", tokenise(text))
# # # print("Token count:", count_tokens(text))
# # from app.intelligence.classifier import classify_prompt

# # tests = [
# #     "What is 2 + 2?",
# #     # "First explain the issue, then compare the options, and finally recommend one.",
# #     "Provide a diagnosis, discuss the pathology, and explain the prognosis.",
# # ]

# # for prompt in tests:
# #     result = classify_prompt(prompt)
# #     print("\nPrompt:", prompt)
# #     print("Class:", result.complexity_class)
# #     print("Explanation:", result.explanation)
# from sqlalchemy import select
# from app.database.connection import SessionLocal
# from app.models.model import Model
# from app.models.request import Request
# from app.routing.router import route_request

# db = SessionLocal()

# try:
#     grok = db.scalar(
#     select(Model).where(Model.identifier == "grok")
# )

#     if grok:
#         grok.enabled = False
#         db.commit()
#         print("Disabled:", grok.identifier)

#     models = list(db.scalars(select(Model)).all())
#     requests = list(db.scalars(select(Request)).all())

#     print("Registered models:")
#     for model in models:
#         print(model.id, model.identifier, model.enabled)

#     if not requests:
#         print("No request exists.")
#     elif not models:
#         print("No models are registered.")
#     else:
#         result = route_request(
#             request_id=requests[0].id,
#             complexity="complex",
#             db=db,
#         )
#         print("Selected model:", result.model_id)
#         print("Estimated cost:", result.estimated_cost)
#         print("Explanation:", result.explanation)
# finally:
#     db.close()
import os
from sqlalchemy import select
from app.database.connection import SessionLocal
from app.models.model import Model
from app.models.request import Request
from app.routing.router import route_request

db = SessionLocal()

try:
    models = list(
        db.scalars(
            select(Model).where(Model.enabled.is_(True))
        ).all()
    )
    request = db.scalar(select(Request).order_by(Request.id.desc()))

    print("Enabled models:")
    for model in models:
        print(model.identifier, model.provider_name)

    if not models or request is None:
        print("You need at least one enabled model and one request.")
    else:
        for policy in ["cost_optimised", "quality_optimised"]:
            os.environ["ROUTING_POLICY"] = policy

            result = route_request(
                request_id=request.id,
                complexity="complex",
                db=db,
            )

            print(f"\nPolicy: {policy}")
            print("Selected:", result.model_id)
            print("Estimated cost:", result.estimated_cost)
            print("Explanation:", result.explanation)

        baseline = models[0]
        os.environ["ROUTING_POLICY"] = "baseline"
        os.environ["BASELINE_MODEL_ID"] = baseline.identifier

        result = route_request(
            request_id=request.id,
            complexity="complex",
            db=db,
        )

        print("\nPolicy: baseline")
        print("Selected:", result.model_id)
        print("Expected:", baseline.identifier)
        print("Explanation:", result.explanation)

finally:
    db.close()