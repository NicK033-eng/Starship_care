
import sys
import os
from sqlalchemy import create_engine, inspect

# Add project root to path
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.database import DATABASE_URL

def inspect_database():
    """Connects to the database and inspects its schema."""
    try:
        engine = create_engine(DATABASE_URL)
        inspector = inspect(engine)

        print("--- Database Inspector ---")
        
        # 1. List all tables
        tables = inspector.get_table_names()
        print(f"Tables found: {tables}")

        # 2. Check for 'leads' table
        if "leads" in tables:
            print("\nTable 'leads' found.")
            
            # 3. Print 'leads' table schema
            print("\nSchema for 'leads' table:")
            columns = inspector.get_columns("leads")
            for column in columns:
                print(f"  - {column['name']} ({column['type']})")
        else:
            print("\nTable 'leads' NOT found.")
            
        print("\n--- Inspection Complete ---")

    except Exception as e:
        print(f"An error occurred during database inspection: {e}")

if __name__ == "__main__":
    inspect_database()
