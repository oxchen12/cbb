import re
import typing
import logging
import urllib.request
from http.client import HTTPResponse
from bs4 import BeautifulSoup
from enum import Enum, auto

class Page:
    def __init__(self, url: str):
        self._url: str = url
        self._response: HTTPResponse = None
        self._soup: BeautifulSoup = None
        self._invalid: bool | None = None

    def __repr__(self):
        return f'Page(url={self.url})'

    @property
    def url(self):
        return self._url
    
    @property
    def invalid(self):
        return self._invalid

    @property
    def response(self):
        if self._response is None:
            try:
                self._response = urllib.request.urlopen(self._url)
            except urllib.error.HTTPError as e:
                self._invalid = True
                logging.warning(f'Page(url={self.url}) could not be resolved ({e.code}: {e.reason})')
            else:
                self._invalid = False
        return self._response
    
    @property
    def soup(self):
        if self.invalid:
            logging.warning('Page could not be resolved, can\'t parse HTML')
            return None
        if self._soup is None:
            html = str(self.response.read())
            self._soup = BeautifulSoup(html, 'html.parser')
        return self._soup
    
class GamePage(Page):
    URL_TEMPLATE = 'https://www.espn.com/mens-college-basketball/{}/_/gameId/{}'

    class Category(Enum):
        GAMECAST = auto()
        RECAP = auto()
        BOX = auto()
        PLAYS = auto()
    
    def __init__(self, gid: typing.Union[str, int]):
        gid = str(gid)
        assert(re.match(r'^\d*$', gid))
        self._gid: str = gid
        self._recap = None
        self._box = None
        self._plays = None
        Page.__init__(self, GamePage.URL_TEMPLATE.format('game', self.gid))
    
    def __repr__(self):
        return f'GamePage(gid={self._gid})'
    
    def _get_url(self, category: Category = Category.PLAYS):
        dest = None
        match category:
            case GamePage.Category.GAMECAST:
                dest = 'game'
            case GamePage.Category.RECAP:
                dest = 'recap'
            case GamePage.Category.BOX:
                dest = 'boxscore'
            case GamePage.Category.PLAYS:
                dest = 'playbyplay'
        if dest is not None:
            return GamePage.URL_TEMPLATE.format(dest, self.gid)
        return None
    
    @property
    def gid(self):
        return self._gid
    
    @property
    def recap(self):
        if self._recap is None:
            self._recap = Page(self._get_url(category=GamePage.Category.RECAP))
        return self._recap

    @property
    def boxscore(self):
        if self._box is None:
            self._box = Page(self._get_url(category=GamePage.Category.BOX))
        return self._box

    @property
    def plays(self):
        if self._plays is None:
            self._plays = Page(self._get_url(category=GamePage.Category.PLAYS))
        return self._plays
