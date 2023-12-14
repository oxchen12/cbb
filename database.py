import sqlite3
from sqlite3 import Error

DB_FILE = "CBB.sqlite"

# def create_connection():
#     """Create a database connection to the database."""
#     conn = None
#     try:
#         conn = sqlite3.connect(db_filename)
#     except Error as e:
#         print(e)
#         if conn:
#             conn.close()
#     return conn

def get_connection():
    """Get connection to the database. Creates the database if it does not exist already."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS""")