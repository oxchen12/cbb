import re
import logging
import json
from typing import Union
from cbb.database import with_db_cursor
from cbb.webscraper import Page, GamePage

TYPE_CHART = (
    ('SHT', r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) (made|missed) (Three Point Jumper|Jumper|Layup|Dunk|Free Throw)\.(?: Assisted by ((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)\.)?"),
    ('REB', r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) (Offensive|Defensive|Deadball Team) Rebound\."),
    ('FL', r"(Technical )?Foul on ((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)\."),
    ('TOV', r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) Turnover\."),
    ('STL', r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) Steal\."),
    ('TO', r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) Timeout"),
    ('JMP', r"Jump Ball won by ((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)"),
    ('EOP', r"End of [A-Za-z0-9]+"),
    ('INV', r".*")
)
SHOT_TYPE_CHART = (
    ('3PJ', 'Three Point Jumper'),
    ('2PJ', 'Jumper'),
    ('2PL', 'Layup'),
    ('2PD', 'Dunk'),
    ('1FT', 'Free Throw')
)

REB_TYPE_CHART = (
    ('OFF', 'Offensive'),
    ('DEF', 'Defensive'),
    ('DBT', 'Deadball Team')
)

def get_game_tids(gid: Union[str, int]):
    """Retrieves the tid's for the away[0] and home[1] teams from the given game"""
    gid = str(gid)
    url = f'https://www.espn.com/mens-college-basketball/playbyplay/_/gameId/{gid}'
    page = Page(url)
    selector = page.soup.select('div[class="Gamestrip__TeamContainer flex items-center"]')
    out = [re.search(r'/mens-college-basketball/team/_/id/(\d+)', str(g))[1] for g in selector]
    if len(out) == 0:
        logging.warning('Team ids missing') # TODO: provide an alternative to encode with a new team id
    return out

@with_db_cursor
def fetch_team_data(cursor, tid: Union[str, int]):
    """Fetches team data and populates the database if it does not already exist"""
    tid = str(tid)
    cursor.execute('SELECT * FROM Teams WHERE tid="?" LIMIT 1', (tid, )) # `tid` should be unique within the database 
    res = cursor.fetchone()
    if not res:
        # populate the line by accessing the team page 
        url = f'https://www.espn.com/mens-college-basketball/team/schedule/_/id/{tid}'
        tp = Page(url)
        cursor.execute('SELECT * FROM Teams WHERE tid="?" LIMIT 1', (tid, )) # `tid` should be unique within the database 
        res = cursor.fetchone()
    return res

@with_db_cursor
def parse_plays_to_db(cursor, gid: Union[str, int]):
    """
    Parses plays from a given game and returns them as a list of lists that
    can be fed into an `sqlite3` `executemany` function call.
    """
    gid = str(gid)

    gp = GamePage(gid)
    pbp = GamePage(gid).plays
    pbp_m = re.search(r'\"pbp\":\s*\{\"playGrps\":(.+\]\]),\"tms\".*\}', str(pbp.soup), flags=re.DOTALL)
    pbp_j = json.loads(pbp_m[1].replace('\\', ''))

    a_tid, h_tid = get_game_tids(gid)
    a_data = fetch_team_data(cursor, a_tid)
    h_data = fetch_team_data(cursor, h_tid)

    periods = []
    for i, pd in enumerate(pbp_j):
        pdn = i+1 # period number
        pdl = []
        for play in pd:
            # these fields are not always present
            subtype = None
            pts_scored = None
            plyr = None
            plyr_ast = None

            # these fields are provided directly
            time_min, time_sec = play['clock']['displayValue'].split(':')
            period = play['period']['number']
            away_score = play['awayScore']
            home_score = play['homeScore']
            desc = play['text']
            # gid_ = gid 
            plid = play['id'].removeprefix(str(gid))

            tid = None
            if 'homeAway' in play:
                tid = a_tid if play['homeAway'] == 'away' else h_tid

            # remaining fields must be parsed from play description
            for t, r in TYPE_CHART:
                m = re.search(r, play['text'])
                if m is None:
                    continue
                g = m.groups()
                type_ = t
                match type_:
                    case 'SHT':
                        # find/make pid of player on `team` roster
                        # name stored in g[0]
                        cursor.execute('SELECT pid FROM Players WHERE name = "?" LIMIT 1', g[0])
                        plyr = cursor.fetchone()

                        # encode subtype
                        subtype = g[2]

                        # determine point value (make/miss)
                        pts_scored = 0 if g[1] == 'miss' else int(subtype[0])

                        # find/make pid of assister on `team` roster
                        cursor.execute('SELECT pid FROM Players WHERE name = "?" LIMIT 1', g[0])
                        plyr_ast = cursor.fetchone()

                    case 'REB':
                        # ('REB', r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) (Offensive|Defensive|Deadball Team) Rebound\."),
                        # determine if team or personal rebound


                        # find/make pid of player on `team` roster if personal

                        # encode subtype
                        pass
                    case 'FL' | 'TOV':
                        pass
                    
                    case 'STL':
                        pass

                    case 'TO' | 'JMP':
                        pass
                break
            
            pdl.append((plid, gid, tid, period, time_min, time_sec, type_, subtype, away_score, home_score, pts_scored, desc, plyr, plyr_ast))
        periods.append(pdl)
    