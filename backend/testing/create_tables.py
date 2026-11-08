"""Create any MISSING NeuroRoute tables.

This script only creates tables that do not exist yet. It never alters an
existing table, so it does NOT add the new columns to the live `requests`
table (that is done by the controlled migration in Task 1.4a).

Run from the `backend/` directory:

    python -m testing.create_tables
"""

from app.database.connection import Base, engine
from app.models.request import Request
from app.models.model import Model
from app.models.routing_decision import RoutingDecision
from app.models.execution import Execution
from app.models.evaluation import Evaluation
from app.models.feedback import Feedback

Base.metadata.create_all(bind=engine)

print("Tables created successfully!")
