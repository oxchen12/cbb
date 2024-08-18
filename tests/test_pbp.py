from test_utils import timeopmany, sqlp, reset_db
from cbb import pbp, schedule, database

def test_db_examples(select=None):
    def ex1():
        """List the number of players that played for each team in descending order."""
        s = '''
        SELECT Teams.name, count(Players.pid) as c
        FROM Players JOIN (PlayerSeasons JOIN 
                          (Rosters JOIN Teams 
                           ON Rosters.tid = Teams.tid) 
                           ON PlayerSeasons.rid = Rosters.rid) 
                           ON PlayerSeasons.pid = Players.pid
        GROUP BY Teams.name
        ORDER BY c DESC
        '''
        sqlp(s)

    def ex2():
        """Determine the number of 3 pointers made by RJ Davis."""
        pid = 4433176  # pid for RJ Davis
        s = f'''
        SELECT count(Plays.plyid)
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
        pid = 4712836   # pid for Seth Trimble
        s = f'''
        SELECT count(Plays.plyid)
        FROM Plays JOIN Players
            ON Plays.plyr = Players.pid
        WHERE Plays.plyr = :pid
          AND Plays.type = "BLK"
        '''
        sqlp(s, {'pid': pid})

    def ex4():
        """List block leaders with at least 5 blocks in descending order."""
        s = f'''
        SELECT Players.lname, count(Plays.plyid) as c
        FROM Plays JOIN Players
            ON Plays.plyr = Players.pid
        WHERE Plays.type = "BLK"
        GROUP BY Plays.plyr
        HAVING c >= 5
        ORDER BY c DESC
        '''
        sqlp(s)

    def ex5():
        """List UNC assists leaders in descending order."""
        tid = 153  # UNC
        s = f'''
        SELECT Players.lname, count(Plays.plyid) as c
        FROM Plays JOIN (Players JOIN
                        (PlayerSeasons JOIN Rosters
            ON PlayerSeasons.rid = Rosters.rid)
            ON Players.pid = PlayerSeasons.pid)
            ON Plays.plyr_ast = Players.pid
        WHERE Rosters.tid = :tid
          AND Plays.type = "SHT"
        GROUP BY Players.pid
        ORDER BY c DESC
        '''
        sqlp(s, {'tid': tid})

    tests = [ex1, ex2, ex3, ex4, ex5]
    if select:
        tests = [t for i, t in enumerate(tests) if i in select]

    for t in tests:
        print(f'=== {t.__name__}: {t.__doc__} ===')
        t()


def main():
    # reset_db()
    # timeopmany(pbp.parse_pbp, 'parse_pbp', schedule.get_schedule_gids(153, 2024))
    test_db_examples()


if __name__ == '__main__':
    main()
