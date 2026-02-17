# SPDX-License-Identifier: Apache-2.0
"""
DOI metadata fetching via CrossRef and DataCite APIs.

Zenodo DOIs (10.5281/zenodo.*) use DataCite.
Most other DOIs use CrossRef.
"""

import json
import re
import urllib.request
import urllib.error
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .types import Source, Author, SourceType


# DOI prefix for Zenodo
ZENODO_PREFIX = "10.5281"

# API endpoints
CROSSREF_API = "https://api.crossref.org/works"
DATACITE_API = "https://api.datacite.org/dois"


@dataclass
class DOIMetadata:
    """Raw metadata fetched from DOI resolver."""

    doi: str
    title: str
    authors: list[dict[str, str]]
    abstract: str | None
    year: int | None
    venue: str | None
    url: str | None
    raw_response: dict[str, Any] | None = None


class DOIFetchError(Exception):
    """Error fetching DOI metadata."""

    def __init__(self, doi: str, message: str):
        self.doi = doi
        super().__init__(f"Error fetching DOI {doi}: {message}")


def normalize_doi(doi: str) -> str:
    """
    Normalize a DOI to just the identifier.

    Handles:
    - https://doi.org/10.1234/example
    - doi:10.1234/example
    - 10.1234/example
    """
    doi = doi.strip()

    # Remove URL prefix
    if doi.startswith("https://doi.org/"):
        doi = doi[16:]
    elif doi.startswith("http://doi.org/"):
        doi = doi[15:]
    elif doi.startswith("doi:"):
        doi = doi[4:]

    return doi


def is_zenodo_doi(doi: str) -> bool:
    """Check if DOI is from Zenodo (uses DataCite)."""
    normalized = normalize_doi(doi)
    return normalized.startswith(ZENODO_PREFIX)


def _fetch_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """Fetch JSON from URL."""
    req_headers = {
        "Accept": "application/json",
        "User-Agent": "NonfictionGovernor/0.1 (https://github.com/unpingable/agent_governor)",
    }
    if headers:
        req_headers.update(headers)

    request = urllib.request.Request(url, headers=req_headers)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise DOIFetchError(url, "DOI not found")
        raise DOIFetchError(url, f"HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise DOIFetchError(url, f"Network error: {e.reason}")


def fetch_from_crossref(doi: str) -> DOIMetadata:
    """Fetch metadata from CrossRef API."""
    normalized = normalize_doi(doi)
    url = f"{CROSSREF_API}/{normalized}"

    data = _fetch_json(url)
    work = data.get("message", {})

    # Extract authors
    authors = []
    for author in work.get("author", []):
        name_parts = []
        if author.get("given"):
            name_parts.append(author["given"])
        if author.get("family"):
            name_parts.append(author["family"])
        if name_parts:
            authors.append({
                "name": " ".join(name_parts),
                "orcid": author.get("ORCID"),
                "affiliation": author.get("affiliation", [{}])[0].get("name") if author.get("affiliation") else None,
            })

    # Extract title
    title = ""
    titles = work.get("title", [])
    if titles:
        title = titles[0]

    # Extract year
    year = None
    published = work.get("published-print") or work.get("published-online") or work.get("created")
    if published and "date-parts" in published:
        date_parts = published["date-parts"]
        if date_parts and date_parts[0]:
            year = date_parts[0][0]

    # Extract venue
    venue = None
    container = work.get("container-title", [])
    if container:
        venue = container[0]

    # Extract abstract
    abstract = work.get("abstract")
    if abstract:
        # Clean up JATS XML tags if present
        abstract = re.sub(r"<[^>]+>", "", abstract)

    return DOIMetadata(
        doi=normalized,
        title=title,
        authors=authors,
        abstract=abstract,
        year=year,
        venue=venue,
        url=work.get("URL"),
        raw_response=work,
    )


def fetch_from_datacite(doi: str) -> DOIMetadata:
    """Fetch metadata from DataCite API (for Zenodo, etc.)."""
    normalized = normalize_doi(doi)
    url = f"{DATACITE_API}/{normalized}"

    data = _fetch_json(url)
    attrs = data.get("data", {}).get("attributes", {})

    # Extract authors
    authors = []
    for creator in attrs.get("creators", []):
        name = creator.get("name", "")
        # DataCite often has "Family, Given" format
        if "," in name and not creator.get("givenName"):
            parts = name.split(",", 1)
            name = f"{parts[1].strip()} {parts[0].strip()}"
        elif creator.get("givenName") and creator.get("familyName"):
            name = f"{creator['givenName']} {creator['familyName']}"

        authors.append({
            "name": name,
            "orcid": None,  # DataCite has nameIdentifiers but more complex
            "affiliation": creator.get("affiliation", [{}])[0].get("name") if creator.get("affiliation") else None,
        })

    # Extract title
    title = ""
    titles = attrs.get("titles", [])
    if titles:
        title = titles[0].get("title", "")

    # Extract year
    year = attrs.get("publicationYear")

    # Extract venue/publisher
    venue = attrs.get("publisher")

    # Extract abstract
    abstract = None
    descriptions = attrs.get("descriptions", [])
    for desc in descriptions:
        if desc.get("descriptionType") == "Abstract":
            abstract = desc.get("description")
            break

    return DOIMetadata(
        doi=normalized,
        title=title,
        authors=authors,
        abstract=abstract,
        year=year,
        venue=venue,
        url=attrs.get("url"),
        raw_response=attrs,
    )


def fetch_doi_metadata(doi: str) -> DOIMetadata:
    """
    Fetch metadata for a DOI.

    Automatically routes to CrossRef or DataCite based on DOI prefix.
    """
    if is_zenodo_doi(doi):
        return fetch_from_datacite(doi)
    else:
        return fetch_from_crossref(doi)


def metadata_to_source(
    metadata: DOIMetadata,
    source_type: SourceType = SourceType.EXTERNAL,
    citation_key: str | None = None,
) -> Source:
    """Convert DOI metadata to a Source object."""
    authors = [
        Author(
            name=a["name"],
            orcid=a.get("orcid"),
            affiliation=a.get("affiliation"),
        )
        for a in metadata.authors
    ]

    return Source(
        doi=metadata.doi,
        url=metadata.url,
        title=metadata.title,
        authors=authors,
        abstract=metadata.abstract,
        year=metadata.year,
        venue=metadata.venue,
        citation_key=citation_key,
        source_type=source_type,
        fetched_at=datetime.now(timezone.utc),
    )


def fetch_source(
    doi: str,
    canonical: bool = False,
    citation_key: str | None = None,
) -> Source:
    """
    Fetch a Source from DOI.

    Args:
        doi: The DOI to fetch
        canonical: Whether this is a canonical (your own) source
        citation_key: Optional override for citation key

    Returns:
        Source object with fetched metadata
    """
    metadata = fetch_doi_metadata(doi)
    source_type = SourceType.CANONICAL if canonical else SourceType.EXTERNAL
    return metadata_to_source(metadata, source_type, citation_key)


def extract_zenodo_id(doi: str) -> str | None:
    """Extract Zenodo record ID from DOI."""
    normalized = normalize_doi(doi)
    if not normalized.startswith(ZENODO_PREFIX):
        return None

    # Format: 10.5281/zenodo.1234567
    match = re.search(r"zenodo\.(\d+)", normalized)
    if match:
        return match.group(1)
    return None
