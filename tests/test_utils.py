import context
import time
from cbb import database
from pprint import pprint


def timeop(func, display=None, *args, **kwargs):
    if display is None:
        display = func.__name__

    running = f'Running {display}'
    if args or kwargs:
        running += ' with'
        if args:
            running += f' {args=}'
            if kwargs:
                running += ' and'
        if kwargs:
            running += f' {kwargs=}'
    running += '...'

    print(running, end='')

    start = time.perf_counter()
    res = func(*args, **kwargs)
    dur = time.perf_counter() - start

    print(f'returned {res=} in {dur:.2f} seconds')


def timeopmany(func, display=None, args_gen=None):
    if args_gen is None:
        return

    print(f'Running {display} {len(args_gen)} times... {{')

    count = 0
    start = time.perf_counter()
    for arg in args_gen:
        print(f'\t[{count}]  \t', end='')
        timeop(func, display, arg)
        count += 1
    dur = time.perf_counter() - start

    print(f'}} Finished {len(args_gen)} executions in {dur:.2f} seconds')


@database.with_cursor
def view_tables(cursor, *tables):
    for t in tables:
        res = sql(f'SELECT * FROM {t}')
        print(f'Results for fetching {t}: {res}')


@database.with_cursor
def sql(cursor, sql_exp: str, sql_params=None):
    if sql_params is None:
        sql_params = tuple()
    res = cursor.execute(sql_exp, sql_params).fetchall()
    if len(res) == 1:
        res = res[0]
    if len(res) == 1:
        res = res[0]
    return res


def sqlp(sql_exp: str, sql_params=None):
    pprint(sql(sql_exp, sql_params))


def reset_db():
    database.delete_db(force=True)
    assert (database.init_schema())
