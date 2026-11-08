from app.database.connection import SessionLocal
from app.models.request import Request

# Create a database session
db = SessionLocal()

try:
    # CREATE: Insert a new request
    new_request = Request(
        prompt="Explain how ML works",
        status="completed"
    )

    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    print("Request inserted successfully!")
    print("Generated ID:", new_request.id)

    # READ: Retrieve all requests
    requests = db.query(Request).all()

    print("\nAll stored requests:")

    for request in requests:
        print(
            f"ID: {request.id} | "
            f"Prompt: {request.prompt} | "
            f"Status: {request.status}"
        )

finally:
    db.close()