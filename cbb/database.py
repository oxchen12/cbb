import sqlite3
import os
import logging
from contextlib import contextmanager

SCHEMA_FILE = 'cbb.sql'     # contains the schema initialization code
DB_FILE = 'CBB.db'          # database file
conn = None                 # singular global database connection

def init_schema() -> bool:
    """Initialize the schema to the appropriate `.db` file."""
    with (
        open(SCHEMA_FILE, 'r') as fp, 
        sqlite3.connect(DB_FILE) as conn 
    ):
        if conn is None:
            logging.warning('connection could not be established')
            return False
        cursor = conn.cursor()
        cursor.executescript(fp.read())
        conn.commit()
    return True

@contextmanager
def db_connect(path: str):
    global conn
    if conn is None:
        conn = sqlite3.connect(path)
    try:
        cursor = conn.cursor()
        yield cursor
    except Exception as e:
        logging.critical('error encountered, rolling back')
        conn.rollback()
        raise e
    else:
        conn.commit()
    finally:
        conn.close()

def with_db_cursor(func, path: str = DB_FILE):
    def _with_db_cursor(*args, **kwargs):
        with db_connect(path) as cursor:
            func(cursor, *args, **kwargs)
    return _with_db_cursor


    
if __name__ == '__main__':
    if not os.file.exists(DB_FILE):
        init_schema()