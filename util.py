import requests
import re
import typing
import datetime
from prettytable import PrettyTable
from bs4 import BeautifulSoup
from dataclasses import dataclass
from enum import Enum, auto

WEB_HOME = "https://www.cbssports.com/college-basketball/gametracker"

class Page:
    def __init__(self, url: str):
        self._url: str = url
        self._page = None
        self._soup = None

    @property
    def page(self):
        if self._page is None:
            self._page = requests.get(self._url)
        return self._page
    
    @property
    def soup(self):
        if self._soup is None:
            self._soup = BeautifulSoup(self.page.content, "html.parser")
        return self._soup

class GamePage(Page):
    """
    Wrapper for a page describing a past game played.
    """
    class Category(Enum):
        RECAP = auto()
        BOX = auto()
        PLAYS = auto()

    def __init__(self, gid: str):
        assert(re.match(r"NCAAB_\d{8}_[A-Z]+@[A-Z]+", gid))
        self._gid: str = gid
        self._box = None
        self._plays = None
        self._home = None
        self._away = None
        Page.__init__(self, f"{WEB_HOME}/recap/{self._gid}/")

    def __repr__(self):
        return f"GamePage(gid={self._gid})"
    
    def _get_url(self, category: Category = Category.PLAYS):
        dest = None
        match category:
            case GamePage.Category.RECAP:
                dest = "recap"
            case GamePage.Category.BOX:
                dest = "boxscore"
            case GamePage.Category.PLAYS:
                dest = "playbyplay"
        if dest is not None:
            return f"{WEB_HOME}/{dest}/{self._gid}"
        return None
    
    def _get_soup(self, category: Category = Category.PLAYS):
        url = self._get_url(category=category)
        if url is not None:
            return BeautifulSoup(requests.get(url).content, "html.parser")
    
    @property
    def box_score(self):
        if self._box is None:
            self._box = self._get_soup(category=GamePage.Category.BOX)
        return self._box

    @property
    def plays(self):
        if self._plays is None:
            self._plays = self._get_soup(category=GamePage.Category.PLAYS)
        return self._plays
    
    @property
    def home(self):
        if self._home is None:
            self._home = re.match(r"NCAAB_\d+_[A-Z]+@([A-Z]+)", self._gid).group(1)
        return self._home
    
    @property
    def away(self):
        if self._away is None:
            self._away = re.match(r"NCAAB_\d+_([A-Z]+)@[A-Z]+", self._gid).group(1)
        return self._away
    
class Play:
    """Encodes a single play/event."""

    class Type(Enum):
        SHOT = auto()
        REB = auto()
        FOUL = auto()
        TO = auto()
        BLK = auto()
        TIME = auto()
        JUMP = auto()
        EOP = auto()
        INV = auto()
    
    TYPE_REGEX = (
        (Type.SHOT, r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) (makes|misses)( [a-z]+)? (two point|three point|free throw) ([A-Za-z0-9 ]+[A-Za-z0-9])(?: \(((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) assists\))?"),
        (Type.REB, r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) (offensive|defensive) rebound"),
        (Type.FOUL, r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) ([A-Za-z]+) foul(?: \(((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) draws the foul\))?"),
        (Type.TO, r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) turnover(?: \(([a-z ]+)\))?(?: \(((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) steals\))?"),
        (Type.BLK, r"((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) blocks ((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)'s (two point|three point) ([A-Za-z0-9 ]+[A-Za-z0-9])"),
        (Type.TIME, r"((?:(?:[A-Za-z']+ )*[A-Za-z']+)|TV)(?: 30 second)? timeout"),
        (Type.JUMP, r"(?:Jump ball. )?((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) vs. ((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+)(?: \(((?:[A-Za-z0-9.'-]+ )*[A-Za-z0-9.'-]+) gains possession\))"),
        (Type.EOP, r"End of period"),
        (Type.INV, r".*")
    )

    def __init__(self, raw: list):
        self._team, self._time, self._pts, self._desc, self._score = (e if e is None else e.strip() for e in raw)
        self._type: typing.Optional[Play.Type] = None
        self._subtype: typing.Optional[str] = None
        self._params: dict[str, str] = dict()      # shot + turnover information
        self._players = None
        self._parse_desc()
    
    def __repr__(self):
        return f"Play(team={self.team}, time={self.time}, type={self.type}, score={self.score})"
    
    @property
    def team(self):
        return self._team
    
    @property
    def time(self):
        return self._time
    
    @property
    def pts(self):
        return self._pts

    @pts.setter
    def pts(self, value):
        if not 0 <= int(value) <= 3:
            raise ValueError(f"Invalid point value: {value}")
        self._pts = str(value).strip()
    
    @property
    def desc(self):
        return self._desc
    
    @property
    def score(self):
        return self._score

    @score.setter
    def score(self, value: str):
        if not re.match(r"\d+-\d+", value):
            raise ValueError(f"Invalid score: {value}")
        self._score = value.strip()

    @property
    def type(self):
        return self._type
        
    @property
    def subtype(self):
        return self._subtype

    @property
    def params(self):
        return self._params.copy()
    
    @property
    def players(self):
        if self._players is None:
            players = []
            match self.type:
                case Play.Type.SHOT:
                    players.append(self.params['shooter'])
                    players.append(self.params['assister'])
                case Play.Type.REB:
                    players.append(self.params['rebounder'])
                case Play.Type.FOUL:
                    players.append(self.params['fouler'])
                    # playersppenddd(self.params['drawer'])
                case Play.Type.TO:
                    players.append(self.params['committer'])
                    players.append(self.params['stealer'])
                case Play.Type.BLK:
                    players.append(self.params['blocker'])
                    players.append(self.params['shooter'])
            self._players = [p for p in players if p is not None]
        return self._players

    def _parse_desc(self):
        """
        Parses description into structured play information. 
        Populates `self._type`, `self._subtype`, `self._params.`
        """
        for type_, regex in Play.TYPE_REGEX:
            m = re.match(regex, self._desc)
            if m:
                break
        
        self._type = type_
        groups = m.groups()
        match self.type:
            case Play.Type.SHOT:
                self._subtype = groups[3]
                self._params["shooter"] = groups[0]
                self._params["assister"] = groups[5]        # might be None
                self._params["made"] = groups[1] == "makes"
                self._params["ft_num" if self._subtype == "free throw" else "shot_type"] = groups[4]
                self._params["foul_type"] = groups[2]
            case Play.Type.REB:
                self._subtype = groups[1]
                self._params["rebounder"] = groups[0]
            case Play.Type.FOUL:
                self._subtype = groups[1]
                self._params["fouler"] = groups[0]
                self._params["drawer"] = groups[2]
            case Play.Type.TO:
                self._params["committer"] = groups[0]
                self._params["stealer"] = groups[2]
                self._params["cause"] = groups[1]
            case Play.Type.BLK:
                self._subtype = groups[2]
                self._params["blocker"] = groups[0]
                self._params["shooter"] = groups[1]
                self._params["shot_type"] = groups[3]
            case Play.Type.TIME:
                if groups[0] == "TV":
                    self._subtype = "tv"
                else:
                    self._subtype = "team"
                    self._params["team"] = groups[0]
            case Play.Type.JUMP:
                self._params["player_1"] = groups[0]
                self._params["player_2"] = groups[1]
                self._params["possessor"] = groups[2] 
            case Play.Type.EOP:
                pass
            case Play.Type.INV:
                pass

# TODO: add `Period`` class

"""TODO: date, venue, encoding `Team`s"""
class Game:
    """Encodes a single game between opponents."""

    PLAY_REGEX = r"\s*(\d+:\d+)\s+(?:\+(\d))?\s+((?:[A-Za-z0-9.'-()]+ ?)+)\s+(\d+-\d+)?\s*"

    def __init__(self, gid: str):
        assert(re.match(r"NCAAB_\d{8}_[A-Z]+@[A-Z]+", gid))
        self._gid = gid
        self._page = GamePage(gid)
        self._plays = None

    def __repr__(self):
        return f"Game(gid={self._gid})"

    @property
    def plays(self):
        if self._plays is None:
            self._plays = self._parse_plays()
        return self._plays
    
    @property
    def all_plays(self):
        return self.plays[0] + self.plays[1]
    
    @property
    def home(self):
        return self._page.home
    
    @property
    def away(self):
        return self._page.away
    
    @property
    def date(self):
        _, year, month, day = re.match(r".*(\d{4})(\d{2})(\d{2})", self.gid).groups()
        return datetime.date(year, month, day)

    @property
    def gid(self):
        return self._gid

    def _parse_plays(self):
        first, second = self._page.plays.find_all('div', {'class' : 'TableBase'})
        plays = [[], []]
        last_score = "0-0"
        for x in first.find_all('tr'):
            m = re.match(Game.PLAY_REGEX, x.text)
            if m:
                play = Play([self._get_team(x)] + list(m.groups()))
                play.pts = play.pts if play.pts is not None else 0
                if play.score is None:
                    play.score = last_score
                else:
                    last_score = play.score
                plays[0].append(play)
        for x in second.find_all('tr'):
            m = re.match(Game.PLAY_REGEX, x.text)
            if m:
                play = Play([self._get_team(x)] + list(m.groups()))
                play.pts = play.pts if play.pts is not None else 0
                if play.score is None:
                    play.score = last_score
                else:
                    last_score = play.score
                plays[1].append(play)
        return plays
    
    def _get_team(self, event) -> typing.Optional[str]:
        home = self.home in str(event)
        away = self.away in str(event)
        if home:
            return self.home
        elif away:
            return self.away
        return None
        

class Team:
    def __init__(self, name: str, mascot: str, schedule_url: str):
        self.name = name
        self.mascot = mascot
        self._page = Page(schedule_url)
        self._soup = self._page.soup

    @property
    def page(self):
        return self._page
    
    @property
    def games(self):
        games_ = []
        for x in self._soup.find_all('div', {'class' : "CellGame"}):
            for y in x.find_all('a'):
                game_ref_match = re.match(r"/college-basketball/gametracker/recap/(.+)/", y['href'])
                if game_ref_match is not None:
                    games_.append(Game(game_ref_match.group(1)))
        return games_

class Box:
    def __init__(self):
        self._player_stats: dict[str, PlayerStats] = dict()

    def std_box(self, team: str):
        table = PrettyTable(["Name", "Pts", "FGM", "FGA", "FG%", "3PTM", "3PTA", "3PT%", "OReb", "DReb", "TReb", "Ast", "Stl", "Blk", "TO", "PF"])
        for name, stats in self._player_stats.items():
            table.add_row([name, stats.pts, stats.fgm, stats.fga, stats.fgpct, stats.fg3m, stats.fg3a, stats.fg3pct, stats.oreb, stats.dreb, stats.treb, stats.ast, stats.stl, stats.blk, stats.to, stats.pf])
        print(table)

    def from_game(self, game: Game):
        # TODO: add `Player` class
        for play in game.all_plays:
            players = play.players
            for player in players:
                if player not in self._player_stats:
                    self._player_stats[player] = PlayerStats(player)
                self._player_stats[player].from_play(play)

class BoxScore:
    pass

class Player:
    def __init__(self, name: str, team: Team):
        self._name = name
        self._team = team

    @property
    def name(self):
        return self._name
    
    @property
    def team(self):
        return self._team

class PlayerStats:
    def __init__(self, name: str):
        assert(name is not None)
        self._name = name
        self.pts: int = 0
        self.fgm: int = 0
        self.fga: int = 0
        self.ftm: int = 0
        self.fta: int = 0
        self.fg3m: int = 0
        self.fg3a: int = 0
        self.oreb: int = 0
        self.dreb: int = 0
        self.ast: int = 0
        self.stl: int = 0
        self.blk: int = 0
        self.pf: int = 0
        self.to: int = 0

    def from_play(self, play: Play):
        match play.type:
            case Play.Type.SHOT:
                if self.name == play.params['shooter']:
                    made = play.params['made']
                    if play.subtype == 'free throw':
                        self.fta += 1
                        if made:
                            self.ftm += 1
                    else:
                        self.fga += 1
                        if made:
                            self.fgm += 1
                        if play.subtype == 'three point':
                            self.fg3a += 1
                            if made:
                                self.fg3m += 1
                    self.pts += int(play.pts)
                elif self.name == play.params['assister']:
                    self.ast += 1
            case Play.Type.REB:
                if self.name == play.params['rebounder']:
                    if play.subtype == 'offensive':
                        self.oreb += 1
                    else:
                        self.dreb += 1
            case Play.Type.FOUL:
                if self.name == play.params['fouler']:
                    self.pf += 1
            case Play.Type.TO:
                if self.name == play.params['committer']:
                    self.to += 1
                elif self.name == play.params['stealer']:
                    self.stl += 1
            case Play.Type.BLK:
                if self.name == play.params['blocker']:
                    self.blk += 1
                elif self.name == play.params['shooter']:
                    self.fga += 1
                    if play.params['shot_type'] == 'three point':
                        self.fg3a += 1

    @property
    def name(self):
        return self._name
    
    @property
    def treb(self):
        return self.oreb + self.dreb
    
    @property
    def fgpct(self):
        if self.fga == 0:
            return 0.0
        return round(self.fgm / self.fga * 100, 1)

    @property
    def fg3pct(self):
        if self.fg3a == 0:
            return 0.0
        return round(self.fg3m / self.fg3a * 100, 1)

    @property
    def ftpct(self):
        if self.ft == 0:
            return 0.0
        return round(self.ftm / self.fta * 100, 1)

    @property
    def ie(self):
        """Individual efficiency."""
        return self.pts + self.fgm + self.ftm - self.fga - self.fta + self.dreb + self.oreb/2 + self.ast + self.stl + self.blk/2 - self.pf - self.to

    @property
    def ts(self):
        """True shooting percentage."""
        return self.pts / (2 * (self.fga + 0.44 * self.fta))