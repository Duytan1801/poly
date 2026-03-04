"""
Shared constants and utilities for scoring and analysis.
"""

CATEGORY_PRIORITY = {
    "tech": 5.0,
    "technology": 5.0,
    "business": 4.0,
    "finance": 4.0,
    "economy": 4.0,
    "federal reserve": 4.0,
    "fed": 4.0,
    "geopolitics": 3.0,
    "politics": 2.5,
    "election": 2.5,
    "president": 2.5,
    "crypto": 1.5,
    "bitcoin": 1.5,
    "ethereum": 1.5,
    "sports": 1.0,
    "entertainment": 1.0,
}


def categorize_market(
    question: str, group_title: str = "", category: str = ""
) -> float:
    """Categorize market and return insider risk score (0-5)."""
    text = f"{question} {group_title} {category}".lower()

    for keywords, score in CATEGORY_PRIORITY.items():
        if keywords in text:
            return score

    return 1.0
