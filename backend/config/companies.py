"""
Target company registry.

Maps display names to LinkedIn universal names (slugs).
Add new companies here — the rest of the pipeline picks them up automatically.
"""

COMPANY_REGISTRY: dict[str, dict] = {
    "Vanguard India": {
        "universal_name": "vanguard-india",
        "id": 108291840,  # confirmed via API
    },
    "Chubb": {
        "universal_name": "chubb",
        "id": 1269,  # parent company (no India-specific page)
    },
    "HCA Healthcare India": {
        "universal_name": "hca-healthcare-india",
        "id": 107604798,
    },
    "The Hartford India": {
        "universal_name": "the-hartford",
        "id": 2467,
    },
    "Lloyds Technology Centre India": {
        "universal_name": "lloyds-technology-centre-india",
        "id": 98085562,  # confirmed via API
    },
    "Carelon Global Solutions India": {
        "universal_name": "carelon-global-solutions-in",
        "id": 91669706,
    },
}


def get_all_company_names() -> list[str]:
    """Return all registered company display names."""
    return list(COMPANY_REGISTRY.keys())


def get_universal_name(company_name: str) -> str | None:
    """Return the LinkedIn universal name for a company."""
    entry = COMPANY_REGISTRY.get(company_name)
    return entry["universal_name"] if entry else None


def set_company_id(company_name: str, company_id: int) -> None:
    """Cache a resolved company ID."""
    if company_name in COMPANY_REGISTRY:
        COMPANY_REGISTRY[company_name]["id"] = company_id


def get_company_id(company_name: str) -> int | None:
    """Return cached company ID if available."""
    entry = COMPANY_REGISTRY.get(company_name)
    return entry["id"] if entry else None
