from typing import Tuple


def normalize_paging(page: int, page_size: int, max_page_size: int = 100) -> Tuple[int, int]:
    p = page if page and page > 0 else 1
    ps = page_size if page_size and page_size > 0 else 20
    ps = min(ps, max_page_size)
    return p, ps


