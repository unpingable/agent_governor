"""Perforce Support — integrity invariants on explicit authority substrate.

Applies the same integrity invariants as Git governance, but on a substrate
that already admits authority exists. P4's explicit changelists, file-level
locking, and immutable history map directly to Governor's principles.

Core insight: Git culture hides authority in vibes. Perforce admits it exists.
Governor just makes that explicit.

Components:
1. Changelist integrity - Metadata claims must correspond to files in CL
2. Lock semantics - Locked files are authoritative state
3. Immutable releases - Tagged release CLs become read-only
4. Depot↔DOI mapping - DOI corresponds to depot path + changelist number
"""

import subprocess
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
import json
import yaml


def _utcnow() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# =============================================================================
# P4 Availability Check
# =============================================================================


def p4_available() -> bool:
    """Check if p4 CLI is available."""
    try:
        result = subprocess.run(
            ["p4", "-V"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class P4NotAvailableError(Exception):
    """Raised when P4 is not available."""
    pass


# =============================================================================
# Types
# =============================================================================


class CheckType(str, Enum):
    """Types of P4 governance checks."""
    CHANGELIST_INTEGRITY = "changelist_integrity"
    LOCK_SEMANTICS = "lock_semantics"
    IMMUTABLE_RELEASE = "immutable_release"
    DOI_MAPPING = "doi_mapping"


class Severity(str, Enum):
    """Severity of a P4 governance violation."""
    WARN = "warn"
    BLOCK = "block"


@dataclass
class Violation:
    """A P4 governance violation."""
    check_type: CheckType
    message: str
    changelist: int | None = None
    file_path: str | None = None
    severity: Severity = Severity.WARN

    def to_dict(self) -> dict:
        return {
            "check_type": self.check_type.value,
            "message": self.message,
            "changelist": self.changelist,
            "file_path": self.file_path,
            "severity": self.severity.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Violation":
        return cls(
            check_type=CheckType(data["check_type"]),
            message=data["message"],
            changelist=data.get("changelist"),
            file_path=data.get("file_path"),
            severity=Severity(data.get("severity", "warn")),
        )


@dataclass
class CheckResult:
    """Result of a P4 governance check."""
    passed: bool
    violations: list[Violation] = field(default_factory=list)
    check_type: CheckType | None = None

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "check_type": self.check_type.value if self.check_type else None,
        }


@dataclass
class LockState:
    """State of a file lock in P4."""
    file_path: str
    locked: bool
    lock_holder: str | None = None
    lock_client: str | None = None
    lock_type: str | None = None  # "exclusive" or "shared"

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "locked": self.locked,
            "lock_holder": self.lock_holder,
            "lock_client": self.lock_client,
            "lock_type": self.lock_type,
        }


@dataclass
class Changelist:
    """A P4 changelist."""
    number: int
    user: str
    client: str
    status: str  # "pending", "submitted", "shelved"
    description: str
    files: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "user": self.user,
            "client": self.client,
            "status": self.status,
            "description": self.description,
            "files": self.files,
            "labels": self.labels,
        }


@dataclass
class DepotDOIMapping:
    """Mapping between DOI and depot path."""
    doi: str
    depot_path: str
    changelist: int
    timestamp: datetime
    content_hash: str | None = None

    def to_dict(self) -> dict:
        return {
            "doi": self.doi,
            "depot_path": self.depot_path,
            "changelist": self.changelist,
            "timestamp": self.timestamp.isoformat(),
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DepotDOIMapping":
        return cls(
            doi=data["doi"],
            depot_path=data["depot_path"],
            changelist=data["changelist"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            content_hash=data.get("content_hash"),
        )


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class P4Connection:
    """P4 connection settings."""
    port: str = ""  # e.g., "ssl:perforce.example.com:1666"
    user: str = ""  # e.g., "${P4USER}"
    client: str = ""  # e.g., "${P4CLIENT}"

    def to_dict(self) -> dict:
        return {
            "port": self.port,
            "user": self.user,
            "client": self.client,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "P4Connection":
        return cls(
            port=data.get("port", ""),
            user=data.get("user", ""),
            client=data.get("client", ""),
        )


@dataclass
class ChangelistIntegrityConfig:
    """Configuration for changelist integrity checking."""
    enabled: bool = True
    require_metadata_match: bool = True
    allow_prior_cl_reference: bool = True

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "require_metadata_match": self.require_metadata_match,
            "allow_prior_cl_reference": self.allow_prior_cl_reference,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChangelistIntegrityConfig":
        return cls(
            enabled=data.get("enabled", True),
            require_metadata_match=data.get("require_metadata_match", True),
            allow_prior_cl_reference=data.get("allow_prior_cl_reference", True),
        )


@dataclass
class LockSemanticsConfig:
    """Configuration for lock semantics enforcement."""
    enabled: bool = True
    treat_as_authoritative: bool = True
    block_cross_agent_claims: bool = True

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "treat_as_authoritative": self.treat_as_authoritative,
            "block_cross_agent_claims": self.block_cross_agent_claims,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LockSemanticsConfig":
        return cls(
            enabled=data.get("enabled", True),
            treat_as_authoritative=data.get("treat_as_authoritative", True),
            block_cross_agent_claims=data.get("block_cross_agent_claims", True),
        )


@dataclass
class ImmutableReleasesConfig:
    """Configuration for immutable release enforcement."""
    enabled: bool = True
    tags: list[str] = field(default_factory=lambda: [
        "published", "preprint", "archival", "release"
    ])
    allow_fork_with_audit: bool = True

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "tags": self.tags,
            "allow_fork_with_audit": self.allow_fork_with_audit,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ImmutableReleasesConfig":
        return cls(
            enabled=data.get("enabled", True),
            tags=data.get("tags", ["published", "preprint", "archival", "release"]),
            allow_fork_with_audit=data.get("allow_fork_with_audit", True),
        )


@dataclass
class DOIMappingConfig:
    """Configuration for DOI mapping."""
    enabled: bool = True
    depot_pattern: str = "//depot/papers/{doi_suffix}/..."
    require_exact_match: bool = True

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "depot_pattern": self.depot_pattern,
            "require_exact_match": self.require_exact_match,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DOIMappingConfig":
        return cls(
            enabled=data.get("enabled", True),
            depot_pattern=data.get("depot_pattern", "//depot/papers/{doi_suffix}/..."),
            require_exact_match=data.get("require_exact_match", True),
        )


@dataclass
class P4GovernanceConfig:
    """Complete P4 governance configuration."""
    enabled: bool = True
    connection: P4Connection = field(default_factory=P4Connection)
    changelist_integrity: ChangelistIntegrityConfig = field(default_factory=ChangelistIntegrityConfig)
    lock_semantics: LockSemanticsConfig = field(default_factory=LockSemanticsConfig)
    immutable_releases: ImmutableReleasesConfig = field(default_factory=ImmutableReleasesConfig)
    doi_mapping: DOIMappingConfig = field(default_factory=DOIMappingConfig)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "connection": self.connection.to_dict(),
            "changelist_integrity": self.changelist_integrity.to_dict(),
            "lock_semantics": self.lock_semantics.to_dict(),
            "immutable_releases": self.immutable_releases.to_dict(),
            "doi_mapping": self.doi_mapping.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "P4GovernanceConfig":
        return cls(
            enabled=data.get("enabled", True),
            connection=P4Connection.from_dict(data.get("connection", {})),
            changelist_integrity=ChangelistIntegrityConfig.from_dict(data.get("changelist_integrity", {})),
            lock_semantics=LockSemanticsConfig.from_dict(data.get("lock_semantics", {})),
            immutable_releases=ImmutableReleasesConfig.from_dict(data.get("immutable_releases", {})),
            doi_mapping=DOIMappingConfig.from_dict(data.get("doi_mapping", {})),
        )

    def save(self, path: Path) -> None:
        """Save configuration to YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)

    @classmethod
    def load(cls, path: Path) -> "P4GovernanceConfig":
        """Load configuration from YAML file."""
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)


# =============================================================================
# P4 Client
# =============================================================================


class P4Client:
    """Thin wrapper around p4 CLI."""

    def __init__(self, config: P4GovernanceConfig | None = None):
        self.config = config or P4GovernanceConfig()
        self._available: bool | None = None

    def _run_p4(self, *args: str) -> tuple[int, str, str]:
        """Run a p4 command and return (returncode, stdout, stderr)."""
        cmd = ["p4"]

        # Add connection options if configured
        if self.config.connection.port:
            cmd.extend(["-p", self.config.connection.port])
        if self.config.connection.user:
            cmd.extend(["-u", self.config.connection.user])
        if self.config.connection.client:
            cmd.extend(["-c", self.config.connection.client])

        cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except FileNotFoundError:
            raise P4NotAvailableError("p4 command not found")
        except subprocess.TimeoutExpired:
            raise P4NotAvailableError("p4 command timed out")

    def is_available(self) -> bool:
        """Check if P4 is available and configured."""
        if self._available is None:
            self._available = p4_available()
        return self._available

    def get_changelist(self, cl: int) -> Changelist | None:
        """Get changelist details."""
        if not self.is_available():
            return None

        code, stdout, _ = self._run_p4("describe", "-s", str(cl))
        if code != 0:
            return None

        # Parse p4 describe output
        lines = stdout.splitlines()
        if not lines:
            return None

        # First line: "Change 12345 by user@client on 2025/01/01 12:00:00"
        first_line = lines[0]
        match = re.match(r"Change (\d+) by (\S+)@(\S+)", first_line)
        if not match:
            return None

        user = match.group(2)
        client = match.group(3)

        # Find description (after blank line)
        description_lines = []
        in_description = False
        files = []
        in_files = False

        for line in lines[1:]:
            if line.startswith("Affected files"):
                in_description = False
                in_files = True
                continue
            if in_files and line.startswith("..."):
                # Parse file path
                file_match = re.match(r"\.\.\. (.+)#\d+", line)
                if file_match:
                    files.append(file_match.group(1))
            elif not line.strip():
                in_description = True
            elif in_description and not in_files:
                description_lines.append(line.strip())

        return Changelist(
            number=cl,
            user=user,
            client=client,
            status="submitted",  # p4 describe shows submitted CLs
            description="\n".join(description_lines),
            files=files,
        )

    def get_files_in_cl(self, cl: int) -> list[str]:
        """Get list of files in a changelist."""
        if not self.is_available():
            return []

        code, stdout, _ = self._run_p4("files", f"@={cl}")
        if code != 0:
            return []

        files = []
        for line in stdout.splitlines():
            # Format: //depot/path/file#rev - action
            match = re.match(r"(.+)#\d+ - \w+", line)
            if match:
                files.append(match.group(1))

        return files

    def get_lock_status(self, file_path: str) -> LockState:
        """Get lock status for a file."""
        if not self.is_available():
            return LockState(file_path=file_path, locked=False)

        code, stdout, _ = self._run_p4("opened", "-a", file_path)
        if code != 0 or not stdout:
            return LockState(file_path=file_path, locked=False)

        # Parse p4 opened output
        # Format: //depot/path/file#rev - action *exclusive* by user@client
        for line in stdout.splitlines():
            if "*exclusive*" in line or "*locked*" in line:
                match = re.match(r".+ by (\S+)@(\S+)", line)
                if match:
                    return LockState(
                        file_path=file_path,
                        locked=True,
                        lock_holder=match.group(1),
                        lock_client=match.group(2),
                        lock_type="exclusive",
                    )

        return LockState(file_path=file_path, locked=False)

    def get_labels(self, cl: int) -> list[str]:
        """Get labels associated with a changelist."""
        if not self.is_available():
            return []

        code, stdout, _ = self._run_p4("labels", f"@{cl}")
        if code != 0:
            return []

        labels = []
        for line in stdout.splitlines():
            # Format: Label label_name date 'description'
            match = re.match(r"Label (\S+)", line)
            if match:
                labels.append(match.group(1))

        return labels

    def get_pending_changelists(self) -> list[int]:
        """Get list of pending changelist numbers."""
        if not self.is_available():
            return []

        code, stdout, _ = self._run_p4("changes", "-s", "pending")
        if code != 0:
            return []

        changelists = []
        for line in stdout.splitlines():
            match = re.match(r"Change (\d+)", line)
            if match:
                changelists.append(int(match.group(1)))

        return changelists


# =============================================================================
# Checkers
# =============================================================================


class ChangelistIntegrityChecker:
    """Check changelist integrity - metadata claims must match files."""

    def __init__(self, config: P4GovernanceConfig, p4: P4Client):
        self.config = config
        self.p4 = p4

    def check(self, cl: int, metadata_claims: list[str] | None = None) -> CheckResult:
        """Check changelist integrity."""
        if not self.config.changelist_integrity.enabled:
            return CheckResult(passed=True, check_type=CheckType.CHANGELIST_INTEGRITY)

        violations = []

        # Get files in changelist
        files = self.p4.get_files_in_cl(cl)
        if not files and self.p4.is_available():
            violations.append(Violation(
                check_type=CheckType.CHANGELIST_INTEGRITY,
                message=f"Changelist {cl} has no files",
                changelist=cl,
                severity=Severity.WARN,
            ))

        # If metadata claims provided, check they're in the CL
        if metadata_claims and self.config.changelist_integrity.require_metadata_match:
            for claim in metadata_claims:
                if claim not in files:
                    violations.append(Violation(
                        check_type=CheckType.CHANGELIST_INTEGRITY,
                        message=f"Claimed artifact '{claim}' not in changelist {cl}",
                        changelist=cl,
                        file_path=claim,
                        severity=Severity.BLOCK,
                    ))

        return CheckResult(
            passed=len(violations) == 0,
            violations=violations,
            check_type=CheckType.CHANGELIST_INTEGRITY,
        )


class LockSemanticsChecker:
    """Enforce lock semantics - locked files are authoritative."""

    def __init__(self, config: P4GovernanceConfig, p4: P4Client):
        self.config = config
        self.p4 = p4

    def check_lock_authority(self, file_path: str, agent_id: str | None = None) -> CheckResult:
        """Check if agent can access a file (respecting locks)."""
        if not self.config.lock_semantics.enabled:
            return CheckResult(passed=True, check_type=CheckType.LOCK_SEMANTICS)

        violations = []
        lock_state = self.p4.get_lock_status(file_path)

        if lock_state.locked:
            if self.config.lock_semantics.block_cross_agent_claims:
                if agent_id and lock_state.lock_holder and agent_id != lock_state.lock_holder:
                    violations.append(Violation(
                        check_type=CheckType.LOCK_SEMANTICS,
                        message=f"File '{file_path}' is locked by {lock_state.lock_holder}",
                        file_path=file_path,
                        severity=Severity.BLOCK,
                    ))

        return CheckResult(
            passed=len(violations) == 0,
            violations=violations,
            check_type=CheckType.LOCK_SEMANTICS,
        )

    def get_locked_files(self) -> list[LockState]:
        """Get all locked files visible to current user."""
        if not self.p4.is_available():
            return []

        # This would require p4 opened -a across depot
        # Simplified for now
        return []


class ImmutableReleaseChecker:
    """Enforce immutable releases - tagged CLs cannot be modified."""

    def __init__(self, config: P4GovernanceConfig, p4: P4Client):
        self.config = config
        self.p4 = p4
        self._immutable_cls: set[int] = set()

    def mark_immutable(self, cl: int, tag: str) -> bool:
        """Mark a changelist as immutable."""
        if tag not in self.config.immutable_releases.tags:
            return False
        self._immutable_cls.add(cl)
        return True

    def is_immutable(self, cl: int) -> bool:
        """Check if a changelist is immutable."""
        if cl in self._immutable_cls:
            return True

        # Check if CL has any immutable labels
        labels = self.p4.get_labels(cl)
        for label in labels:
            if any(tag in label.lower() for tag in self.config.immutable_releases.tags):
                self._immutable_cls.add(cl)
                return True

        return False

    def check_modification_attempt(self, cl: int) -> CheckResult:
        """Check if modification of CL is allowed."""
        if not self.config.immutable_releases.enabled:
            return CheckResult(passed=True, check_type=CheckType.IMMUTABLE_RELEASE)

        violations = []

        if self.is_immutable(cl):
            violations.append(Violation(
                check_type=CheckType.IMMUTABLE_RELEASE,
                message=f"Changelist {cl} is marked immutable and cannot be modified",
                changelist=cl,
                severity=Severity.BLOCK,
            ))

        return CheckResult(
            passed=len(violations) == 0,
            violations=violations,
            check_type=CheckType.IMMUTABLE_RELEASE,
        )


class DOIMappingChecker:
    """Verify DOI↔depot mappings."""

    def __init__(self, config: P4GovernanceConfig, p4: P4Client):
        self.config = config
        self.p4 = p4
        self._mappings: dict[str, DepotDOIMapping] = {}

    def add_mapping(self, mapping: DepotDOIMapping) -> None:
        """Add a DOI mapping."""
        self._mappings[mapping.doi] = mapping

    def get_mapping(self, doi: str) -> DepotDOIMapping | None:
        """Get mapping for a DOI."""
        return self._mappings.get(doi)

    def verify_mapping(self, doi: str) -> CheckResult:
        """Verify a DOI mapping is valid."""
        if not self.config.doi_mapping.enabled:
            return CheckResult(passed=True, check_type=CheckType.DOI_MAPPING)

        violations = []
        mapping = self._mappings.get(doi)

        if mapping is None:
            violations.append(Violation(
                check_type=CheckType.DOI_MAPPING,
                message=f"No mapping found for DOI: {doi}",
                severity=Severity.WARN,
            ))
            return CheckResult(
                passed=False,
                violations=violations,
                check_type=CheckType.DOI_MAPPING,
            )

        # Verify depot path exists in changelist
        files = self.p4.get_files_in_cl(mapping.changelist)
        if self.p4.is_available() and not any(f.startswith(mapping.depot_path.rstrip("/...")) for f in files):
            violations.append(Violation(
                check_type=CheckType.DOI_MAPPING,
                message=f"Depot path '{mapping.depot_path}' not found in CL {mapping.changelist}",
                changelist=mapping.changelist,
                file_path=mapping.depot_path,
                severity=Severity.BLOCK,
            ))

        return CheckResult(
            passed=len(violations) == 0,
            violations=violations,
            check_type=CheckType.DOI_MAPPING,
        )

    def list_mappings(self) -> list[DepotDOIMapping]:
        """List all DOI mappings."""
        return list(self._mappings.values())


# =============================================================================
# P4 Governor (Main Interface)
# =============================================================================


class P4Governor:
    """Main interface for P4 governance."""

    def __init__(self, config: P4GovernanceConfig | None = None, cwd: Path | None = None):
        self.cwd = cwd or Path(".")
        self.config = config or self._load_config()
        self.p4 = P4Client(self.config)
        self.changelist_checker = ChangelistIntegrityChecker(self.config, self.p4)
        self.lock_checker = LockSemanticsChecker(self.config, self.p4)
        self.immutable_checker = ImmutableReleaseChecker(self.config, self.p4)
        self.doi_checker = DOIMappingChecker(self.config, self.p4)

    def _load_config(self) -> P4GovernanceConfig:
        """Load config from .governor/p4_policy.yaml."""
        config_path = self.cwd / ".governor" / "p4_policy.yaml"
        return P4GovernanceConfig.load(config_path)

    def is_available(self) -> bool:
        """Check if P4 is available."""
        return self.p4.is_available()

    def check_changelist(self, cl: int, metadata_claims: list[str] | None = None) -> CheckResult:
        """Check changelist integrity."""
        return self.changelist_checker.check(cl, metadata_claims)

    def check_lock(self, file_path: str, agent_id: str | None = None) -> CheckResult:
        """Check lock authority for a file."""
        return self.lock_checker.check_lock_authority(file_path, agent_id)

    def check_immutable(self, cl: int) -> CheckResult:
        """Check if CL modification is allowed."""
        return self.immutable_checker.check_modification_attempt(cl)

    def mark_release(self, cl: int, tag: str) -> bool:
        """Mark a changelist as an immutable release."""
        return self.immutable_checker.mark_immutable(cl, tag)

    def add_doi_mapping(self, doi: str, depot_path: str, changelist: int) -> DepotDOIMapping:
        """Add a DOI mapping."""
        mapping = DepotDOIMapping(
            doi=doi,
            depot_path=depot_path,
            changelist=changelist,
            timestamp=_utcnow(),
        )
        self.doi_checker.add_mapping(mapping)
        return mapping

    def verify_doi(self, doi: str) -> CheckResult:
        """Verify a DOI mapping."""
        return self.doi_checker.verify_mapping(doi)

    def pre_submit_check(self, cl: int) -> list[Violation]:
        """Run all pre-submit checks."""
        violations = []

        # Check changelist integrity
        result = self.check_changelist(cl)
        violations.extend(result.violations)

        # Check immutability
        result = self.check_immutable(cl)
        violations.extend(result.violations)

        return violations

    def should_block(self, cl: int) -> tuple[bool, list[Violation]]:
        """Check if commit should be blocked."""
        violations = self.pre_submit_check(cl)
        blocking = [v for v in violations if v.severity == Severity.BLOCK]
        return len(blocking) > 0, blocking


# =============================================================================
# DOI Mapping Store
# =============================================================================


class DOIMappingStore:
    """Persistent store for DOI mappings."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._index_path = base_path / "index.json"
        self._mappings: dict[str, DepotDOIMapping] = {}
        self._load()

    def _load(self) -> None:
        """Load mappings from disk."""
        if self._index_path.exists():
            with open(self._index_path) as f:
                data = json.load(f)
            for doi, mapping_data in data.items():
                self._mappings[doi] = DepotDOIMapping.from_dict(mapping_data)

    def _save(self) -> None:
        """Save mappings to disk."""
        data = {doi: m.to_dict() for doi, m in self._mappings.items()}
        with open(self._index_path, "w") as f:
            json.dump(data, f, indent=2)

    def add(self, mapping: DepotDOIMapping) -> None:
        """Add a mapping."""
        self._mappings[mapping.doi] = mapping
        self._save()

    def get(self, doi: str) -> DepotDOIMapping | None:
        """Get a mapping by DOI."""
        return self._mappings.get(doi)

    def list_all(self) -> list[DepotDOIMapping]:
        """List all mappings."""
        return list(self._mappings.values())

    def remove(self, doi: str) -> bool:
        """Remove a mapping."""
        if doi in self._mappings:
            del self._mappings[doi]
            self._save()
            return True
        return False


# =============================================================================
# Module-Level Convenience
# =============================================================================


def create_p4_governor(cwd: Path | None = None) -> P4Governor:
    """Create a P4Governor instance."""
    return P4Governor(cwd=cwd)


def check_pre_submit(cl: int, cwd: Path | None = None) -> list[Violation]:
    """Convenience function for pre-submit hook."""
    governor = create_p4_governor(cwd)
    return governor.pre_submit_check(cl)
