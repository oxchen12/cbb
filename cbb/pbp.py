import re
import logging
import json
from datetime import datetime
from collections import namedtuple
from typing import Union
from cbb.database import with_db_cursor
from cbb.webscraper import Page, GamePage

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
def fetch_cid_from_tid(cursor, tid: Union[str, int]):
    """Fetches cid from team id"""
    # this function assumes that the team is new and does not yet store its own `cid`
    tp_url = f'https://www.espn.com/mens-college-basketball/team/_/id/{tid}'
    tp = Page(tp_url)
    # idk if this is the best way to do it but it should work every time
    conf_url = [tp.soup.find_all('a', string='Full Standings')][0][0]['href']
    cid = conf_url.split('/')[-1]
    cursor.execute('SELECT cid FROM Conferences WHERE cid="?"', (cid, ))
    if cursor.fetchone() is None:
        conf = Page(conf)
        s1 = conf.soup.select('h1[class="headline headline__h1 dib"]')
        abbrev = next(g.text for g in s1).removesuffix("Men's College Basketball Standings - 2023-24").strip()

        s2 = conf.soup.select('div[class="Table__Title"]')
        name = next(g.text for g in s2)

        cursor.execute('INSERT INTO Conferences (cid, name, abbrev) VALUES (?, ?, ?)', (cid, name, abbrev))
    return cid


@with_db_cursor
def fetch_team_data(cursor, tid: Union[str, int]):
    """Fetches team data and populates the database if it does not already exist"""
    tid = str(tid)
    cursor.execute('SELECT * FROM Teams WHERE tid="?" LIMIT 1', (tid, )) # `tid` should be unique within the database 
    res = cursor.fetchone()
    if not res:
        cid = fetch_cid_from_tid(tid)
        
        # access team page for naming
        url = f'https://www.espn.com/mens-college-basketball/team/schedule/_/id/{tid}'
        tp = Page(url)
        selector = tp.soup.select('span[class="flex flex-wrap"] span')
        name, mascot = [g.text for g in selector]

        res = (tid, cid, name, mascot)

        # create new record for team
        cursor.execute('INSERT INTO Teams (tid, cid, name, mascot) VALUES (?, ?, ?, ?)', res)
    return res

@with_db_cursor
def fetch_pid_from_roster(cursor, name: str, tid: Union[str, int], year: Union[str, int]):
    """Fetches pid based on player name and roster (e.g., team + year)"""
    # TODO: I need to refactor this/the usage thereof so player ids are not added individually
    # one option is to use ESPN's pid's, which also eliminate key collision on name
    tid = str(tid)
    year = str(tid)

    cursor.execute('SELECT rid FROM Rosters WHERE tid="?" AND year=? LIMIT 1', (tid, year))
    rid = cursor.fetchone()
    if rid is None:
        # roster does not exist
        cursor.execute('INSERT INTO Rosters (tid, year) VALUES ("?", ?)', (tid, year))
        cursor.execute('SELECT rid FROM Rosters WHERE tid="?" AND year=? LIMIT 1', (tid, year))
        rid = cursor.fetchone()
    
    cursor.execute('SELECT Players.pid FROM PlayerSeasons JOIN Players ON PlayerSeasons.pid = Players.pid WHERE PlayerSeasons.rid = ?', (rid, ))
    pid = cursor.fetchone()
    if pid is None:
        # player does not exist in current roster
        cursor.execute('INSERT INTO Players ')

PLAY_TYPES = (
    ('SHT', re.compile(r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) (made|missed) (Three Point Jumper|Jumper|Layup|Dunk|Free Throw)\.(?: Assisted by ((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)\.)?")),
    ('REB', re.compile(r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) (Offensive|Defensive|Deadball Team) Rebound\.")),
    ('FL', re.compile(r"(Technical )?Foul on ((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)\.")),
    ('TOV', re.compile(r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) Turnover\.")),
    ('STL', re.compile(r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) Steal\.")),
    ('TO', re.compile(r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) Timeout")),
    ('JMP', re.compile(r"Jump Ball won by ((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)")),
    ('EOP', re.compile(r"End of [A-Za-z0-9]+")),
    ('INV', re.compile(r".*"))
)
SHOT_SUBTYPES = (
    ('3PJ', 'Three Point Jumper'),
    ('2PJ', 'Jumper'),
    ('2PL', 'Layup'),
    ('2PD', 'Dunk'),
    ('1FT', 'Free Throw')
)

REB_SUBTYPES = (
    ('OFF', 'Offensive'),
    ('DEF', 'Defensive'),
    ('DBT', 'Deadball Team')
)

@with_db_cursor
def parse_pbp(cursor, gid: Union[str, int]):
    """
    Parses plays from a given game and returns them as a list of lists that
    can be fed into an `sqlite3` `executemany` function call.
    """
    gid = str(gid)

    gp = GamePage(gid)
    pbp = gp.plays
    pbp_m = re.search(r'\"pbp\":\s*\{\"playGrps\":(.+\]\]),\"tms\".*\}', str(pbp.soup), flags=re.DOTALL)
    pbp_j = json.loads(pbp_m[1].replace('\\', ''))

    # fetch game data
    # note: this data also stores whether a game is a conference game
    gm_m = re.search(r'\"gmStrp\":(\{.+\}),\"gpLinks\"', str(pbp.soup), flags=re.DOTALL)
    gm_j = json.loads(gm_m[1].replace('\\', ''))
    dt = datetime.strptime(gm_j['dt'], '%Y-%m-%dT%H:%MZ')
    date = dt.date
    season = dt.year + int(datetime(dt.year, 7, 1) < dt)    # add 1 to year if dt is in the fall semester
    neutral = int(gm_j['neutralSite'])
    for tm in gm_j['tms']:
        if tm['isHome']:
            home = tm['id']
        else:
            away = tm['id']

    cursor.execute('INSERT INTO Games (gid, neutral, home, away, date, season) VALUES (?, ?, ?, "?", ?)', (gid, neutral, home, away, date, season))

    a_tid, h_tid = get_game_tids(gid)
    TeamData = namedtuple('TeamData', ('tid', 'cid', 'name', 'mascot'))
    a_data = TeamData(*fetch_team_data(cursor, a_tid))
    h_data = TeamData(*fetch_team_data(cursor, h_tid))

    def is_team_name(s: str):
        return s == a_data.name or s == h_data.name

    out = []
    for i, pd in enumerate(pbp_j):
        pdl = []
        for play in pd:
            # these fields are not always present
            subtype = None
            pts_scored = None
            plyr = None
            plyr_ast = None
            tid = None

            # these fields are provided directly
            time_min, time_sec = play['clock']['displayValue'].split(':')
            period = play['period']['number']
            away_score = play['awayScore']
            home_score = play['homeScore']
            desc = play['text']
            plid = play['id'].removeprefix(str(gid))

            if 'homeAway' in play:
                tid = a_tid if play['homeAway'] == 'away' else h_tid

            # remaining fields must be parsed from play description
            for t, r in PLAY_TYPES:
                m = r.search(play['text'])
                if m is not None:
                    break
            
            g = m.groups()
            type_ = t
            match type_:
                case 'SHT':
                    # find/make pid of player on `team` roster
                    plyr = fetch_pid_from_roster(g[0], tid, season)

                    # encode subtype
                    for a, s in SHOT_SUBTYPES:
                        if g[2] == s:
                            subtype = a
                            break 

                    # determine point value (make/miss)
                    pts_scored = 0
                    if g[1] == 'made':
                        pts_scored = int(subtype[0])
                        if g[3] is not None:
                            # find/make pid of assister on `team` roster
                            plyr_ast = fetch_pid_from_roster(g[3], tid, season)

                case 'REB' | 'FL' | 'TOV':
                    # can be attributed to team or individual
                    if not is_team_name(g[0]):
                        plyr = fetch_pid_from_roster(g[0], tid, season)

                    # encode subtype
                    if type_ == 'REB':
                        for a, s in REB_SUBTYPES:
                            if g[1] == s:
                                subtype = a
                                break
                
                case 'STL': 
                    plyr = fetch_pid_from_roster(g[0], tid, season)
                    pass

                case 'TO' | 'EOP' | 'INV':
                    # TO: just encode TV timeouts as neutral timeouts
                    pass

            pdl.append((plid, gid, tid, period, time_min, time_sec, type_, subtype, away_score, home_score, pts_scored, desc, plyr, plyr_ast))
        out.append(pdl)