import difflib
from typing import Iterable, Optional


def fuzzy_match(search_term: str, values: Iterable[str]) -> Optional[str]:
    matched = difflib.get_close_matches(search_term, values, n=1)

    if matched:
        return matched[0]
    else:
        return None
