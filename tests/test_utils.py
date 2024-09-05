import context
import time
from cbb import database
from pprint import pprint
from prettytable import PrettyTable


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
    try:
        res = func(*args, **kwargs)
    except Exception as e:
        dur = time.perf_counter() - start
        print(f'exited with error {e=} in {dur:.2f} seconds')
    else:
        dur = time.perf_counter() - start
        print(f'returned {res=} in {dur:.2f} seconds')

    return dur


def timeopmany(func, display=None, args_gen=None, level=0, extras=False):
    if args_gen is None:
        return

    execs = len(list(args_gen))

    print(f'Running {display} {execs} times... {{')

    durs = []
    prefix = '\t' * (level + 1)
    start = time.perf_counter()
    for args in args_gen:
        print(f'{prefix}[{len(durs)}]  \t', end='')
        dur = timeop(func, display, *args)
        durs.append(dur)
    overall_dur = time.perf_counter() - start

    fin = f'}} Finished {execs} executions in {overall_dur:.2f} seconds'
    if extras:
        fin += f' (avg={sum(durs)/execs:.2f}, max={max(durs):.2f}, min={min(durs):.2f})'
    print(fin)
    return {'overall': overall_dur, 'individual': durs}


def view_tables(*tables):
    for t in tables:
        res = sql(f'SELECT * FROM {t}')
        print(f'Results for fetching {t}: {dict(res)}')


@database.with_cursor
def sql(cursor, sql_exp: str, sql_params=None):
    if sql_params is None:
        sql_params = tuple()
    res = cursor.execute(sql_exp, sql_params).fetchall()
    return res


def sqlp(sql_exp: str, sql_params=None):
    res = sql(sql_exp, sql_params)
    if res is None or len(res) == 0:
        print('No results')
        return
    table = PrettyTable()
    table.field_names = res[0].keys()
    for row in res:
        table.add_row(tuple(row))
    print(table)



def reset_db():
    database.delete_db(force=True)
    assert (database.init_schema())
