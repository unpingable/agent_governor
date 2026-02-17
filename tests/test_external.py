# SPDX-License-Identifier: Apache-2.0
"""Tests for external constraint attachment module."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest

from governor.external import (
    # Enums
    Volatility,
    AuthorityType,
    BindingType,
    Resolution,
    # Data types
    TrustProfile,
    SubstrateSnapshot,
    ConstraintBinding,
    Discrepancy,
    # Substrates
    WikidataSubstrate,
    WikipediaSubstrate,
    ScholarSubstrate,
    SUBSTRATES,
    TRUST_PROFILES,
    get_substrate,
    list_substrates,
    # Manager
    ConstraintManager,
    get_manager,
    attach_external_constraint,
    _generate_id,
    _hash_response,
)


# -----------------------------------------------------------------------------
# Test Enums
# -----------------------------------------------------------------------------


class TestVolatility:
    def test_all_values(self):
        assert Volatility.IMMUTABLE == "immutable"
        assert Volatility.STABLE == "stable"
        assert Volatility.DYNAMIC == "dynamic"
        assert Volatility.EPHEMERAL == "ephemeral"

    def test_from_string(self):
        assert Volatility("stable") == Volatility.STABLE


class TestAuthorityType:
    def test_all_values(self):
        assert AuthorityType.INSTITUTIONAL == "institutional"
        assert AuthorityType.CROWD == "crowd"
        assert AuthorityType.ALGORITHMIC == "algorithmic"
        assert AuthorityType.PRIMARY == "primary"


class TestBindingType:
    def test_all_values(self):
        assert BindingType.SUPPORTS == "supports"
        assert BindingType.CONTRADICTS == "contradicts"
        assert BindingType.TANGENTIAL == "tangential"
        assert BindingType.SILENT == "silent"


class TestResolution:
    def test_all_values(self):
        assert Resolution.CLAIM_UPDATED == "claim_updated"
        assert Resolution.CLAIM_RETAINED == "claim_retained"
        assert Resolution.SUBSTRATE_STALE == "substrate_stale"
        assert Resolution.CONTEXT_DIFFERS == "context_differs"
        assert Resolution.PENDING == "pending"


# -----------------------------------------------------------------------------
# Test Trust Profiles
# -----------------------------------------------------------------------------


class TestTrustProfile:
    def test_creation(self):
        profile = TrustProfile(
            volatility=Volatility.STABLE,
            authority_type=AuthorityType.CROWD,
        )
        assert profile.volatility == Volatility.STABLE
        assert profile.authority_type == AuthorityType.CROWD
        assert profile.citation_required is True
        assert profile.snapshot_ttl == timedelta(hours=24)

    def test_to_dict(self):
        profile = TrustProfile(
            volatility=Volatility.IMMUTABLE,
            authority_type=AuthorityType.PRIMARY,
            citation_required=False,
            snapshot_ttl=timedelta(days=365),
        )
        d = profile.to_dict()
        assert d["volatility"] == "immutable"
        assert d["authority_type"] == "primary"
        assert d["citation_required"] is False
        assert d["snapshot_ttl_seconds"] == 365 * 24 * 3600

    def test_from_dict(self):
        data = {
            "volatility": "dynamic",
            "authority_type": "crowd",
            "citation_required": True,
            "snapshot_ttl_seconds": 3600,
        }
        profile = TrustProfile.from_dict(data)
        assert profile.volatility == Volatility.DYNAMIC
        assert profile.authority_type == AuthorityType.CROWD
        assert profile.snapshot_ttl == timedelta(hours=1)

    def test_roundtrip(self):
        original = TrustProfile(
            volatility=Volatility.EPHEMERAL,
            authority_type=AuthorityType.ALGORITHMIC,
            citation_required=False,
            snapshot_ttl=timedelta(minutes=30),
        )
        restored = TrustProfile.from_dict(original.to_dict())
        assert restored.volatility == original.volatility
        assert restored.authority_type == original.authority_type
        assert restored.citation_required == original.citation_required
        assert restored.snapshot_ttl == original.snapshot_ttl


class TestDefaultTrustProfiles:
    def test_wikidata_profile(self):
        profile = TRUST_PROFILES["wikidata"]
        assert profile.volatility == Volatility.STABLE
        assert profile.authority_type == AuthorityType.CROWD

    def test_wikipedia_profile(self):
        profile = TRUST_PROFILES["wikipedia"]
        assert profile.volatility == Volatility.DYNAMIC
        assert profile.authority_type == AuthorityType.CROWD

    def test_scholar_profile(self):
        profile = TRUST_PROFILES["scholar"]
        assert profile.volatility == Volatility.STABLE
        assert profile.authority_type == AuthorityType.INSTITUTIONAL

    def test_archive_profile(self):
        profile = TRUST_PROFILES["archive"]
        assert profile.volatility == Volatility.IMMUTABLE
        assert profile.authority_type == AuthorityType.PRIMARY


# -----------------------------------------------------------------------------
# Test Substrate Snapshot
# -----------------------------------------------------------------------------


class TestSubstrateSnapshot:
    def test_creation(self):
        now = datetime.utcnow()
        snapshot = SubstrateSnapshot(
            snapshot_id="snap_123",
            substrate_id="wikidata",
            query="Q42",
            response='{"entities": {}}',
            queried_at=now,
            response_hash="abc123",
            affordance_used="entity",
        )
        assert snapshot.snapshot_id == "snap_123"
        assert snapshot.substrate_id == "wikidata"
        assert snapshot.query == "Q42"
        assert snapshot.queried_at == now

    def test_to_dict(self):
        now = datetime(2024, 1, 15, 12, 0, 0)
        snapshot = SubstrateSnapshot(
            snapshot_id="snap_456",
            substrate_id="wikipedia",
            query="Douglas Adams",
            response='{"pages": {}}',
            queried_at=now,
            response_hash="def456",
            affordance_used="article",
            metadata={"language": "en"},
        )
        d = snapshot.to_dict()
        assert d["snapshot_id"] == "snap_456"
        assert d["queried_at"] == "2024-01-15T12:00:00"
        assert d["metadata"]["language"] == "en"

    def test_from_dict(self):
        data = {
            "snapshot_id": "snap_789",
            "substrate_id": "scholar",
            "query": "10.1000/xyz",
            "response": '{"DOI": "10.1000/xyz"}',
            "queried_at": "2024-01-15T12:00:00",
            "response_hash": "ghi789",
            "affordance_used": "doi",
            "metadata": {"source": "crossref"},
        }
        snapshot = SubstrateSnapshot.from_dict(data)
        assert snapshot.snapshot_id == "snap_789"
        assert snapshot.substrate_id == "scholar"
        assert snapshot.queried_at == datetime(2024, 1, 15, 12, 0, 0)

    def test_roundtrip(self):
        original = SubstrateSnapshot(
            snapshot_id="snap_test",
            substrate_id="wikidata",
            query="Q42",
            response='{"test": true}',
            queried_at=datetime.utcnow(),
            response_hash="test123",
            affordance_used="entity",
            metadata={"key": "value"},
        )
        restored = SubstrateSnapshot.from_dict(original.to_dict())
        assert restored.snapshot_id == original.snapshot_id
        assert restored.query == original.query
        assert restored.metadata == original.metadata


# -----------------------------------------------------------------------------
# Test Constraint Binding
# -----------------------------------------------------------------------------


class TestConstraintBinding:
    def test_creation(self):
        binding = ConstraintBinding(
            binding_id="bind_123",
            claim_id="claim_456",
            snapshot_id="snap_789",
            binding_type=BindingType.SUPPORTS,
            delta_t=timedelta(hours=2),
        )
        assert binding.binding_id == "bind_123"
        assert binding.binding_type == BindingType.SUPPORTS
        assert binding.delta_t == timedelta(hours=2)

    def test_to_dict(self):
        binding = ConstraintBinding(
            binding_id="bind_test",
            claim_id="claim_test",
            snapshot_id="snap_test",
            binding_type=BindingType.CONTRADICTS,
            delta_t=timedelta(minutes=30),
            notes="Test note",
        )
        d = binding.to_dict()
        assert d["binding_type"] == "contradicts"
        assert d["delta_t_seconds"] == 1800
        assert d["notes"] == "Test note"

    def test_from_dict(self):
        data = {
            "binding_id": "bind_from",
            "claim_id": "claim_from",
            "snapshot_id": "snap_from",
            "binding_type": "tangential",
            "delta_t_seconds": 3600,
            "notes": None,
            "created_at": "2024-01-15T12:00:00",
        }
        binding = ConstraintBinding.from_dict(data)
        assert binding.binding_type == BindingType.TANGENTIAL
        assert binding.delta_t == timedelta(hours=1)


# -----------------------------------------------------------------------------
# Test Discrepancy
# -----------------------------------------------------------------------------


class TestDiscrepancy:
    def test_creation(self):
        discrepancy = Discrepancy(
            discrepancy_id="disc_123",
            claim_id="claim_456",
            binding_id="bind_789",
            claim_value="The Earth is flat",
            substrate_value="The Earth is an oblate spheroid",
            delta_t=timedelta(hours=1),
        )
        assert discrepancy.resolution == Resolution.PENDING
        assert discrepancy.resolved_at is None

    def test_to_dict(self):
        discrepancy = Discrepancy(
            discrepancy_id="disc_test",
            claim_id="claim_test",
            binding_id="bind_test",
            claim_value="Claim A",
            substrate_value="Response B",
            delta_t=timedelta(minutes=15),
            resolution=Resolution.CLAIM_RETAINED,
            resolution_reason="Context differs",
            resolved_at=datetime(2024, 1, 15, 14, 0, 0),
        )
        d = discrepancy.to_dict()
        assert d["resolution"] == "claim_retained"
        assert d["resolution_reason"] == "Context differs"
        assert d["resolved_at"] == "2024-01-15T14:00:00"

    def test_from_dict(self):
        data = {
            "discrepancy_id": "disc_from",
            "claim_id": "claim_from",
            "binding_id": "bind_from",
            "claim_value": "Value A",
            "substrate_value": "Value B",
            "delta_t_seconds": 900,
            "resolution": "pending",
            "resolution_reason": None,
            "resolved_at": None,
            "created_at": "2024-01-15T12:00:00",
        }
        discrepancy = Discrepancy.from_dict(data)
        assert discrepancy.resolution == Resolution.PENDING
        assert discrepancy.resolved_at is None


# -----------------------------------------------------------------------------
# Test Substrates
# -----------------------------------------------------------------------------


class TestWikidataSubstrate:
    def test_substrate_id(self):
        substrate = WikidataSubstrate()
        assert substrate.substrate_id == "wikidata"

    def test_available_affordances(self):
        substrate = WikidataSubstrate()
        affordances = substrate.available_affordances()
        assert "entity" in affordances
        assert "search" in affordances

    @patch("urllib.request.urlopen")
    def test_query_entity(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "entities": {"Q42": {"labels": {"en": {"value": "Douglas Adams"}}}}
        }).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        substrate = WikidataSubstrate()
        snapshot = substrate.query("Q42", "entity")

        assert snapshot.substrate_id == "wikidata"
        assert snapshot.query == "Q42"
        assert snapshot.affordance_used == "entity"
        assert "Douglas Adams" in snapshot.response

    @patch("urllib.request.urlopen")
    def test_query_search(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "search": [{"id": "Q42", "label": "Douglas Adams"}]
        }).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        substrate = WikidataSubstrate()
        snapshot = substrate.query("Douglas Adams", "search")

        assert snapshot.affordance_used == "search"
        assert "Q42" in snapshot.response

    def test_query_error_handling(self):
        substrate = WikidataSubstrate()
        # This will fail with network error but should not raise
        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            snapshot = substrate.query("Q42")
            assert "error" in snapshot.response


class TestWikipediaSubstrate:
    def test_substrate_id(self):
        substrate = WikipediaSubstrate()
        assert substrate.substrate_id == "wikipedia"

    def test_available_affordances(self):
        substrate = WikipediaSubstrate()
        affordances = substrate.available_affordances()
        assert "article" in affordances
        assert "section" in affordances
        assert "revision" in affordances

    @patch("urllib.request.urlopen")
    def test_query_article(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "query": {"pages": {"1": {"extract": "Douglas Adams was an English author"}}}
        }).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        substrate = WikipediaSubstrate()
        snapshot = substrate.query("Douglas Adams", "article")

        assert snapshot.substrate_id == "wikipedia"
        assert snapshot.affordance_used == "article"
        assert "English author" in snapshot.response


class TestScholarSubstrate:
    def test_substrate_id(self):
        substrate = ScholarSubstrate()
        assert substrate.substrate_id == "scholar"

    def test_available_affordances(self):
        substrate = ScholarSubstrate()
        affordances = substrate.available_affordances()
        assert "doi" in affordances
        assert "search" in affordances

    @patch("urllib.request.urlopen")
    def test_query_doi(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "message": {"DOI": "10.1000/xyz123", "title": ["Test Paper"]}
        }).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        substrate = ScholarSubstrate()
        snapshot = substrate.query("10.1000/xyz123", "doi")

        assert snapshot.substrate_id == "scholar"
        assert snapshot.affordance_used == "doi"
        assert "Test Paper" in snapshot.response

    def test_doi_cleaning(self):
        substrate = ScholarSubstrate()
        # Test that DOI prefixes are handled
        with patch("urllib.request.urlopen", side_effect=Exception("test")):
            # These should all query the same DOI
            substrate.query("10.1000/xyz")
            substrate.query("doi:10.1000/xyz")
            substrate.query("https://doi.org/10.1000/xyz")


class TestSubstrateRegistry:
    def test_list_substrates(self):
        substrates = list_substrates()
        assert "wikidata" in substrates
        assert "wikipedia" in substrates
        assert "scholar" in substrates

    def test_get_substrate(self):
        substrate = get_substrate("wikidata")
        assert substrate is not None
        assert substrate.substrate_id == "wikidata"

    def test_get_unknown_substrate(self):
        substrate = get_substrate("unknown")
        assert substrate is None


# -----------------------------------------------------------------------------
# Test Constraint Manager
# -----------------------------------------------------------------------------


class TestConstraintManager:
    def test_creation(self):
        manager = ConstraintManager()
        assert manager._snapshots == {}
        assert manager._bindings == {}
        assert manager._discrepancies == {}

    @patch("urllib.request.urlopen")
    def test_query_substrate(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"entities": {}}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        manager = ConstraintManager()
        snapshot = manager.query_substrate("wikidata", "Q42")

        assert snapshot.substrate_id == "wikidata"
        assert snapshot.snapshot_id in manager._snapshots

    def test_query_unknown_substrate(self):
        manager = ConstraintManager()
        with pytest.raises(ValueError, match="Unknown substrate"):
            manager.query_substrate("unknown", "test")

    @patch("urllib.request.urlopen")
    def test_bind_constraint(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": "test"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        manager = ConstraintManager()
        snapshot = manager.query_substrate("wikidata", "Q42")

        claim_time = datetime.utcnow() - timedelta(hours=1)
        binding = manager.bind_constraint(
            claim_id="claim_123",
            snapshot_id=snapshot.snapshot_id,
            binding_type=BindingType.SUPPORTS,
            claim_created_at=claim_time,
        )

        assert binding.claim_id == "claim_123"
        assert binding.snapshot_id == snapshot.snapshot_id
        assert binding.binding_type == BindingType.SUPPORTS

    def test_bind_unknown_snapshot(self):
        manager = ConstraintManager()
        with pytest.raises(ValueError, match="Unknown snapshot"):
            manager.bind_constraint(
                claim_id="claim_123",
                snapshot_id="nonexistent",
                binding_type=BindingType.SUPPORTS,
                claim_created_at=datetime.utcnow(),
            )

    @patch("urllib.request.urlopen")
    def test_bind_creates_discrepancy_on_contradiction(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": "test response"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        manager = ConstraintManager()
        snapshot = manager.query_substrate("wikidata", "Q42")

        binding = manager.bind_constraint(
            claim_id="claim_123",
            snapshot_id=snapshot.snapshot_id,
            binding_type=BindingType.CONTRADICTS,
            claim_created_at=datetime.utcnow(),
            claim_value="My claim value",
        )

        discrepancies = manager.get_discrepancies()
        assert len(discrepancies) == 1
        assert discrepancies[0].claim_value == "My claim value"
        assert discrepancies[0].resolution == Resolution.PENDING

    @patch("urllib.request.urlopen")
    def test_attach_constraint(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": "test"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        manager = ConstraintManager()
        claim_time = datetime.utcnow() - timedelta(minutes=30)

        snapshot, binding = manager.attach_constraint(
            claim_id="claim_456",
            claim_created_at=claim_time,
            claim_value="Douglas Adams wrote Hitchhiker's Guide",
            substrate_id="wikidata",
            query="Q42",
        )

        assert snapshot is not None
        assert binding is not None
        assert binding.claim_id == "claim_456"

    @patch("urllib.request.urlopen")
    def test_resolve_discrepancy(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": "test"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        manager = ConstraintManager()
        snapshot = manager.query_substrate("wikidata", "Q42")

        manager.bind_constraint(
            claim_id="claim_123",
            snapshot_id=snapshot.snapshot_id,
            binding_type=BindingType.CONTRADICTS,
            claim_created_at=datetime.utcnow(),
            claim_value="Test claim",
        )

        discrepancies = manager.get_discrepancies(status=Resolution.PENDING)
        assert len(discrepancies) == 1

        resolved = manager.resolve_discrepancy(
            discrepancy_id=discrepancies[0].discrepancy_id,
            resolution=Resolution.CLAIM_RETAINED,
            reason="Context differs between claim and source",
        )

        assert resolved.resolution == Resolution.CLAIM_RETAINED
        assert resolved.resolution_reason == "Context differs between claim and source"
        assert resolved.resolved_at is not None

    def test_resolve_unknown_discrepancy(self):
        manager = ConstraintManager()
        with pytest.raises(ValueError, match="Unknown discrepancy"):
            manager.resolve_discrepancy("nonexistent", Resolution.CLAIM_UPDATED, "test")

    @patch("urllib.request.urlopen")
    def test_resolve_already_resolved(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": "test"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        manager = ConstraintManager()
        snapshot = manager.query_substrate("wikidata", "Q42")

        manager.bind_constraint(
            claim_id="claim_123",
            snapshot_id=snapshot.snapshot_id,
            binding_type=BindingType.CONTRADICTS,
            claim_created_at=datetime.utcnow(),
            claim_value="Test claim",
        )

        disc_id = manager.get_discrepancies()[0].discrepancy_id
        manager.resolve_discrepancy(disc_id, Resolution.CLAIM_RETAINED, "test")

        with pytest.raises(ValueError, match="already resolved"):
            manager.resolve_discrepancy(disc_id, Resolution.CLAIM_UPDATED, "test2")

    @patch("urllib.request.urlopen")
    def test_get_bindings(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": "test"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        manager = ConstraintManager()
        snapshot1 = manager.query_substrate("wikidata", "Q42")
        snapshot2 = manager.query_substrate("wikipedia", "Douglas Adams")

        manager.bind_constraint(
            claim_id="claim_123",
            snapshot_id=snapshot1.snapshot_id,
            binding_type=BindingType.SUPPORTS,
            claim_created_at=datetime.utcnow(),
        )
        manager.bind_constraint(
            claim_id="claim_123",
            snapshot_id=snapshot2.snapshot_id,
            binding_type=BindingType.SUPPORTS,
            claim_created_at=datetime.utcnow(),
        )
        manager.bind_constraint(
            claim_id="claim_456",
            snapshot_id=snapshot1.snapshot_id,
            binding_type=BindingType.TANGENTIAL,
            claim_created_at=datetime.utcnow(),
        )

        bindings_123 = manager.get_bindings("claim_123")
        bindings_456 = manager.get_bindings("claim_456")
        bindings_999 = manager.get_bindings("claim_999")

        assert len(bindings_123) == 2
        assert len(bindings_456) == 1
        assert len(bindings_999) == 0

    @patch("urllib.request.urlopen")
    def test_check_binding_freshness(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": "test"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        manager = ConstraintManager()
        snapshot = manager.query_substrate("wikidata", "Q42")

        # Fresh binding
        binding = manager.bind_constraint(
            claim_id="claim_123",
            snapshot_id=snapshot.snapshot_id,
            binding_type=BindingType.SUPPORTS,
            claim_created_at=datetime.utcnow(),
        )

        freshness = manager.check_binding_freshness(binding)
        assert freshness["fresh"] is True
        assert len(freshness["warnings"]) == 0

    @patch("urllib.request.urlopen")
    def test_check_binding_freshness_retroactive(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": "test"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        manager = ConstraintManager()
        snapshot = manager.query_substrate("wikidata", "Q42")

        # Retroactive binding - claim is much older than query
        old_claim_time = datetime.utcnow() - timedelta(days=10)
        binding = manager.bind_constraint(
            claim_id="claim_123",
            snapshot_id=snapshot.snapshot_id,
            binding_type=BindingType.SUPPORTS,
            claim_created_at=old_claim_time,
        )

        freshness = manager.check_binding_freshness(binding)
        assert any("Retroactive" in w for w in freshness["warnings"])

    @patch("urllib.request.urlopen")
    def test_serialization_roundtrip(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": "test"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        manager = ConstraintManager()
        snapshot = manager.query_substrate("wikidata", "Q42")

        manager.bind_constraint(
            claim_id="claim_123",
            snapshot_id=snapshot.snapshot_id,
            binding_type=BindingType.CONTRADICTS,
            claim_created_at=datetime.utcnow(),
            claim_value="Test claim",
        )

        # Serialize
        data = manager.to_dict()

        # Deserialize
        restored = ConstraintManager.from_dict(data)

        assert len(restored._snapshots) == 1
        assert len(restored._bindings) == 1
        assert len(restored._discrepancies) == 1


class TestClassifyBinding:
    def test_classify_supports(self):
        manager = ConstraintManager()
        # Claim terms appear in response
        binding_type = manager._classify_binding(
            "Douglas Adams author",
            '{"description": "Douglas Adams was an English author and screenwriter"}',
        )
        assert binding_type == BindingType.SUPPORTS

    def test_classify_silent_on_error(self):
        manager = ConstraintManager()
        binding_type = manager._classify_binding(
            "Test claim",
            '{"error": "Not found"}',
        )
        assert binding_type == BindingType.SILENT

    def test_classify_tangential(self):
        manager = ConstraintManager()
        # Some terms match but not many
        binding_type = manager._classify_binding(
            "Douglas Adams wrote science fiction",
            '{"description": "Science fiction is a genre of literature"}',
        )
        assert binding_type in [BindingType.TANGENTIAL, BindingType.SUPPORTS]


# -----------------------------------------------------------------------------
# Test Module Functions
# -----------------------------------------------------------------------------


class TestModuleFunctions:
    def test_generate_id(self):
        id1 = _generate_id("test")
        id2 = _generate_id("test")
        assert id1.startswith("test_")
        assert id2.startswith("test_")
        assert id1 != id2

    def test_hash_response(self):
        hash1 = _hash_response("test response")
        hash2 = _hash_response("test response")
        hash3 = _hash_response("different response")
        assert hash1 == hash2
        assert hash1 != hash3
        assert len(hash1) == 64  # SHA-256 hex

    def test_get_manager_singleton(self):
        # Reset singleton
        import governor.external as ext
        ext._default_manager = None

        manager1 = get_manager()
        manager2 = get_manager()
        assert manager1 is manager2

    @patch("urllib.request.urlopen")
    def test_attach_external_constraint_convenience(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"data": "test"}'
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        # Reset singleton
        import governor.external as ext
        ext._default_manager = None

        snapshot, binding = attach_external_constraint(
            claim_id="claim_test",
            claim_created_at=datetime.utcnow(),
            claim_value="Test claim",
            substrate_id="wikidata",
            query="Q42",
        )

        assert snapshot is not None
        assert binding is not None


# -----------------------------------------------------------------------------
# Test Temporal Invariants
# -----------------------------------------------------------------------------


class TestTemporalInvariants:
    def test_max_binding_age(self):
        manager = ConstraintManager()
        assert manager.MAX_BINDING_AGE == timedelta(hours=24)

    def test_retroactive_threshold(self):
        manager = ConstraintManager()
        assert manager.RETROACTIVE_THRESHOLD == timedelta(days=7)


# -----------------------------------------------------------------------------
# Integration-style Tests (no network)
# -----------------------------------------------------------------------------


class TestIntegration:
    @patch("urllib.request.urlopen")
    def test_full_workflow(self, mock_urlopen):
        """Test full constraint attachment workflow."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "entities": {
                "Q42": {
                    "labels": {"en": {"value": "Douglas Adams"}},
                    "descriptions": {"en": {"value": "English author and humorist"}},
                }
            }
        }).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        manager = ConstraintManager()

        # 1. Create a claim (simulated)
        claim_id = "claim_001"
        claim_value = "Douglas Adams was an English author"
        claim_time = datetime.utcnow() - timedelta(minutes=5)

        # 2. Attach external constraint
        snapshot, binding = manager.attach_constraint(
            claim_id=claim_id,
            claim_created_at=claim_time,
            claim_value=claim_value,
            substrate_id="wikidata",
            query="Q42",
        )

        # 3. Verify binding created
        assert binding.binding_type == BindingType.SUPPORTS
        assert binding.delta_t < timedelta(minutes=10)

        # 4. Verify snapshot recorded
        assert manager.get_snapshot(snapshot.snapshot_id) is not None

        # 5. Verify binding retrievable
        bindings = manager.get_bindings(claim_id)
        assert len(bindings) == 1
        assert bindings[0].binding_id == binding.binding_id

    @patch("urllib.request.urlopen")
    def test_contradiction_workflow(self, mock_urlopen):
        """Test workflow when external source contradicts claim."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "entities": {
                "Q42": {
                    "labels": {"en": {"value": "Douglas Adams"}},
                    "claims": {"P569": [{"value": "1952-03-11"}]},  # Birth date
                }
            }
        }).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock()
        mock_urlopen.return_value = mock_response

        manager = ConstraintManager()

        # Claim with wrong date
        claim_id = "claim_002"
        claim_value = "Douglas Adams was born in 1960"
        claim_time = datetime.utcnow()

        # Query and manually set contradiction
        snapshot = manager.query_substrate("wikidata", "Q42")
        binding = manager.bind_constraint(
            claim_id=claim_id,
            snapshot_id=snapshot.snapshot_id,
            binding_type=BindingType.CONTRADICTS,
            claim_created_at=claim_time,
            claim_value=claim_value,
        )

        # Discrepancy should be created
        discrepancies = manager.get_discrepancies(status=Resolution.PENDING)
        assert len(discrepancies) == 1

        # Human resolves - claim was wrong
        disc = discrepancies[0]
        resolved = manager.resolve_discrepancy(
            discrepancy_id=disc.discrepancy_id,
            resolution=Resolution.CLAIM_UPDATED,
            reason="Claim had incorrect birth year; updated to 1952",
        )

        assert resolved.resolution == Resolution.CLAIM_UPDATED
        assert manager.get_discrepancies(status=Resolution.PENDING) == []
