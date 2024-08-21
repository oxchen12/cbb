import asyncio
import re
import logging
import json
import aiohttp
from datetime import datetime
from bs4 import BeautifulSoup
from .database import with_cursor
from .webscraper import Page, GamePage

ESPN_HOME = 'https://www.espn.com/mens-college-basketball'
RE_PLAY_TYPES = (
    ('SHT',
     r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)\s+(made|missed)\s+(Three Point Jumper|Jumper|Layup|Dunk|Free Throw|Hook Shot|Two Point Tip Shot)?\.?(?:\s+Assisted by\s+((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)\.)?"),
    ('REB', r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)\s+(Offensive|Defensive|Deadball Team)\s+Rebound\."),
    ('FL', r"(Technical )?Foul on\s+((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)\."),
    ('TOV', r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)\s+Turnover\."),
    ('STL', r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)\s+Steal\."),
    ('BLK', r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)\s+Block\."),
    ('TO', r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)\s+Timeout"),
    ('JMP', r"Jump Ball won by\s+((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)"),
    ('EOP', r"End of\s+[A-Za-z0-9]+"),
    ('INV', r".*")
)
ABBREV_SHOT_SUBTYPES = (
    ('3PJ', 'Three Point Jumper'),
    ('3FG', ''),  # fall-through for generic 3-pointer
    ('2PJ', 'Jumper'),
    ('2PL', 'Layup'),
    ('2PD', 'Dunk'),
    ('2PT', 'Two Point Tip Shot'),
    ('2PH', 'Hook Shot'),
    ('2FG', ''),  # fall-through for generic 2-pointer
    ('1FT', 'Free Throw'),
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

TODO_ERROR = 91202


def get_game_tids(gid: int):
    """Retrieves the tid's for the away[0] and home[1] teams from the given game"""
    url = f'{ESPN_HOME}/playbyplay/_/gameId/{gid}'
    page = Page(url)
    selector = page.soup.select('div[class="Gamestrip__TeamContainer flex items-center"]')
    out = [re.search(r'/mens-college-basketball/team/_/id/(\d+)', str(g)) for g in selector]
    out = [e[1] for e in out if e is not None]
    if len(out) < 2:
        # TODO: provide an alternative to encode with a new team id that doesn't collide with ESPN's
        #       -- for now, we will just have a special case exit for parse_pbp
        #       -- this is part of a larger issue where we need to be able to handle data that simply
        #       -- does not exist on ESPN's website, e.g., DII teams and players
        logging.warning('At least one team id missing, skipping this game')
        return TODO_ERROR
    return out


@with_cursor
def fetch_cid_from_tid(cursor, tid: int):
    """Fetches cid from team id"""
    # this function assumes that the team is new and does not yet store its own `cid`
    tp_url = f'{ESPN_HOME}/team/_/id/{tid}'
    tp = Page(tp_url)
    # idk if this is the best way to do it but it should work every time
    conf_url = tp.soup.find('a', string='Full Standings')['href']
    cid = conf_url.split('/')[-1]
    res = cursor.execute('SELECT cid FROM Conferences WHERE cid=":cid LIMIT 1"', {'cid': cid}).fetchone()

    if res is None:
        conf = Page(conf_url)
        s1 = conf.soup.select('h1[class="headline headline__h1 dib"]')
        abbrev = s1[0].text.removesuffix("Men's College Basketball Standings - 2023-24").strip()

        s2 = conf.soup.select('div[class="Table__Title"]')
        name = s2[0].text

        cursor.execute('INSERT INTO Conferences (cid, name, abbrev) VALUES (:cid, :name, :abbrev)',
                       {'cid': cid, 'name': name, 'abbrev': abbrev})

    return cid


@with_cursor
def fetch_team_data(cursor, tid: int):
    """Fetches team data and populates the database if it does not already exist"""
    res = cursor.execute('SELECT tid FROM Teams WHERE tid=:tid LIMIT 1',
                         {'tid': tid}).fetchone()

    if res is None:
        cid = fetch_cid_from_tid(tid)

        # access team page for naming
        url = f'{ESPN_HOME}/team/schedule/_/id/{tid}'
        tp = Page(url)
        selector = tp.soup.select('span[class="flex flex-wrap"] span')
        name, mascot = (g.text for g in selector)

        res = {
            'tid': tid,
            'cid': cid,
            'name': name,
            'mascot': mascot
        }

        # create new record for team
        cursor.execute('INSERT INTO Teams (tid, cid, name, mascot) VALUES (:tid, :cid, :name, :mascot)', res)

    return dict(res)


@with_cursor
def fetch_rid(cursor, tid: int, season: int):
    res = cursor.execute('SELECT rid FROM Rosters WHERE tid=":tid" AND season=:season LIMIT 1',
                         {'tid': tid, 'season': season}).fetchone()

    if res is None:
        # roster does not exist
        cursor.execute('INSERT INTO Rosters (tid, season) VALUES (:tid, :season)', {'tid': tid, 'season': season})
        res = cursor.execute('SELECT rid FROM Rosters WHERE tid=:tid AND season=:season LIMIT 1',
                             {'tid': tid, 'season': season}).fetchone()

    rid = res['rid']
    return rid


def _get_abb(table, value):
    for abb, l in table:
        if value == l:
            return abb


@with_cursor
def parse_pbp(cursor, gid: int):
    """
    Parses plays from a given game and inserts them into the database, along with any other missing game data.
    """
    # TODO: if we can assume that a game can only be inserted by a call to parse_pbp, we can exit here
    # cursor.execute('SELECT gid FROM Games WHERE gid=:gid LIMIT 1', {'gid': gid})
    # if cursor.fetchone():
    #     return

    # grab play-by-play data from game page
    gp = GamePage(gid)
    pbp = gp.plays
    pbp_m = re.search(r'\"pbp\":\s*\{\"playGrps\":(.+\]\]),\"tms\".*\}', str(pbp.soup), flags=re.DOTALL)
    if not pbp_m:
        logging.warning(f'Play by play data is not available for {gid=}')
        return None
    pbp_j = json.loads(pbp_m[1].replace('\\', ''))

    # fetch game data
    # note: this data also stores whether a game is a conference game
    gm_m = re.search(r'\"gmStrp\":(\{.+\}),\"gpLinks\"', str(pbp.soup), flags=re.DOTALL)
    gm_j = json.loads(gm_m[1].replace('\\', ''))
    dt = datetime.strptime(gm_j['dt'], '%Y-%m-%dT%H:%MZ')
    date = dt.strftime('%Y-%m-%d')
    season = dt.year + int(datetime(dt.year, 7, 1) < dt)  # add 1 to year if dt is in the fall semester
    neutral = 0 if 'neutralSite' not in gm_j else int(gm_j['neutralSite'])
    for tm in gm_j['tms']:
        if tm['isHome']:
            home = tm['id']
        else:
            away = tm['id']

    cursor.execute('''INSERT INTO Games (gid, neutral, home, away, season, date) 
                      VALUES (:gid, :neutral, :home, :away, :season, :date)''',
                   {
                       'gid': gid,
                       'neutral': neutral,
                       'home': home,
                       'away': away,
                       'season': season,
                       'date': date
                   })

    res = get_game_tids(gid)
    if res == TODO_ERROR:
        return None
    a_tid, h_tid = res

    team_data = {
        'home': {**fetch_team_data(h_tid), **{'rid': fetch_rid(h_tid, season)}},
        'away': {**fetch_team_data(a_tid), **{'rid': fetch_rid(a_tid, season)}}
    }

    # insert all players from box score if it exists
    # TODO: while almost all box score participants also appear in the play-by-play,
    #       it is possible for players to be parsed here without ever appearing in
    #       Plays, making it impossible to reliably determine whether a player played
    #       in a game and how many they've played in only from play-by-play
    bs = gp.boxscore
    team_dumps_raw = []
    for tab in bs.soup.select('tbody[class="Table__TBODY"]'):
        box_dumps = tab.select('a[class="AnchorLink truncate db Boxscore__AthleteName"]')
        if box_dumps:
            team_dumps_raw.append(box_dumps)
    team_dumps = {
        'away': team_dumps_raw[0],
        'home': team_dumps_raw[1]
    }

    async def _fetch(session, url):
        async with session.get(url) as resp:
            return str(await resp.read())

    async def _get_plyr_pages(dumps):
        pids = [re.search(r'.*:(\d+)', dump['data-player-uid'])[1] for dump in dumps]
        urls = [f'{ESPN_HOME}/player/_/id/{pid}' for pid in pids]
        async with aiohttp.ClientSession() as session:
            tasks = [asyncio.create_task(_fetch(session, url)) for url in urls]
            htmls = await asyncio.gather(*tasks)
            return htmls

    async def _get_all_plyr_pages(team_dumps):
        plyr_htmls = dict()
        plyr_htmls['away'] = await _get_plyr_pages(team_dumps['away'])
        plyr_htmls['home'] = await _get_plyr_pages(team_dumps['home'])
        return plyr_htmls

    # asynchronously grab the player pages -- each page ~400KB * ~22 players = 8.8 MB in memory
    plyr_htmls = asyncio.run(_get_all_plyr_pages(team_dumps))

    # process acquired player data
    players = {
        team_data['away']['tid']: dict(),
        team_data['home']['tid']: dict()
    }
    plyr_d_add = []
    plyrseason_d_add = []
    for ha, team_htmls in plyr_htmls.items():
        tid = team_data[ha]['tid']
        for html in team_htmls:
            bs = BeautifulSoup(str(html), 'html.parser')
            url = bs.select('meta[property="og:url"]')[0]['content']
            pid = re.search(r'\d+', url)[0]

            res = cursor.execute('SELECT fname, lname FROM Players WHERE pid=:pid', {'pid': pid}).fetchone()
            if res is None:
                # m2 contains player info (hardcoded with ending for now)
                m2 = re.search(r'"plyrHdr":\{"ath":(\{.*\}),"statsBlck".*\}', html)
                j2 = json.loads(m2[1].replace('\\\\', '\\').replace('\\\'', '\''))
                fname = j2['fNm']
                lname = j2['lNm']
                pos = j2.get('posAbv', None)[-1]  # TODO: may need to test this for possible multiple position listing
                htft, htin, wt = None, None, None
                htwt_raw = j2.get('htwt', None)
                if htwt_raw is not None:
                    htft, htin, wt = re.search(r'''(\d+)' (\d+)", (\d+) lbs''', htwt_raw).groups()
                # brthpl = j2.get('brthpl', None)

                res = {
                    'pid': pid,
                    'fname': fname,
                    'lname': lname,
                    'pos': pos,
                    'htft': htft,
                    'htin': htin,
                    'wt': wt,
                }

                ha = 'away' if tid == team_data['away'] else 'home'

                plyr_d_add.append(res)
                plyrseason_d_add.append({'pid': pid, 'rid': team_data[ha]['rid']})

            plyr_name = f'{res["fname"]} {res["lname"]}'
            try:
                players[tid][plyr_name] = pid
            except KeyError:
                print(players.keys())

    # insert missing Players and PlayerSeasons to appropriate tables
    cursor.executemany(
        'INSERT INTO Players (pid, fname, lname, pos, htft, htin, wt) VALUES (:pid, :fname, :lname, :pos, :htft, :htin, :wt)',
        plyr_d_add)
    cursor.executemany('INSERT INTO PlayerSeasons (pid, rid) VALUES (:pid, :rid)',
                       plyrseason_d_add)

    # pbp convenience functions
    def is_team_name(s: str):
        return s == team_data['home']['name'] or s == team_data['away']['name']

    def _get_or_warn(d: dict, key):
        # TODO: for player name typos, could option to search
        #       manually O(n) through dict keys for last name
        #       only since that is more likely to be accurate
        if key in d:
            return d[key]
        # logging.warning(f'Couldn\'t find {key=} in dict={d}')

    def _get_pts_scored(away_score, home_score, last_play):
        try:
            if last_play['away_score'] != away_score:
                # away team scored
                return away_score - last_play['away_score']
            else:
                # home team scored
                return home_score - last_play['home_score']
        except IndexError:
            pass

    # parse play-by-play
    plays = []
    for pd in pbp_j:
        for play in pd:
            # TODO: I could pull this section out to make it more readable
            # these fields are not always present
            subtype = None
            pts_scored = None
            plyr = None
            plyr_ast = None
            tid = None

            # these fields are provided directly
            plyid = int(play['id'].removeprefix(str(gid)))
            cursor.execute('SELECT plyid FROM Plays WHERE plyid=:plyid AND gid=:gid', {'plyid': plyid, 'gid': gid})
            if cursor.fetchone():
                continue
            time_min, time_sec = play['clock']['displayValue'].split(':')
            period = play['period']['number']
            away_score = play['awayScore']
            home_score = play['homeScore']
            ha = play.get('homeAway', None)
            if ha is not None:
                data = team_data[ha]
                tid = data['tid']
                # rid = data['rid']
            if 'text' not in play:  # desc not provided
                # check if play was scoring play
                type_ = None
                if play['scoringPlay']:
                    # check who scored and how many points
                    type_ = 'SHT'
                    if plays:
                        pts_scored = _get_pts_scored(away_score, home_score, plays[-1])
                plays.append({'plyid': plyid, 'gid': gid, 'tid': tid, 'period': period,
                              'time_min': time_min, 'time_sec': time_sec, 'type': type_,
                              'subtype': subtype, 'away_score': away_score,
                              'home_score': home_score, 'pts_scored': pts_scored,
                              'desc': None, 'plyr': plyr, 'plyr_ast': plyr_ast})
                continue
            desc = play['text']

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
                    plyr_name = plyr_name.replace('.', '')  # always exclude periods from player names
                    plyr = _get_or_warn(players[tid], plyr_name)  # get pid of shooter
                    if sht_sub is not None:  # some missed shots do not have encoded subtype
                        subtype = _get_abb(ABBREV_SHOT_SUBTYPES, sht_sub)  # encode subtype

                    pts_scored = 0  # default 0 points
                    if sht_result == 'made':
                        if sht_sub is not None:
                            pts_scored = int(subtype[0])  # if made, determine points from subtype
                        else:
                            pts_scored = _get_pts_scored(away_score, home_score, plays[-1])
                            subtype = '3FG' if pts_scored == 3 else '2FG'
                        if ast_name is not None:
                            ast_name = ast_name.replace('.', '')
                            plyr_ast = _get_or_warn(players[tid], ast_name)  # get pid of assister

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

                case 'STL' | 'BLK':
                    plyr_name = g[0].replace('.', '')
                    plyr = _get_or_warn(players[tid], plyr_name)

                case 'TO' | 'EOP' | 'INV':
                    # TO: just encode TV timeouts as neutral timeouts
                    pass

            plays.append({'plyid': plyid, 'gid': gid, 'tid': tid, 'period': period,
                          'time_min': time_min, 'time_sec': time_sec, 'type': type_,
                          'subtype': subtype, 'away_score': away_score,
                          'home_score': home_score, 'pts_scored': pts_scored,
                          'desc': desc, 'plyr': plyr, 'plyr_ast': plyr_ast})
    cursor.executemany('''INSERT INTO Plays (plyid, gid, tid, period, time_min, time_sec, type, 
                             subtype, away_score, home_score, pts_scored, desc, plyr, plyr_ast)
                          VALUES (:plyid, :gid, :tid, :period, :time_min, :time_sec, :type, 
                             :subtype, :away_score, :home_score, :pts_scored, :desc, :plyr, :plyr_ast)''',
                       plays)
