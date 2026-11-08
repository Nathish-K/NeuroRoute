from sqlalchemy import text
from app.database.connection import engine

try:
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT DATABASE(), VERSION()")
        )

        database, version = result.fetchone()

        print("Database connected successfully!")
        print("Database:", database)
        print("MySQL Version:", version)

except Exception as error:
    print("Database connection failed!")
    print(error)