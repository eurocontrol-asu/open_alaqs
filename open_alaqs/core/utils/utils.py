import difflib
from datetime import datetime
from typing import Iterable, Optional


def fuzzy_match(search_term: str, values: Iterable[str]) -> Optional[str]:
    matched = difflib.get_close_matches(search_term, values, n=1)

    if matched:
        return matched[0]
    else:
        return None


def get_hours_in_year(year: int) -> int:
    td = datetime(year + 1, 1, 1, 0, 0, 0) - datetime(year, 1, 1, 0, 0, 0)
    return int(td.total_seconds() / 60 / 60)
