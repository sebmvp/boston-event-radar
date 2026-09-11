from __future__ import annotations

import re


def has_term(blob: str, term: str) -> bool:
    """Match topic terms without 'ai' hitting 'fair' or 'said'."""
    blob_l = blob.lower()
    term_l = term.lower().strip()
    if not term_l:
        return False
    if " " in term_l or len(term_l) > 4:
        return term_l in blob_l
    return re.search(rf"(?<![a-z0-9]){re.escape(term_l)}(?![a-z0-9])", blob_l) is not None
