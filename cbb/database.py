import sqlite3
import os
import logging
from typing import Optional
from contextlib import contextmanager

SCHEMA_FILE = 'cbb.sql'     # contains the schema initialization code
DB_FILE = 'CBB.db'          # database file

_conn: Optional[sqlite3.Connection] = None                # singular global database connection

def delete_db(force = False) -> bool:
    """Delete the database file."""
    if _conn is not None:
        _conn.rollback()
    if not os.path.exists(DB_FILE):
        print('Database file does not exist.')
        return False
    ans = 'y' if force else input('Are you sure you want to delete the existing database? [y/N]').lower()[0]
    res = ans == 'y'
    if res:
        try:
            print(f'Deleting {DB_FILE}...', end='')
            os.remove(DB_FILE)
            print('deleted.')
        except OSError as e:
            print(f'Something went wrong while deleting the DB file: {e}')
            return False
    else:
        print('Canceled deleting database.')
    return res

def init_schema() -> bool:
    """Initialize the schema to the appropriate `db` file."""
    with (
        open(SCHEMA_FILE, 'r') as fp,
        conn() as c
    ):
        if c is None:
            logging.warning('connection could not be established')
            return False
        cursor = c.cursor()
        cursor.executescript(fp.read())
        c.commit()
    return True

@contextmanager
def conn(path: str = DB_FILE):
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(path)
    try:
        yield _conn
    except Exception as e:
        logging.critical('error encountered, rolling back')
        _conn.rollback()
        raise e
    else:
        _conn.commit()
    # for now, we won't worry about explicitly closing the connection
    # (see https://stackoverflow.com/questions/9561832/what-if-i-dont-close-the-database-connection-in-python-sqlite)
    # finally:
    #     _conn.close()

def with_cursor(func):
    def _with_cursor(*args, **kwargs):
        with conn() as c:
            res = func(c.cursor(), *args, **kwargs)
        return res
    return _with_cursor
