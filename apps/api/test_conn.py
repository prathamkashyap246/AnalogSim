import os
import sys
from sqlalchemy import create_engine, text


def check_and_create_database():
    # Force 127.0.0.1 instead of 'localhost' to bypass IPv6 (::1) translation issues
    base_url = os.environ["DATABASE_URL_ADMIN"]
    engine = create_engine(base_url, isolation_level="AUTOCOMMIT")

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = 'analogsim'")
            ).scalar()

            if not result:
                conn.execute(text("CREATE DATABASE analogsim"))
                print("SUCCESS: Created the 'analogsim' database!")
            else:
                print("INFO: 'analogsim' database already exists.")
    except Exception as e:
        print(f"ERROR connecting to PostgreSQL server: {e}")
        sys.exit(1)


def main():
    check_and_create_database()
    print("Database connection verified successfully. You can now run seed_data.py!")


if __name__ == "__main__":
    main()