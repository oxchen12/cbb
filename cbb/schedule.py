"""schedule.py: Module for fetching schedule data for teams."""

import re
import logging
from typing import Union
from .webscraper import Page


def get_schedule_gids(tid: Union[str, int], year: int):
    """Retrieves the gid's for a team's games in the given athletic year"""
    tid = str(tid)
    url = f'https://www.espn.com/mens-college-basketball/team/schedule/_/id/{tid}/season/{year}'
    page = Page(url)
    selector = page.soup.select('tr[data-idx] a[class=AnchorLink][href*=\/game\/]')  # filters html data for game urls
    out = [re.search(r'\d+', str(g))[0] for g in selector]
    if len(out) == 0:
        logging.warning("No games found, check tid and year")
    return out
