import re
import logging
import json
from datetime import datetime
from collections import namedtuple
from typing import Union, Iterable, Dict, Callable
from database import with_cursor
from webscraper import Page, GamePage

def get_game_tids(gid: Union[str, int]):
    """Retrieves the tid's for the away[0] and home[1] teams from the given game"""
    gid = str(gid)
    url = f'https://www.espn.com/mens-college-basketball/playbyplay/_/gameId/{gid}'
    page = Page(url)
    selector = page.soup.select('div[class="Gamestrip__TeamContainer flex items-center"]')
    out = [re.search(r'/mens-college-basketball/team/_/id/(\d+)', str(g))[1] for g in selector]
    if len(out) < 2:
        logging.warning('Team ids missing') # TODO: provide an alternative to encode with a new team id
    return out

@with_cursor
def fetch_cid_from_tid(cursor, tid: Union[str, int]):
    """Fetches cid from team id"""
    # this function assumes that the team is new and does not yet store its own `cid`
    tp_url = f'https://www.espn.com/mens-college-basketball/team/_/id/{tid}'
    tp = Page(tp_url)
    # idk if this is the best way to do it but it should work every time
    conf_url = [tp.soup.find_all('a', string='Full Standings')][0][0]['href']
    cid = conf_url.split('/')[-1]
    res = cursor.execute('SELECT cid FROM Conferences WHERE cid=":cid"', {'cid': cid}).fetchone()
    if res is None:
        conf = Page(conf_url)
        s1 = conf.soup.select('h1[class="headline headline__h1 dib"]')
        abbrev = next(g.text for g in s1).removesuffix("Men's College Basketball Standings - 2023-24").strip()

        s2 = conf.soup.select('div[class="Table__Title"]')
        name = next(g.text for g in s2)

        cursor.execute('INSERT OR IGNORE INTO Conferences (cid, name, abbrev) VALUES (?, ?, ?)', (cid, name, abbrev))
    return cid


@with_cursor
def fetch_team_data(cursor, tid: Union[str, int]):
    """Fetches team data and populates the database if it does not already exist"""
    tid = str(tid)
    res = cursor.execute('SELECT * FROM Teams WHERE tid=:tid LIMIT 1', {'tid': tid}).fetchone() # `tid` should be unique within the database 
    if res is None:
        cid = fetch_cid_from_tid(tid)
        
        # access team page for naming
        url = f'https://www.espn.com/mens-college-basketball/team/schedule/_/id/{tid}'
        tp = Page(url)
        selector = tp.soup.select('span[class="flex flex-wrap"] span')
        name, mascot = (g.text for g in selector)

        res = (tid, cid, name, mascot)

        # create new record for team
        cursor.execute('INSERT OR IGNORE INTO Teams (tid, cid, name, mascot) VALUES (?, ?, ?, ?)', res)
    return res

@with_cursor
def fetch_rid(cursor, tid: Union[str, int], season: Union[str, int]):
    tid = str(tid)
    season = str(season)
    
    res = cursor.execute('SELECT rid FROM Rosters WHERE tid=":tid" AND season=:season LIMIT 1', {'tid': tid, 'season': season}).fetchone()
    if res is None:
        # roster does not exist
        cursor.execute('INSERT INTO Rosters (tid, season) VALUES (:tid, :season)', {'tid': tid, 'season': season})
        res = cursor.execute('SELECT rid FROM Rosters WHERE tid=:tid AND season=:season LIMIT 1', {'tid': tid, 'season': season}).fetchone()
    rid = res[0]
    return rid

@with_cursor
def fetch_pid_from_roster(cursor, name: str, rid: Union[str, int]):
    """Fetches pid based on rid"""
    # TODO: I need to refactor this/the usage thereof so player ids are not added individually
    # one option is to use ESPN's pid's, which also eliminate key collision on name
    rid = str(rid)
    res = cursor.execute('SELECT Players.pid FROM PlayerSeasons JOIN Players ON PlayerSeasons.pid = Players.pid WHERE PlayerSeasons.rid = ?', (rid, )).fetchone()
    if res is None:
        # TODO: player does not exist in current roster
        cursor.execute('INSERT INTO Players ')
        pass

RE_PLAY_TYPES = (
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
ABBREV_SHOT_SUBTYPES = (
    ('3PJ', 'Three Point Jumper'),
    ('2PJ', 'Jumper'),
    ('2PL', 'Layup'),
    ('2PD', 'Dunk'),
    ('1FT', 'Free Throw')
)

ABBREV_REB_SUBTYPES = (
    ('OFF', 'Offensive'),
    ('DEF', 'Defensive'),
    ('DBT', 'Deadball Team')
)

ABBREV_POS = (
    ('G', 'Guard'),
    ('F', 'Forward'),
    ('C', 'Center')
)

def _get_abb_cond(table, value, cond = lambda x, y: x == y):
    for abb, l in table:
        if cond(value, l):
            return abb

def _get_abb(table, value):
    return _get_abb_cond(table, value, lambda x, y: x == y)


@with_cursor
def select_unique_or_insert(cursor, sql: str, sql_params: Iterable | Dict, insert_func: Callable, *insert_args, **insert_kwargs):
    """Selects the unique record using the supplied SQL statement and inserts it if it doesn't exist."""
    res = cursor.execute(sql, sql_params).fetchone()
    if res is None:
        insert_func(*insert_args, checked = True, **insert_kwargs)
        res = cursor.execute(sql, sql_params).fetchone()
    return res

@with_cursor
def insert_new_plyr(cursor, pid: Union[str, int], checked: bool = False):
    """Inserts if does not exist a new player to the Players table."""
    pid = str(pid)
    if not checked:
        res = cursor.execute('SELECT pid FROM Players WHERE pid=:pid LIMIT 1', {'pid': pid}).fetchone()
        if res is not None:
            return False
    
    url = f'https://www.espn.com/mens-college-basketball/player/_/id/{pid}'
    pl = Page(url)
    hdr_s = pl.soup.select('div[class="PlayerHeader__Left flex items-center justify-start overflow-hidden brdr-clr-gray-09"]')
    hdr, = (g for g in hdr_s)
    
    fname, lname = (nm.text.replace('.', '') for nm in hdr.select('h1[class="PlayerHeader__Name flex flex-column ttu fw-bold pr4 h2"] span'))
    pos_long = hdr.select('ul[class="PlayerHeader__Team_Info list flex pt1 pr4 min-w-0 flex-basis-0 flex-shrink flex-grow nowrap"] li')[-1].text
    pos = _get_abb(ABBREV_POS, pos_long)
    
    bio = hdr.select('ul[class="PlayerHeader__Bio_List flex flex-column list clr-gray-04"] li')
    # htwt_str, = (li.text for li in bio if li.text.startswith('HT/WT'))
    htft, htin, wt = None, None, None
    try:
        htwt_str, = (li.text for li in bio if li.text.startswith('HT/WT'))
        htft, htin, wt = re.match(r'HT/WT(\d+)\' (\d+)", (\d+) lbs', htwt_str).groups()
    except ValueError as e:
        logging.debug(f'Missing ht/wt for {pid=} (error: {e})')
    
    d = {
        'pid': pid,
        'fname': fname,
        'lname': lname,
        'pos': pos,
        'htft': htft,
        'htin': htin,
        'wt': wt
    }
    
    cursor.execute('INSERT INTO Players (pid, fname, lname, pos, htft, htin, wt) VALUES (:pid, :fname, :lname, :pos, :htft, :htin, :wt)', d)
    
    return d

@with_cursor
def insert_new_plyrseason(cursor, pid: Union[str, int], rid: Union[str, int], checked: bool = False):
    pid = str(pid)
    rid = str(rid)
    d = {'pid': pid, 'rid': rid}
    if not checked:
        res = cursor.execute('SELECT rid FROM PlayerSeasons WHERE pid=:pid AND rid=:rid LIMIT 1', d).fetchone()
        if res is not None:
            return False
    
    cursor.execute('INSERT INTO PlayerSeasons (pid, rid) VALUES (:pid, :rid)', d)
    return d

@with_cursor
def parse_pbp(cursor, gid: Union[str, int]):
    """
    Parses plays from a given game and returns them as a list of lists that
    can be fed into an `sqlite3` `executemany` function call.
    """
    gid = str(gid)
    
    # TODO: lots of floating variables that are used throughout the function,
    #       see if i can break this up more logically

    # grab play-by-play data from game page
    gp = GamePage(gid)
    pbp = gp.plays
    pbp_m = re.search(r'\"pbp\":\s*\{\"playGrps\":(.+\]\]),\"tms\".*\}', str(pbp.soup), flags=re.DOTALL)
    pbp_j = json.loads(pbp_m[1].replace('\\', ''))

    # fetch game data
    # note: this data also stores whether a game is a conference game
    gm_m = re.search(r'\"gmStrp\":(\{.+\}),\"gpLinks\"', str(pbp.soup), flags=re.DOTALL)
    gm_j = json.loads(gm_m[1].replace('\\', ''))
    dt = datetime.strptime(gm_j['dt'], '%Y-%m-%dT%H:%MZ')
    date = dt.strftime('%Y-%m-%d')
    season = dt.year + int(datetime(dt.year, 7, 1) < dt)    # add 1 to year if dt is in the fall semester
    neutral = 0 if 'neutralSite' not in gm_j else int(gm_j['neutralSite'])
    for tm in gm_j['tms']:
        if tm['isHome']:
            home = tm['id']
        else:
            away = tm['id']

    cursor.execute('''INSERT OR IGNORE INTO Games (gid, neutral, home, away, season, date) 
                      VALUES (:gid, :neutral, :home, :away, :season, :date)''',
                      {
                        'gid': gid,
                        'neutral': neutral,
                        'home': home,
                        'away': away,
                        'season': season,
                        'date': date
                      })

    # TODO: this section is bootycheeks lmao
    a_tid, h_tid = get_game_tids(gid)

    TeamData = namedtuple('TeamData', ('tid', 'cid', 'name', 'mascot', 'rid'))
    a_data = TeamData(*fetch_team_data(a_tid), fetch_rid(a_tid, season))
    h_data = TeamData(*fetch_team_data(h_tid), fetch_rid(h_tid, season))      
    
    # insert all players from box score if it exists
    # TODO: if we can't find the players from the box score, resolve them manually
    #       by using their name against/inserting into the appropriate roster
    bs = gp.boxscore
    bs_tab_s = bs.soup.select('tbody[class="Table__TBODY"]')
    bs_plyr_s = []
    for tab in bs_tab_s:
        bs_ath_s = tab.select('a[class="AnchorLink truncate db Boxscore__AthleteName"]')
        if bs_ath_s:
            bs_plyr_s.append(bs_ath_s)
    a_plyr_s, h_plyr_s = bs_plyr_s
    
    players = { # map player names to pid
        a_tid: dict(),
        h_tid: dict()    
        }    
    # player_d_s = []
    # roster_d_s = []
    
    for data in [a_data, h_data]:
        # clean the hell up out of this
        # TODO: factor this so we can executemany instead
        tid = str(data.tid)
        rid = data.rid
        plyr_s = a_plyr_s if tid == a_tid else h_plyr_s
        for r in plyr_s:
            pid = re.search(r'.*:(\d+)', r['data-player-uid'])[1]
        
            plyr_d = select_unique_or_insert('SELECT fname, lname FROM Players WHERE pid=:pid LIMIT 1', {'pid': pid}, insert_new_plyr, pid)
            select_unique_or_insert('SELECT rid FROM PlayerSeasons WHERE pid=:pid AND rid=:rid LIMIT 1', {'pid': pid, 'rid': rid}, insert_new_plyrseason, pid, rid)
            
            # player_d_s.append(plyr_d)
            # roster_d_s.append(roster_d)
                    
            plyr_name = f'{plyr_d[0]} {plyr_d[1]}'
            players[tid][plyr_name] = pid
            
    # pbp convenience functions
    def is_team_name(s: str):
        return s == a_data.name or s == h_data.name
    
    def _get_or_warn(d: dict, key):
        # TODO: for player name typos, could option to search
        #       manually O(n) through dict keys for last name
        #       only since that is more likely to be correct
        if key in d:
            return d[key]
        # logging.warning(f'Couldn\'t find {key=} in dict={d}')  
    
    # parse play-by-play
    plays = []
    for _, pd in enumerate(pbp_j):
        for play in pd:
            # these fields are not always present
            subtype = None
            pts_scored = None
            plyr = None
            plyr_ast = None
            tid = None

            # these fields are provided directly
            plyid = play['id'].removeprefix(str(gid))
            time_min, time_sec = play['clock']['displayValue'].split(':')
            period = play['period']['number']
            away_score = play['awayScore']
            home_score = play['homeScore']
            if 'text' not in play:
                # check if play was scoring play
                type_ = None
                if play['scoringPlay']:
                    # check who scored and how muchs
                    type_ = 'SHT'
                    try:
                        last_score = plays[-1][8:10]    # quick fix: for dev purposes, need to be able to name the fields
                        if last_score[0] != away_score:
                            # away team scored
                            pts_scored = away_score - last_score[0]
                        else:
                            # home team scored
                            pts_scored = home_score - last_score[1]
                    except IndexError:
                        pass
                
                plays.append((plyid, gid, tid, period, time_min, time_sec, type_, subtype, away_score, home_score, pts_scored, None, plyr, plyr_ast))
                continue
            desc = play['text']    

            if 'homeAway' in play:
                data = a_data if play['homeAway'] == 'away' else h_data 
                tid = str(data.tid)
                rid = str(data.rid)

            # remaining fields must be parsed from play description
            for t, r in RE_PLAY_TYPES:
                m = re.search(r, desc)
                if m is not None:
                    type_ = t
                    break
            
            g = m.groups()
            match type_:
                case 'SHT':
                    plyr_name, sht_result, sht_sub, ast_name = g
                    plyr_name = plyr_name.replace('.', '')  # player names never include periods within player page
                    # find/make pid of player on `team` roster
                    plyr = _get_or_warn(players[tid], plyr_name)

                    # encode subtype
                    subtype = _get_abb(ABBREV_SHOT_SUBTYPES, sht_sub)

                    # determine point value (make/miss)
                    pts_scored = 0
                    if sht_result == 'made':
                        pts_scored = int(subtype[0])
                        if ast_name is not None:
                            # find/make pid of assister on `team` roster
                            ast_name = ast_name.replace('.', '')
                            plyr = _get_or_warn(players[tid], ast_name)

                case 'REB' | 'TOV':
                    # can be attributed to team or individual
                    plyr_name = g[0].replace('.', '')
                    if not is_team_name(plyr_name):
                        plyr = _get_or_warn(players[tid], plyr_name)

                    # encode subtype
                    if type_ == 'REB':
                        reb_sub = g[1]
                        subtype = _get_abb(ABBREV_REB_SUBTYPES, reb_sub)
                
                case 'FL':
                    tech, plyr_name = g
                    if tech:
                        subtype = 'TCH'
                    plyr_name = plyr_name.replace('.', '')
                    plyr = _get_or_warn(players[tid], plyr_name)
                    
                
                case 'STL': 
                    plyr_name = g[0].replace('.', '')
                    plyr = _get_or_warn(players[tid], plyr_name)

                case 'TO' | 'EOP' | 'INV':
                    # TO: just encode TV timeouts as neutral timeouts
                    pass

            plays.append((plyid, gid, tid, period, time_min, time_sec, type_, subtype, away_score, home_score, pts_scored, desc, plyr, plyr_ast))
    cursor.executemany('''INSERT INTO Plays (plyid, gid, tid, period, time_min, time_sec, type, 
                             subtype, away_score, home_score, pts_scored, desc, plyr, plyr_ast)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', plays)