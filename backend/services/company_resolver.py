"""
Company name → LinkdAPI company ID resolver.

Two-step strategy:
  1. Try universal-name-to-id (fast, direct)
  2. Fall back to name-lookup autocomplete (fuzzy match)
Results are cached in the company registry for the session.

"""

from config.companies import (
    COMPANY_REGISTRY,
    get_company_id,
    get_universal_name,
    set_company_id,
)
from services.linkdapi_client import LinkdAPIClient
from utils.logger import get_logger

logger = get_logger(__name__)


async def resolve_company_id(
    client: LinkdAPIClient,
    company_name: str,
) -> int | None:
    """
    Resolve a company display name to its LinkdAPI integer ID.

    Strategy:
      1. Return cached ID if available.
      2. Try GET /companies/company/universal-name-to-id with the slug.
      3. Fall back to GET /companies/name-lookup for fuzzy search.

    Args:
        client: An initialized LinkdAPIClient.
        company_name: Display name from COMPANY_REGISTRY.

    Returns:
        Integer company ID, or None if resolution fails.
    """
    # Step 0: Check cache
    cached_id = get_company_id(company_name)
    if cached_id is not None:
        logger.info(f"Using cached ID for '{company_name}': {cached_id}")
        return cached_id

    # Step 1: Direct lookup by universal name
    universal_name = get_universal_name(company_name)
    if universal_name:
        company_id = await _resolve_by_universal_name(client, universal_name)
        if company_id:
            set_company_id(company_name, company_id)
            logger.info(
                f"Resolved '{company_name}' via universal name "
                f"'{universal_name}' → ID {company_id}"
            )
            return company_id

    # Step 2: Fuzzy search fallback
    company_id = await _resolve_by_name_lookup(client, company_name)
    if company_id:
        set_company_id(company_name, company_id)
        logger.info(f"Resolved '{company_name}' via name lookup → ID {company_id}")
        return company_id

    logger.error(f"Could not resolve company ID for '{company_name}'")
    return None


async def _resolve_by_universal_name(
    client: LinkdAPIClient,
    universal_name: str,
) -> int | None:
    """Try direct universal-name-to-id endpoint."""
    try:
        response = await client.get(
            "/companies/company/universal-name-to-id",
            params={"universalName": universal_name},
        )

        # The response structure may vary; try common patterns
        if isinstance(response, dict):
            # Try: { "data": { "id": 12345 } }
            data = response.get("data")
            if isinstance(data, dict) and "id" in data:
                return int(data["id"])
            # Try: { "data": 12345 }
            if isinstance(data, (int, str)):
                return int(data)
            # Try: { "id": 12345 }
            if "id" in response:
                return int(response["id"])

    except Exception as e:
        logger.warning(f"Universal name lookup failed for '{universal_name}': {e}")

    return None


async def _resolve_by_name_lookup(
    client: LinkdAPIClient,
    company_name: str,
) -> int | None:
    """Fall back to autocomplete-style name lookup."""
    try:
        response = await client.get(
            "/companies/name-lookup",
            params={"query": company_name},
        )

        if isinstance(response, dict):
            data = response.get("data", {})

            # Actual LinkdAPI format: { "data": { "companies": [ { "id": "...", "displayName": "..." } ] } }
            if isinstance(data, dict):
                companies = data.get("companies")
                if isinstance(companies, list) and companies:
                    first = companies[0]
                    if isinstance(first, dict) and "id" in first:
                        logger.info(
                            f"Name lookup matched: '{first.get('displayName', '?')}' "
                            f"(ID: {first['id']})"
                        )
                        return int(first["id"])

            # Fallback: data is a list directly
            if isinstance(data, list) and data:
                first = data[0]
                if isinstance(first, dict) and "id" in first:
                    logger.info(
                        f"Name lookup matched: '{first.get('name', '?')}' "
                        f"(ID: {first['id']})"
                    )
                    return int(first["id"])

    except Exception as e:
        logger.warning(f"Name lookup failed for '{company_name}': {e}")

    return None


async def resolve_all_companies(
    client: LinkdAPIClient,
) -> dict[str, int | None]:
    """
    Resolve IDs for all companies in the registry.

    Returns:
        Dict mapping company name → resolved ID (or None).
    """
    results = {}
    for name in COMPANY_REGISTRY:
        results[name] = await resolve_company_id(client, name)
    return results
