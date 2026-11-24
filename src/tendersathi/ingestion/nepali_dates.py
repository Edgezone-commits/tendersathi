"""Convert Bikram Sambat (BS) dates, as found in Nepali bid documents, to AD.

Nepali government tenders date everything in the Bikram Sambat calendar,
sometimes alongside an AD date in parentheses, sometimes not. The Scout
agent only asks the LLM to transcribe whichever date string is in the
document; LLMs are unreliable at calendar arithmetic, so the actual BS -> AD
conversion happens here, deterministically, via the `nepali_datetime`
package.
"""

from __future__ import annotations

import re
from datetime import date

import nepali_datetime

_BS_DATE_PATTERN = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})\s*$")


class InvalidBsDateError(ValueError):
    """Raised when a string isn't a valid 'YYYY-MM-DD' Bikram Sambat date."""


def bs_to_ad(value: str) -> date:
    """Convert a 'YYYY-MM-DD' Bikram Sambat date string to an AD `date`."""
    match = _BS_DATE_PATTERN.match(value)
    if not match:
        raise InvalidBsDateError(f"{value!r} is not a 'YYYY-MM-DD' Bikram Sambat date")

    year, month, day = (int(part) for part in match.groups())
    try:
        bs_date = nepali_datetime.date(year, month, day)
    except ValueError as error:
        raise InvalidBsDateError(f"{value!r} is not a valid Bikram Sambat date") from error

    return bs_date.to_datetime_date()
