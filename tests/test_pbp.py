from pprint import pprint

import context
import re
import logging

from cbb.webscraper import Page
from test_utils import timeopmany, sqlp, reset_db, view_tables
from cbb import pbp, schedule, database


def test_db_examples(*select) -> None:
    def ex1(cid = 2):
        """List the total number of games played by each ACC team."""
        s = '''
        SELECT T.name as Name,
               count(DISTINCT G.gid) as `Games Played`
        FROM Games G JOIN Teams T ON G.home = T.tid OR G.away = T.tid
        WHERE T.cid = :cid
        GROUP BY T.tid
        ORDER BY `Games Played` DESC
        '''
        sqlp(s, {'cid': cid})

    def ex2(pid = 4433176):
        """Determine the number of 3 pointers made by RJ Davis."""
        s = f'''
        SELECT count(Plays.plyid) as 'Threes Made'
        FROM Plays JOIN Players
            ON Plays.plyr = Players.pid
        WHERE Plays.plyr = :pid
          AND Plays.type = "SHT"
          AND Plays.subtype = "3PJ"
          AND Plays.pts_scored > 0
        '''
        sqlp(s, {'pid': pid})

    def ex3(pid = 4712836):
        """Determine the number of blocks made by Seth Trimble."""
        s = f'''
        SELECT count(Plays.plyid) as Blocks
        FROM Plays JOIN Players
            ON Plays.plyr = Players.pid
        WHERE Plays.plyr = :pid
          AND Plays.type = "BLK"
        '''
        sqlp(s, {'pid': pid})

    def ex4():
        """List top 10 block leaders with at least 5 blocks in descending order."""
        s = f'''
        SELECT Players.fname || ' ' || Players.lname as Name, count(Plays.plyid) as Blocks
        FROM Plays JOIN Players
            ON Plays.plyr = Players.pid
        WHERE Plays.type = "BLK"
        GROUP BY Plays.plyr
        HAVING Blocks >= 5
        ORDER BY Blocks DESC
        LIMIT 10
        '''
        sqlp(s)

    def ex5(tid = 153):
        """List UNC assists leaders in descending order."""
        s = f'''
        SELECT Players.fname || ' ' || Players.lname as Name, count(Plays.plyid) as Assists
        FROM Plays JOIN (Players JOIN
                        (PlayerSeasons JOIN Rosters
            ON PlayerSeasons.rid = Rosters.rid)
            ON Players.pid = PlayerSeasons.pid)
            ON Plays.plyr_ast = Players.pid
        WHERE Rosters.tid = :tid
          AND Plays.type = "SHT"
        GROUP BY Players.pid
        ORDER BY Assists DESC
        '''
        sqlp(s, {'tid': tid})

    def ex6(pid = 4433176):
        """Determine the number of RJ Davis's shots that were blocked."""
        s = f'''
        SELECT count(*) as 'Shots Blocked'
        FROM Plays 
        WHERE plyr=:plyr 
        AND (gid, plyid) IN (SELECT P.gid, P.rel_ply 
                             FROM Plays P 
                             WHERE P.type = 'BLK')'''
        sqlp(s, {'plyr': pid})

    def ex7(pid = 4433176):
        """Determine the total points scored by RJ Davis."""
        s = f'''
        SELECT sum(pts_scored) as 'Points Scored'
        FROM Plays
        WHERE plyr=:plyr'''
        sqlp(s, {'plyr': pid})

    def ex8():
        """List the top 20 FT% leaders with at least 50 attempts."""
        s = '''
        WITH
            made AS (SELECT P.plyr, PL.fname, PL.lname, count(*) as n FROM Plays P JOIN Players PL ON P.plyr=PL.pid WHERE P.pts_scored=1 GROUP BY P.plyr),
            attempted AS (SELECT P.plyr, count(*) as n FROM Plays P JOIN Players PL ON P.plyr=PL.pid WHERE P.subtype='1FT' GROUP BY P.plyr)
        SELECT M.fname || ' ' || M.lname as `Name`, 
               ROUND(CAST(M.n AS FLOAT) / CAST(A.n AS FLOAT), 3) as `FT%` 
        FROM made M 
            JOIN attempted A ON M.plyr = A.plyr
        WHERE A.n >= 50
        ORDER BY `FT%` DESC
        LIMIT 20'''
        sqlp(s)

    def ex9():
        """List the 10 furthest made shots."""
        s = '''
        WITH
            Y AS (SELECT Y.*,
                             CAST((Y.x_coord - 25) AS FLOAT) as x_norm, 
                             CAST(Y.y_coord AS FLOAT) as y_norm
                     FROM Plays Y WHERE Y.x_coord IS NOT NULL)
        SELECT T.name as Team,
               P.fname || ' ' || P.lname as Name, 
               O.name as Against,
               G.date as Date,
               Y.period as Period, 
               Y.time_min || ':' || (CASE WHEN Y.time_sec < 10 THEN '0' ELSE '' END) || Y.time_sec as Clock, 
               ROUND(sqrt(x_norm * x_norm + y_norm * y_norm), 2) as Distance--, Y.x_coord, Y.y_coord
        FROM Y JOIN Players P ON Y.plyr = P.pid
               JOIN Games G ON Y.gid = G.gid
               JOIN Teams T ON Y.tid = T.tid
               JOIN Teams O ON (O.tid = G.home OR O.tid = G.away) AND O.tid != Y.tid
        WHERE Y.pts_scored > 0
        ORDER BY Distance DESC
        LIMIT 10'''
        sqlp(s)


    def ex10():
        """List the 10 shortest players."""
        s = '''
        SELECT P.fname || ' ' || P.lname as Name,
               P.htft || "'" || P.htin || '"' as Height
        FROM Players P
        WHERE Height IS NOT NULL
        ORDER BY P.htft ASC,
                 P.htin ASC
        LIMIT 10'''
        sqlp(s)

    def ex11(tid = 153):
        """Determine the largest lead and deficit for UNC in each game of the 2023-2024 season."""
        s = '''
        WITH
            D AS (SELECT G.gid, G.date,
                         CASE
                            WHEN G.home = :tid THEN G.away
                            ELSE G.home
                         END as opp,
                         CASE 
                            WHEN G.home = :tid THEN P.home_score - P.away_score 
                            ELSE P.away_score - P.home_score 
                         END as diff
                  FROM Games G JOIN Plays P ON G.gid = P.gid
                  WHERE (G.home = :tid OR G.away = :tid)
                        AND G.season = 2024)
        SELECT T.name as Opponent,
               D.date as Date,
               MAX(D.diff) as Lead,
               MIN(D.diff) as Deficit
        FROM D JOIN Teams T ON D.opp = T.tid
        GROUP BY D.gid
        ORDER BY Date
        '''
        sqlp(s, {'tid': tid})

    def ex12():
        """List the top 10 players in rebounding their own shots."""
        s = '''
        SELECT P.fname || ' ' || P.lname as Name,
               COUNT(L1.plyid) as `Own-Shot Rebounds`
        FROM Plays L1 LEFT JOIN Players P ON P.pid = L1.plyr
                     JOIN Plays L2 ON L1.rel_ply = L2.plyid 
                                      AND L1.gid = L2.gid
        WHERE L1.type = 'REB'
              AND L2.plyr = L1.plyr
        GROUP BY P.pid
        ORDER BY `Own-Shot Rebounds` DESC
        LIMIT 10'''
        sqlp(s)

    tests = (
        ex1,
        ex2,
        ex3,
        ex4,
        ex5,
        ex6,
        ex7,
        ex8,
        ex9,
        ex10,
        ex11,
        ex12
    )
    if select:
        tests = (t for i, t in enumerate(tests) if i+1 in select)

    for t in tests:
        print(f'=== {t.__name__}: {t.__doc__} ===')
        t()


def test_parse_team(tid: int, season: int, level=0, assume_gid_from_pbp: bool = False):
    timeopmany(pbp.parse_pbp, 'parse_pbp', [(s, assume_gid_from_pbp) for s in schedule.get_schedule_gids(tid, season)],
               level=level, extras=True)


def test_parse_conference(cid: int, season: int, assume_gid_from_pbp: bool = False):
    url = f'https://www.espn.com/mens-college-basketball/standings/_/group/{cid}'
    conf = Page(url)
    tids = {re.search(r'team/_/id/(\d+)', str(t))[1] for t in
            conf.soup.select('tbody[class="Table__TBODY"] tr a[class="AnchorLink"]')}

    res = timeopmany(test_parse_team, display='parse_team', args_gen=[(tid, season, 1, True) for tid in tids],
                     extras=True)

    y = [f'{t:.2f}' for t in res['individual']]
    print(f'Individual times: {y}')


def main():
    # reset_db()
    # test_parse_conference(2, 2024, assume_gid_from_pbp=True)
    # test_parse_team(153, 2024)
    test_db_examples()


if __name__ == '__main__':
    main()
