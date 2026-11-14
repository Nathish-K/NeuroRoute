# # # # # # # # # import asyncio
# # # # # # # # # from decimal import Decimal
# # # # # # # # # from app.adapters.gemini_adapter import GeminiAdapter
# # # # # # # # # from dotenv import load_dotenv

# # # # # # # # # load_dotenv()

# # # # # # # # # async def test():
# # # # # # # # #     adapter = GeminiAdapter()

# # # # # # # # #     result = await adapter.dispatch(
# # # # # # # # #         prompt="Reply with exactly: Gemini adapter works",
# # # # # # # # #         model_name="gemini-3.1-flash-lite",
# # # # # # # # #         cost_per_input_token=Decimal("0.0000001"),
# # # # # # # # #         cost_per_output_token=Decimal("0.0000004"),
# # # # # # # # #     )

# # # # # # # # #     print("Status:", result.status)
# # # # # # # # #     print("Response:", result.response_text)
# # # # # # # # #     print("Input tokens:", result.input_token_count)
# # # # # # # # #     print("Output tokens:", result.output_token_count)
# # # # # # # # #     print("Latency:", result.latency_ms, "ms")
# # # # # # # # #     print("Estimated cost:", result.estimated_cost)
# # # # # # # # #     print("Error:", result.error_message)

# # # # # # # # # asyncio.run(test())
# # # # # # # # import asyncio
# # # # # # # # from decimal import Decimal
# # # # # # # # from dotenv import load_dotenv
# # # # # # # # from app.adapters.ollama_adapter import OllamaAdapter

# # # # # # # # load_dotenv(".env", override=True)

# # # # # # # # async def test():
# # # # # # # #     result = await OllamaAdapter().dispatch(
# # # # # # # #         prompt="Reply with exactly: Ollama adapter works",
# # # # # # # #         model_name="qwen2.5:3b",
# # # # # # # #         cost_per_input_token=Decimal("0.0000001"),
# # # # # # # #         cost_per_output_token=Decimal("0.0000004"),
# # # # # # # #     )

# # # # # # # #     print("Status:", result.status)
# # # # # # # #     print("Response:", result.response_text)
# # # # # # # #     print("Input tokens:", result.input_token_count)
# # # # # # # #     print("Output tokens:", result.output_token_count)
# # # # # # # #     print("Latency:", result.latency_ms, "ms")
# # # # # # # #     print("Estimated cost:", result.estimated_cost)
# # # # # # # #     print("Error:", result.error_message)

# # # # # # # # asyncio.run(test())
# # # # # # # import asyncio
# # # # # # # from decimal import Decimal
# # # # # # # from dotenv import load_dotenv
# # # # # # # from app.adapters.groq_adapter import GroqAdapter

# # # # # # # load_dotenv(".env", override=True)

# # # # # # # async def test():
# # # # # # #     result = await GroqAdapter().dispatch(
# # # # # # #         prompt="Reply with exactly: Groq adapter works",
# # # # # # #         model_name="openai/gpt-oss-20b",
# # # # # # #         cost_per_input_token=Decimal("0.0000001"),
# # # # # # #         cost_per_output_token=Decimal("0.0000004"),
# # # # # # #     )

# # # # # # #     print("Status:", result.status)
# # # # # # #     print("Response:", result.response_text)
# # # # # # #     print("Input tokens:", result.input_token_count)
# # # # # # #     print("Output tokens:", result.output_token_count)
# # # # # # #     print("Latency:", result.latency_ms, "ms")
# # # # # # #     print("Estimated cost:", result.estimated_cost)
# # # # # # #     print("Error:", result.error_message)

# # # # # # # # asyncio.run(test())
# # # # # # # from app.intelligence.complexity import tokenise, count_tokens

# # # # # # # text = "Elon musk is the richest man in the world. He is the founder of SpaceX and Tesla."

# # # # # # # print("Tokens:", tokenise(text))
# # # # # # # print("Token count:", count_tokens(text))
# # # # # # from app.intelligence.classifier import classify_prompt

# # # # # # tests = [
# # # # # #     "What is 2 + 2?",
# # # # # #     # "First explain the issue, then compare the options, and finally recommend one.",
# # # # # #     "Provide a diagnosis, discuss the pathology, and explain the prognosis.",
# # # # # # ]

# # # # # # for prompt in tests:
# # # # # #     result = classify_prompt(prompt)
# # # # # #     print("\nPrompt:", prompt)
# # # # # #     print("Class:", result.complexity_class)
# # # # # #     print("Explanation:", result.explanation)
# # # # # from sqlalchemy import select
# # # # # from app.database.connection import SessionLocal
# # # # # from app.models.model import Model
# # # # # from app.models.request import Request
# # # # # from app.routing.router import route_request

# # # # # db = SessionLocal()

# # # # # try:
# # # # #     grok = db.scalar(
# # # # #     select(Model).where(Model.identifier == "grok")
# # # # # )

# # # # #     if grok:
# # # # #         grok.enabled = False
# # # # #         db.commit()
# # # # #         print("Disabled:", grok.identifier)

# # # # #     models = list(db.scalars(select(Model)).all())
# # # # #     requests = list(db.scalars(select(Request)).all())

# # # # #     print("Registered models:")
# # # # #     for model in models:
# # # # #         print(model.id, model.identifier, model.enabled)

# # # # #     if not requests:
# # # # #         print("No request exists.")
# # # # #     elif not models:
# # # # #         print("No models are registered.")
# # # # #     else:
# # # # #         result = route_request(
# # # # #             request_id=requests[0].id,
# # # # #             complexity="complex",
# # # # #             db=db,
# # # # #         )
# # # # #         print("Selected model:", result.model_id)
# # # # #         print("Estimated cost:", result.estimated_cost)
# # # # #         print("Explanation:", result.explanation)
# # # # # finally:
# # # # #     db.close()
# # # # import os
# # # # from sqlalchemy import select
# # # # from app.database.connection import SessionLocal
# # # # from app.models.model import Model
# # # # from app.models.request import Request
# # # # from app.routing.router import route_request

# # # # db = SessionLocal()

# # # # try:
# # # #     models = list(
# # # #         db.scalars(
# # # #             select(Model).where(Model.enabled.is_(True))
# # # #         ).all()
# # # #     )
# # # #     request = db.scalar(select(Request).order_by(Request.id.desc()))

# # # #     print("Enabled models:")
# # # #     for model in models:
# # # #         print(model.identifier, model.provider_name)

# # # #     if not models or request is None:
# # # #         print("You need at least one enabled model and one request.")
# # # #     else:
# # # #         for policy in ["cost_optimised", "quality_optimised"]:
# # # #             os.environ["ROUTING_POLICY"] = policy

# # # #             result = route_request(
# # # #                 request_id=request.id,
# # # #                 complexity="complex",
# # # #                 db=db,
# # # #             )

# # # #             print(f"\nPolicy: {policy}")
# # # #             print("Selected:", result.model_id)
# # # #             print("Estimated cost:", result.estimated_cost)
# # # #             print("Explanation:", result.explanation)

# # # #         baseline = models[0]
# # # #         os.environ["ROUTING_POLICY"] = "baseline"
# # # #         os.environ["BASELINE_MODEL_ID"] = baseline.identifier

# # # #         result = route_request(
# # # #             request_id=request.id,
# # # #             complexity="complex",
# # # #             db=db,
# # # #         )

# # # #         print("\nPolicy: baseline")
# # # #         print("Selected:", result.model_id)
# # # #         print("Expected:", baseline.identifier)
# # # #         print("Explanation:", result.explanation)

# # # # finally:
# # # #     db.close()

# # # import asyncio
# # # from decimal import Decimal

# # # from sqlalchemy import create_engine
# # # from sqlalchemy.orm import Session
# # # from sqlalchemy.pool import StaticPool

# # # from app import models as _models
# # # from app.database.connection import Base
# # # from app.adapters.engine import execute_request
# # # from app.models.model import Model
# # # from app.models.request import Request
# # # from app.models.routing_decision import RoutingDecision


# # # async def main():
# # #     engine = create_engine(
# # #         "sqlite://",
# # #         connect_args={"check_same_thread": False},
# # #         poolclass=StaticPool,
# # #     )
# # #     Base.metadata.create_all(engine)

# # #     with Session(engine) as db:
# # #         request = Request(prompt="Explain routing in one sentence", status="pending")
# # #         db.add(request)
# # #         db.flush()

# # #         model = Model(
# # #             identifier="manual-ollama",
# # #             provider_name="ollama",
# # #             model_name="qwen2.5:3b",
# # #             max_context_length=8192,
# # #             cost_per_input_token=Decimal("0.0000000000"),
# # #             cost_per_output_token=Decimal("0.0000000000"),
# # #             capability_tier=2,
# # #             enabled=True,
# # #         )
# # #         db.add(model)
# # #         db.flush()

# # #         decision = RoutingDecision(
# # #             request_id=request.id,
# # #             model_id=model.id,
# # #             policy="baseline",
# # #             complexity_class="simple",
# # #             estimated_cost=Decimal("0"),
# # #             explanation="Manual Phase 6.1 verification",
# # #         )
# # #         db.add(decision)
# # #         db.commit()

# # #         execution = await execute_request(
# # #             routing_decision_id=decision.id,
# # #             prompt=request.prompt,
# # #             model=model,
# # #             db=db,
# # #         )

# # #         print("Status:", execution.status)
# # #         print("Response:", execution.response_text)
# # #         print("Latency:", execution.latency_ms)
# # #         print("Error:", execution.error_message)

# # #         assert execution.status == "completed"
# # #         assert execution.latency_ms is not None
# # #         assert execution.latency_ms >= 0
# # #         print("6.1 Ollama checkpoint: PASS")


# # # asyncio.run(main())

# # from datetime import datetime
# # from decimal import Decimal

# # from app import models as _models
# # from app.models.execution import Execution
# # from app.schemas.executions import ExecutionResponse

# # execution = Execution(
# #     id=1,
# #     routing_decision_id=10,
# #     response_text="Manual schema verification",
# #     input_token_count=5,
# #     output_token_count=12,
# #     latency_ms=250,
# #     estimated_cost=Decimal("0.0000010000"),
# #     status="completed",
# #     error_message=None,
# #     is_escalated=False,
# #     created_at=datetime.now(),
# # )

# # response = ExecutionResponse.model_validate(execution)

# # print(response)
# # print("Status:", response.status)
# # print("Cost:", response.estimated_cost)
# # print("From ORM:", response.model_config["from_attributes"])

# # assert response.id == 1
# # assert response.routing_decision_id == 10
# # assert response.status == "completed"
# # assert response.estimated_cost == Decimal("0.0000010000")
# # assert response.model_config["from_attributes"] is True

# # print("6.2 schema verification: PASS")

# from app.evaluation.evaluator import evaluate_execution
# from app.models.execution import Execution
# from app.models.request import Request
# from app.models.routing_decision import RoutingDecision

# request = Request(
#     prompt="Explain routing because it selects a model"
# )
# decision = RoutingDecision(request=request)

# completed = Execution(
#     routing_decision=decision,
#     response_text=(
#         "Routing selects a model because it matches the prompt. "
#         "In summary, this reduces cost."
#     ),
#     status="completed",
# )

# result = evaluate_execution(completed, threshold=0.70)

# print("Quality score:", result.quality_score)
# print("Confidence:", result.confidence)
# print("Escalation:", result.escalation_flag)

# assert 0.0 <= result.quality_score <= 1.0
# assert 0.0 <= result.confidence <= 1.0
# assert result.escalation_flag == (result.confidence < 0.70)

# failed = Execution(
#     routing_decision=decision,
#     response_text="",
#     status="failed",
# )

# failed_result = evaluate_execution(failed, threshold=0.70)

# print("Failed quality:", failed_result.quality_score)
# print("Failed confidence:", failed_result.confidence)
# print("Failed escalation:", failed_result.escalation_flag)

# assert failed_result.quality_score == 0.0
# assert failed_result.confidence == 0.0
# assert failed_result.escalation_flag is True

# print("7.1 manual verification: PASS")

import asyncio
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import models as _models
from app.database.connection import Base
from app.evaluation.escalation import handle_escalation
from app.models.evaluation import Evaluation
from app.models.execution import Execution
from app.models.model import Model
from app.models.request import Request
from app.models.routing_decision import RoutingDecision


async def fake_execute_request(routing_decision_id, prompt, model, db):
    execution = Execution(
        routing_decision_id=routing_decision_id,
        response_text=(
            "The stronger model provides a detailed answer because "
            "it matches the routing prompt. In summary, the result is improved."
        ),
        input_token_count=10,
        output_token_count=30,
        latency_ms=20,
        estimated_cost=Decimal("0.0001000000"),
        status="completed",
        is_escalated=False,
    )
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


async def main():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        request = Request(
            prompt="Explain routing and model selection",
            status="pending",
        )
        db.add(request)
        db.flush()

        basic = Model(
            identifier="basic-model",
            provider_name="ollama",
            model_name="qwen2.5:3b",
            max_context_length=4096,
            cost_per_input_token=Decimal("0"),
            cost_per_output_token=Decimal("0"),
            capability_tier=1,
            enabled=True,
        )
        stronger = Model(
            identifier="stronger-model",
            provider_name="ollama",
            model_name="qwen2.5:3b",
            max_context_length=8192,
            cost_per_input_token=Decimal("0"),
            cost_per_output_token=Decimal("0"),
            capability_tier=2,
            enabled=True,
        )
        db.add_all([basic, stronger])
        db.flush()

        decision = RoutingDecision(
            request_id=request.id,
            model_id=basic.id,
            policy="cost_optimised",
            complexity_class="moderate",
            estimated_cost=Decimal("0"),
            explanation="Initial routing",
        )
        db.add(decision)
        db.flush()

        original = Execution(
            routing_decision_id=decision.id,
            response_text="Short answer",
            input_token_count=5,
            output_token_count=2,
            latency_ms=10,
            estimated_cost=Decimal("0"),
            status="completed",
            is_escalated=False,
        )
        db.add(original)
        db.flush()

        evaluation = Evaluation(
            execution_id=original.id,
            quality_score=0.10,
            confidence=0.10,
            escalation_flag=True,
        )
        db.add(evaluation)
        db.commit()
        db.refresh(evaluation)

        with patch(
            "app.evaluation.escalation.execute_request",
            new=fake_execute_request,
        ):
            selected = await handle_escalation(request, evaluation, db)

        assert selected is not None
        assert selected.is_escalated is True
        assert selected.routing_decision.model.identifier == "stronger-model"

        executions = db.scalars(
            select(Execution).where(
                Execution.routing_decision_id == selected.routing_decision_id
            )
        ).all()
        assert len(executions) == 1

        evaluations = db.scalars(select(Evaluation)).all()
        assert len(evaluations) == 2

        print("Selected model:", selected.routing_decision.model.identifier)
        print("Selected quality:", evaluations[-1].quality_score)
        print("Execution escalated:", selected.is_escalated)
        print("7.2 escalation verification: PASS")


asyncio.run(main())
