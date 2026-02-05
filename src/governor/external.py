"""External Constraint Attachment — bind claims to external substrate snapshots.

This is NOT fact verification. It is structural logging of what the system
believed vs what external substrates reported at specific moments.

Core principle: Mismatch between claim and external state is a SIGNAL,
not an error. You don't "fix" disagreement — you surface it and ledger it.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Protocol
import hashlib
import json
import urllib.request
import urllib.parse
import urllib.error


def _utcnow() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# -----------------------------------------------------------------------------
# Enums
# -----------------------------------------------------------------------------


class Volatility(str, Enum):
    """How often the external source changes."""

    IMMUTABLE = "immutable"  # DOIs, archived pages
    STABLE = "stable"  # Wikidata, peer-reviewed
    DYNAMIC = "dynamic"  # Wikipedia, news
    EPHEMERAL = "ephemeral"  # Social media, live APIs


class AuthorityType(str, Enum):
    """What kind of authority the source represents."""

    INSTITUTIONAL = "institutional"  # Journal, government
    CROWD = "crowd"  # Wikipedia, Stack Overflow
    ALGORITHMIC = "algorithmic"  # Search results, embeddings
    PRIMARY = "primary"  # Original source


class BindingType(str, Enum):
    """How the external state relates to the claim."""

    SUPPORTS = "supports"  # External state aligns with claim
    CONTRADICTS = "contradicts"  # External state conflicts
    TANGENTIAL = "tangential"  # Related but not directly relevant
    SILENT = "silent"  # External source has no information


class Resolution(str, Enum):
    """How a discrepancy was resolved."""

    CLAIM_UPDATED = "claim_updated"  # Human revised claim
    CLAIM_RETAINED = "claim_retained"  # Human kept claim despite contradiction
    SUBSTRATE_STALE = "substrate_stale"  # Substrate was out of date
    CONTEXT_DIFFERS = "context_differs"  # Different contexts, both valid
    PENDING = "pending"  # Not yet resolved


# -----------------------------------------------------------------------------
# Trust Profiles
# -----------------------------------------------------------------------------


@dataclass
class TrustProfile:
    """How to interpret responses from a substrate."""

    volatility: Volatility
    authority_type: AuthorityType
    citation_required: bool = True
    snapshot_ttl: timedelta = field(default_factory=lambda: timedelta(hours=24))

    def to_dict(self) -> dict:
        return {
            "volatility": self.volatility.value,
            "authority_type": self.authority_type.value,
            "citation_required": self.citation_required,
            "snapshot_ttl_seconds": self.snapshot_ttl.total_seconds(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TrustProfile":
        return cls(
            volatility=Volatility(data["volatility"]),
            authority_type=AuthorityType(data["authority_type"]),
            citation_required=data.get("citation_required", True),
            snapshot_ttl=timedelta(seconds=data.get("snapshot_ttl_seconds", 86400)),
        )


# Default trust profiles for known substrates
TRUST_PROFILES: dict[str, TrustProfile] = {
    "wikidata": TrustProfile(
        volatility=Volatility.STABLE,
        authority_type=AuthorityType.CROWD,
        citation_required=True,
        snapshot_ttl=timedelta(days=7),
    ),
    "wikipedia": TrustProfile(
        volatility=Volatility.DYNAMIC,
        authority_type=AuthorityType.CROWD,
        citation_required=True,
        snapshot_ttl=timedelta(hours=24),
    ),
    "scholar": TrustProfile(
        volatility=Volatility.STABLE,
        authority_type=AuthorityType.INSTITUTIONAL,
        citation_required=True,
        snapshot_ttl=timedelta(days=30),
    ),
    "archive": TrustProfile(
        volatility=Volatility.IMMUTABLE,
        authority_type=AuthorityType.PRIMARY,
        citation_required=True,
        snapshot_ttl=timedelta(days=365),
    ),
}


# -----------------------------------------------------------------------------
# Core Data Types
# -----------------------------------------------------------------------------


@dataclass
class SubstrateSnapshot:
    """Immutable record of external state at query time."""

    snapshot_id: str
    substrate_id: str
    query: str
    response: str
    queried_at: datetime
    response_hash: str
    affordance_used: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "substrate_id": self.substrate_id,
            "query": self.query,
            "response": self.response,
            "queried_at": self.queried_at.isoformat(),
            "response_hash": self.response_hash,
            "affordance_used": self.affordance_used,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubstrateSnapshot":
        return cls(
            snapshot_id=data["snapshot_id"],
            substrate_id=data["substrate_id"],
            query=data["query"],
            response=data["response"],
            queried_at=datetime.fromisoformat(data["queried_at"]),
            response_hash=data["response_hash"],
            affordance_used=data["affordance_used"],
            metadata=data.get("metadata", {}),
        )


@dataclass
class ConstraintBinding:
    """Binding between a claim and external snapshot."""

    binding_id: str
    claim_id: str
    snapshot_id: str
    binding_type: BindingType
    delta_t: timedelta  # Time between claim and query
    notes: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "binding_id": self.binding_id,
            "claim_id": self.claim_id,
            "snapshot_id": self.snapshot_id,
            "binding_type": self.binding_type.value,
            "delta_t_seconds": self.delta_t.total_seconds(),
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConstraintBinding":
        return cls(
            binding_id=data["binding_id"],
            claim_id=data["claim_id"],
            snapshot_id=data["snapshot_id"],
            binding_type=BindingType(data["binding_type"]),
            delta_t=timedelta(seconds=data["delta_t_seconds"]),
            notes=data.get("notes"),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class Discrepancy:
    """Record of claim-substrate mismatch."""

    discrepancy_id: str
    claim_id: str
    binding_id: str
    claim_value: str
    substrate_value: str
    delta_t: timedelta
    resolution: Resolution = Resolution.PENDING
    resolution_reason: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "discrepancy_id": self.discrepancy_id,
            "claim_id": self.claim_id,
            "binding_id": self.binding_id,
            "claim_value": self.claim_value,
            "substrate_value": self.substrate_value,
            "delta_t_seconds": self.delta_t.total_seconds(),
            "resolution": self.resolution.value,
            "resolution_reason": self.resolution_reason,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Discrepancy":
        return cls(
            discrepancy_id=data["discrepancy_id"],
            claim_id=data["claim_id"],
            binding_id=data["binding_id"],
            claim_value=data["claim_value"],
            substrate_value=data["substrate_value"],
            delta_t=timedelta(seconds=data["delta_t_seconds"]),
            resolution=Resolution(data["resolution"]),
            resolution_reason=data.get("resolution_reason"),
            resolved_at=(
                datetime.fromisoformat(data["resolved_at"])
                if data.get("resolved_at")
                else None
            ),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


# -----------------------------------------------------------------------------
# Substrate Protocol and Implementations
# -----------------------------------------------------------------------------


class ExternalSubstrate(Protocol):
    """Protocol for external data sources."""

    substrate_id: str
    trust_profile: TrustProfile

    def query(self, query: str, affordance: str | None = None) -> SubstrateSnapshot:
        """Query the substrate and return an immutable snapshot."""
        ...

    def available_affordances(self) -> list[str]:
        """Return list of query affordances this substrate supports."""
        ...


def _generate_id(prefix: str) -> str:
    """Generate a unique ID with prefix."""
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _hash_response(response: str) -> str:
    """SHA-256 hash of response content."""
    return hashlib.sha256(response.encode("utf-8")).hexdigest()


class WikidataSubstrate:
    """Structured knowledge graph queries via Wikidata API."""

    substrate_id: str = "wikidata"
    trust_profile: TrustProfile = TRUST_PROFILES["wikidata"]

    WIKIDATA_API = "https://www.wikidata.org/w/api.php"

    def available_affordances(self) -> list[str]:
        return ["entity", "claim", "search"]

    def query(self, query: str, affordance: str | None = None) -> SubstrateSnapshot:
        """Query Wikidata.

        Args:
            query: Q-ID (e.g., "Q42") for entity/claim, or search string
            affordance: "entity", "claim", or "search"
        """
        affordance = affordance or "entity"
        queried_at = _utcnow()

        if affordance == "entity":
            response = self._query_entity(query)
        elif affordance == "search":
            response = self._search_entity(query)
        else:
            response = self._query_entity(query)

        response_str = json.dumps(response, ensure_ascii=False, indent=2)

        return SubstrateSnapshot(
            snapshot_id=_generate_id("snap"),
            substrate_id=self.substrate_id,
            query=query,
            response=response_str,
            queried_at=queried_at,
            response_hash=_hash_response(response_str),
            affordance_used=affordance,
            metadata={"api_version": "wbgetentities"},
        )

    def _query_entity(self, qid: str) -> dict:
        """Get entity by Q-ID."""
        params = {
            "action": "wbgetentities",
            "ids": qid,
            "format": "json",
            "languages": "en",
        }
        return self._make_request(params)

    def _search_entity(self, label: str) -> dict:
        """Search for entity by label."""
        params = {
            "action": "wbsearchentities",
            "search": label,
            "format": "json",
            "language": "en",
            "limit": 10,
        }
        return self._make_request(params)

    def _make_request(self, params: dict) -> dict:
        """Make HTTP request to Wikidata API."""
        url = f"{self.WIKIDATA_API}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AgentGovernor/1.0 (external constraint binding)"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            return {"error": str(e), "query": params}
        except Exception as e:
            return {"error": str(e), "query": params}


class WikipediaSubstrate:
    """Article content queries via Wikipedia API."""

    substrate_id: str = "wikipedia"
    trust_profile: TrustProfile = TRUST_PROFILES["wikipedia"]

    WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

    def available_affordances(self) -> list[str]:
        return ["article", "section", "revision"]

    def query(self, query: str, affordance: str | None = None) -> SubstrateSnapshot:
        """Query Wikipedia.

        Args:
            query: Article title, or "title|section" for section, or "title|revid" for revision
            affordance: "article", "section", or "revision"
        """
        affordance = affordance or "article"
        queried_at = _utcnow()

        if affordance == "revision" and "|" in query:
            title, rev_id = query.rsplit("|", 1)
            response = self._query_revision(title, int(rev_id))
        elif affordance == "section" and "|" in query:
            title, section = query.rsplit("|", 1)
            response = self._query_section(title, section)
        else:
            response = self._query_article(query)

        response_str = json.dumps(response, ensure_ascii=False, indent=2)

        return SubstrateSnapshot(
            snapshot_id=_generate_id("snap"),
            substrate_id=self.substrate_id,
            query=query,
            response=response_str,
            queried_at=queried_at,
            response_hash=_hash_response(response_str),
            affordance_used=affordance,
            metadata={"language": "en"},
        )

    def _query_article(self, title: str) -> dict:
        """Get article extract by title."""
        params = {
            "action": "query",
            "titles": title,
            "prop": "extracts|revisions",
            "exintro": "true",
            "explaintext": "true",
            "rvprop": "ids|timestamp",
            "format": "json",
        }
        return self._make_request(params)

    def _query_section(self, title: str, section: str) -> dict:
        """Get specific section of article."""
        params = {
            "action": "parse",
            "page": title,
            "section": section,
            "prop": "text|revid",
            "format": "json",
        }
        return self._make_request(params)

    def _query_revision(self, title: str, rev_id: int) -> dict:
        """Get specific revision (immutable)."""
        params = {
            "action": "query",
            "titles": title,
            "prop": "revisions",
            "rvprop": "content|ids|timestamp",
            "rvlimit": "1",
            "rvstartid": str(rev_id),
            "rvendid": str(rev_id),
            "format": "json",
        }
        return self._make_request(params)

    def _make_request(self, params: dict) -> dict:
        """Make HTTP request to Wikipedia API."""
        url = f"{self.WIKIPEDIA_API}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "AgentGovernor/1.0 (external constraint binding)"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            return {"error": str(e), "query": params}
        except Exception as e:
            return {"error": str(e), "query": params}


class ScholarSubstrate:
    """Academic paper metadata queries.

    Note: Uses CrossRef/DataCite APIs for DOI resolution.
    Google Scholar has no public API.
    """

    substrate_id: str = "scholar"
    trust_profile: TrustProfile = TRUST_PROFILES["scholar"]

    CROSSREF_API = "https://api.crossref.org/works"
    DATACITE_API = "https://api.datacite.org/dois"

    def available_affordances(self) -> list[str]:
        return ["doi", "search"]

    def query(self, query: str, affordance: str | None = None) -> SubstrateSnapshot:
        """Query academic databases.

        Args:
            query: DOI (e.g., "10.1000/xyz123") or search string
            affordance: "doi" or "search"
        """
        affordance = affordance or "doi"
        queried_at = _utcnow()

        if affordance == "doi":
            response = self._query_doi(query)
        else:
            response = self._search_papers(query)

        response_str = json.dumps(response, ensure_ascii=False, indent=2)

        return SubstrateSnapshot(
            snapshot_id=_generate_id("snap"),
            substrate_id=self.substrate_id,
            query=query,
            response=response_str,
            queried_at=queried_at,
            response_hash=_hash_response(response_str),
            affordance_used=affordance,
            metadata={"source": "crossref"},
        )

    def _query_doi(self, doi: str) -> dict:
        """Get paper metadata by DOI."""
        # Clean DOI
        doi = doi.strip()
        if doi.startswith("https://doi.org/"):
            doi = doi[16:]
        elif doi.startswith("doi:"):
            doi = doi[4:]

        url = f"{self.CROSSREF_API}/{urllib.parse.quote(doi, safe='')}"
        return self._make_request(url)

    def _search_papers(self, query: str) -> dict:
        """Search for papers."""
        params = {"query": query, "rows": 10}
        url = f"{self.CROSSREF_API}?{urllib.parse.urlencode(params)}"
        return self._make_request(url)

    def _make_request(self, url: str) -> dict:
        """Make HTTP request."""
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "AgentGovernor/1.0 (mailto:governor@example.com)",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            return {"error": str(e), "url": url}
        except Exception as e:
            return {"error": str(e), "url": url}


# -----------------------------------------------------------------------------
# Substrate Registry
# -----------------------------------------------------------------------------


SUBSTRATES: dict[str, ExternalSubstrate] = {
    "wikidata": WikidataSubstrate(),
    "wikipedia": WikipediaSubstrate(),
    "scholar": ScholarSubstrate(),
}


def get_substrate(substrate_id: str) -> ExternalSubstrate | None:
    """Get substrate by ID."""
    return SUBSTRATES.get(substrate_id)


def list_substrates() -> list[str]:
    """List available substrate IDs."""
    return list(SUBSTRATES.keys())


# -----------------------------------------------------------------------------
# Constraint Manager
# -----------------------------------------------------------------------------


class ConstraintManager:
    """Manages external constraint bindings and discrepancies.

    This is the main interface for attaching external constraints to claims.
    """

    def __init__(self):
        self._snapshots: dict[str, SubstrateSnapshot] = {}
        self._bindings: dict[str, ConstraintBinding] = {}
        self._discrepancies: dict[str, Discrepancy] = {}
        self._claim_bindings: dict[str, list[str]] = {}  # claim_id -> binding_ids

    # Temporal thresholds
    MAX_BINDING_AGE = timedelta(hours=24)
    RETROACTIVE_THRESHOLD = timedelta(days=7)

    def query_substrate(
        self,
        substrate_id: str,
        query: str,
        affordance: str | None = None,
    ) -> SubstrateSnapshot:
        """Query a substrate and store the snapshot."""
        substrate = get_substrate(substrate_id)
        if not substrate:
            raise ValueError(f"Unknown substrate: {substrate_id}")

        snapshot = substrate.query(query, affordance)
        self._snapshots[snapshot.snapshot_id] = snapshot
        return snapshot

    def bind_constraint(
        self,
        claim_id: str,
        snapshot_id: str,
        binding_type: BindingType,
        claim_created_at: datetime,
        claim_value: str | None = None,
        notes: str | None = None,
    ) -> ConstraintBinding:
        """Bind a snapshot to a claim.

        Args:
            claim_id: ID of the claim to bind
            snapshot_id: ID of the snapshot to bind
            binding_type: How the snapshot relates to the claim
            claim_created_at: When the claim was created
            claim_value: Optional claim value for discrepancy tracking
            notes: Optional notes about the binding

        Returns:
            The created binding
        """
        snapshot = self._snapshots.get(snapshot_id)
        if not snapshot:
            raise ValueError(f"Unknown snapshot: {snapshot_id}")

        delta_t = snapshot.queried_at - claim_created_at

        binding = ConstraintBinding(
            binding_id=_generate_id("bind"),
            claim_id=claim_id,
            snapshot_id=snapshot_id,
            binding_type=binding_type,
            delta_t=delta_t,
            notes=notes,
        )

        self._bindings[binding.binding_id] = binding

        if claim_id not in self._claim_bindings:
            self._claim_bindings[claim_id] = []
        self._claim_bindings[claim_id].append(binding.binding_id)

        # If contradiction, create discrepancy record
        if binding_type == BindingType.CONTRADICTS and claim_value is not None:
            self._create_discrepancy(
                claim_id=claim_id,
                binding_id=binding.binding_id,
                claim_value=claim_value,
                substrate_value=snapshot.response[:500],  # Truncate for storage
                delta_t=delta_t,
            )

        return binding

    def attach_constraint(
        self,
        claim_id: str,
        claim_created_at: datetime,
        claim_value: str,
        substrate_id: str,
        query: str,
        affordance: str | None = None,
    ) -> tuple[SubstrateSnapshot, ConstraintBinding]:
        """Query substrate and bind result to claim in one step.

        This is the primary interface for external constraint attachment.
        """
        snapshot = self.query_substrate(substrate_id, query, affordance)

        # Classify binding type (simple heuristic - real impl would be smarter)
        binding_type = self._classify_binding(claim_value, snapshot.response)

        binding = self.bind_constraint(
            claim_id=claim_id,
            snapshot_id=snapshot.snapshot_id,
            binding_type=binding_type,
            claim_created_at=claim_created_at,
            claim_value=claim_value,
        )

        return snapshot, binding

    def _classify_binding(self, claim_value: str, substrate_response: str) -> BindingType:
        """Classify how substrate response relates to claim.

        This is a simple heuristic. Real implementation would use
        semantic similarity, entity matching, etc.
        """
        response_lower = substrate_response.lower()
        claim_lower = claim_value.lower()

        # Check for error responses
        if '"error"' in response_lower:
            return BindingType.SILENT

        # Very basic: check if claim terms appear in response
        claim_terms = set(claim_lower.split())
        significant_terms = {t for t in claim_terms if len(t) > 3}

        if not significant_terms:
            return BindingType.TANGENTIAL

        matches = sum(1 for t in significant_terms if t in response_lower)
        match_ratio = matches / len(significant_terms) if significant_terms else 0

        if match_ratio > 0.5:
            return BindingType.SUPPORTS
        elif match_ratio > 0.2:
            return BindingType.TANGENTIAL
        else:
            return BindingType.SILENT

    def _create_discrepancy(
        self,
        claim_id: str,
        binding_id: str,
        claim_value: str,
        substrate_value: str,
        delta_t: timedelta,
    ) -> Discrepancy:
        """Create a discrepancy record."""
        discrepancy = Discrepancy(
            discrepancy_id=_generate_id("disc"),
            claim_id=claim_id,
            binding_id=binding_id,
            claim_value=claim_value,
            substrate_value=substrate_value,
            delta_t=delta_t,
        )
        self._discrepancies[discrepancy.discrepancy_id] = discrepancy
        return discrepancy

    def resolve_discrepancy(
        self,
        discrepancy_id: str,
        resolution: Resolution,
        reason: str,
    ) -> Discrepancy:
        """Resolve a discrepancy (human action required).

        The governor NEVER auto-resolves discrepancies. This must be
        called by human action.
        """
        discrepancy = self._discrepancies.get(discrepancy_id)
        if not discrepancy:
            raise ValueError(f"Unknown discrepancy: {discrepancy_id}")

        if discrepancy.resolution != Resolution.PENDING:
            raise ValueError(f"Discrepancy already resolved: {discrepancy_id}")

        discrepancy.resolution = resolution
        discrepancy.resolution_reason = reason
        discrepancy.resolved_at = _utcnow()

        return discrepancy

    def get_bindings(self, claim_id: str) -> list[ConstraintBinding]:
        """Get all bindings for a claim."""
        binding_ids = self._claim_bindings.get(claim_id, [])
        return [self._bindings[bid] for bid in binding_ids if bid in self._bindings]

    def get_snapshot(self, snapshot_id: str) -> SubstrateSnapshot | None:
        """Get a snapshot by ID."""
        return self._snapshots.get(snapshot_id)

    def get_discrepancies(
        self,
        status: Resolution | None = None,
    ) -> list[Discrepancy]:
        """Get discrepancies, optionally filtered by status."""
        discrepancies = list(self._discrepancies.values())
        if status is not None:
            discrepancies = [d for d in discrepancies if d.resolution == status]
        return discrepancies

    def get_discrepancy(self, discrepancy_id: str) -> Discrepancy | None:
        """Get a discrepancy by ID."""
        return self._discrepancies.get(discrepancy_id)

    def check_binding_freshness(self, binding: ConstraintBinding) -> dict:
        """Check if a binding is fresh enough.

        Returns dict with:
        - fresh: bool
        - age: timedelta
        - warnings: list[str]
        """
        snapshot = self._snapshots.get(binding.snapshot_id)
        if not snapshot:
            return {"fresh": False, "age": None, "warnings": ["Snapshot not found"]}

        age = _utcnow() - snapshot.queried_at
        warnings = []

        if age > self.MAX_BINDING_AGE:
            warnings.append(f"Snapshot older than {self.MAX_BINDING_AGE}")

        if binding.delta_t > self.RETROACTIVE_THRESHOLD:
            warnings.append(f"Retroactive binding: claim predates query by {binding.delta_t}")

        return {
            "fresh": age <= self.MAX_BINDING_AGE,
            "age": age,
            "warnings": warnings,
        }

    def to_dict(self) -> dict:
        """Serialize manager state."""
        return {
            "snapshots": {k: v.to_dict() for k, v in self._snapshots.items()},
            "bindings": {k: v.to_dict() for k, v in self._bindings.items()},
            "discrepancies": {k: v.to_dict() for k, v in self._discrepancies.items()},
            "claim_bindings": self._claim_bindings,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ConstraintManager":
        """Deserialize manager state."""
        manager = cls()
        manager._snapshots = {
            k: SubstrateSnapshot.from_dict(v) for k, v in data.get("snapshots", {}).items()
        }
        manager._bindings = {
            k: ConstraintBinding.from_dict(v) for k, v in data.get("bindings", {}).items()
        }
        manager._discrepancies = {
            k: Discrepancy.from_dict(v) for k, v in data.get("discrepancies", {}).items()
        }
        manager._claim_bindings = data.get("claim_bindings", {})
        return manager


# -----------------------------------------------------------------------------
# Module-level convenience functions
# -----------------------------------------------------------------------------


_default_manager: ConstraintManager | None = None


def get_manager() -> ConstraintManager:
    """Get or create the default constraint manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = ConstraintManager()
    return _default_manager


def attach_external_constraint(
    claim_id: str,
    claim_created_at: datetime,
    claim_value: str,
    substrate_id: str,
    query: str,
    affordance: str | None = None,
) -> tuple[SubstrateSnapshot, ConstraintBinding]:
    """Attach external constraint using default manager."""
    return get_manager().attach_constraint(
        claim_id=claim_id,
        claim_created_at=claim_created_at,
        claim_value=claim_value,
        substrate_id=substrate_id,
        query=query,
        affordance=affordance,
    )
