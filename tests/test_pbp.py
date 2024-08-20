import context
import re
import logging

from cbb.webscraper import Page
from test_utils import timeopmany, sqlp, reset_db, sql
from cbb import pbp, schedule, database


def test_db_examples(select=None):
    def ex1():
        """List the number of players that played for each team in descending order."""
        s = '''
        SELECT Teams.name, count(Players.pid) as num_players
        FROM Players JOIN (PlayerSeasons JOIN 
                          (Rosters JOIN Teams 
                           ON Rosters.tid = Teams.tid) 
                           ON PlayerSeasons.rid = Rosters.rid) 
                           ON PlayerSeasons.pid = Players.pid
        GROUP BY Teams.name
        ORDER BY num_players DESC
        '''
        sqlp(s)

    def ex2():
        """Determine the number of 3 pointers made by RJ Davis."""
        pid = 4433176  # pid for RJ Davis
        s = f'''
        SELECT count(Plays.plyid) as threes_made
        FROM Plays JOIN Players
            ON Plays.plyr = Players.pid
        WHERE Plays.plyr = :pid
          AND Plays.type = "SHT"
          AND Plays.subtype = "3PJ"
          AND Plays.pts_scored > 0
        '''
        sqlp(s, {'pid': pid})

    def ex3():
        """Determine the number of blocks made by Seth Trimble."""
        pid = 4712836  # pid for Seth Trimble
        s = f'''
        SELECT count(Plays.plyid) as blocks
        FROM Plays JOIN Players
            ON Plays.plyr = Players.pid
        WHERE Plays.plyr = :pid
          AND Plays.type = "BLK"
        '''
        sqlp(s, {'pid': pid})

    def ex4():
        """List block leaders with at least 5 blocks in descending order."""
        s = f'''
        SELECT Players.lname, count(Plays.plyid) as blocks
        FROM Plays JOIN Players
            ON Plays.plyr = Players.pid
        WHERE Plays.type = "BLK"
        GROUP BY Plays.plyr
        HAVING blocks >= 5
        ORDER BY blocks DESC
        '''
        sqlp(s)

    def ex5():
        """List UNC assists leaders in descending order."""
        tid = 153  # UNC
        s = f'''
        SELECT Players.lname, count(Plays.plyid) as assists
        FROM Plays JOIN (Players JOIN
                        (PlayerSeasons JOIN Rosters
            ON PlayerSeasons.rid = Rosters.rid)
            ON Players.pid = PlayerSeasons.pid)
            ON Plays.plyr_ast = Players.pid
        WHERE Rosters.tid = :tid
          AND Plays.type = "SHT"
        GROUP BY Players.pid
        ORDER BY assists DESC
        '''
        sqlp(s, {'tid': tid})

    tests = [ex1, ex2, ex3, ex4, ex5]
    if select:
        tests = [t for i, t in enumerate(tests) if i in select]

    for t in tests:
        print(f'=== {t.__name__}: {t.__doc__} ===')
        t()


def test_parse_team(tid: int, season: int, level=0):
    timeopmany(pbp.parse_pbp, 'parse_pbp', [(s,) for s in schedule.get_schedule_gids(tid, season)], level=level, extras=True)


def test_parse_conference(cid: int, season: int):
    url = f'https://www.espn.com/mens-college-basketball/standings/_/group/{cid}'
    conf = Page(url)
    tids = {re.search(r'team/_/id/(\d+)', str(t))[1] for t in
            conf.soup.select('tbody[class="Table__TBODY"] tr a[class="AnchorLink"]')}

    res = timeopmany(test_parse_team, display='parse_team', args_gen=[(tid, season, 1) for tid in tids], extras=True)

    y = [f'{t:.2f}' for t in res['individual']]
    print(f'Individual times: {res["individual"]}')


def main():
    reset_db()
    test_parse_conference(2, 2024)
    # test_parse_team(153, 2024)


if __name__ == '__main__':
    main()
