# SPDX-License-Identifier: Apache-2.0
"""
Tests for identity check (name grounding).
"""

import json
import pytest
from pathlib import Path

from governor.identity import (
    IdentityConfig,
    IdentityFinding,
    IdentitySeverity,
    IdentityMatchType,
    check_identity,
    check_identity_strict,
    identity_invariant_check,
    load_identity_config,
)


class TestIdentityConfig:
    def test_empty_config(self):
        config = IdentityConfig()
        assert config.authors == []
        assert config.organizations == []

    def test_from_dict(self):
        data = {
            "authors": ["James Beck", "Jane Doe"],
            "organizations": ["Unpingable"],
        }
        config = IdentityConfig.from_dict(data)
        assert config.authors == ["James Beck", "Jane Doe"]
        assert config.organizations == ["Unpingable"]

    def test_to_dict(self):
        config = IdentityConfig(authors=["James Beck"])
        d = config.to_dict()
        assert d["authors"] == ["James Beck"]

    def test_all_author_variants(self):
        config = IdentityConfig(
            authors=["James Beck"],
            aliases={"James Beck": ["J. Beck", "Beck, James"]},
        )
        variants = config.all_author_variants()
        assert "james beck" in variants
        assert "j. beck" in variants
        assert "beck, james" in variants
        assert variants["j. beck"] == "James Beck"

    def test_all_org_variants(self):
        config = IdentityConfig(
            organizations=["Unpingable"],
            aliases={"Unpingable": ["Unpingable Inc", "unpingable.com"]},
        )
        variants = config.all_org_variants()
        assert "unpingable" in variants
        assert "unpingable inc" in variants


class TestIdentityFinding:
    def test_to_dict(self):
        f = IdentityFinding(
            found_name="James",
            expected_names=["James Beck"],
            context="Copyright 2026 James",
            reason="Incomplete name",
            severity=IdentitySeverity.WARN,
            match_type=IdentityMatchType.INCOMPLETE,
            position=15,
        )
        d = f.to_dict()
        assert d["found_name"] == "James"
        assert d["severity"] == "warn"
        assert d["match_type"] == "incomplete"


class TestCheckIdentity:
    def test_exact_match_no_findings(self):
        config = IdentityConfig(authors=["James Beck"])
        findings = check_identity("Copyright 2026 James Beck", config)
        assert findings == []

    def test_incomplete_name_flagged(self):
        config = IdentityConfig(authors=["James Beck"])
        findings = check_identity("Copyright 2026 James", config)
        assert len(findings) == 1
        assert findings[0].match_type == IdentityMatchType.INCOMPLETE
        assert findings[0].severity == IdentitySeverity.WARN
        assert "James Beck" in findings[0].reason

    def test_unknown_name_flagged(self):
        config = IdentityConfig(authors=["James Beck"])
        findings = check_identity("Copyright 2026 John Smith", config)
        assert len(findings) == 1
        assert findings[0].match_type == IdentityMatchType.UNKNOWN
        assert findings[0].severity == IdentitySeverity.ERROR

    def test_hallucinated_last_name(self):
        config = IdentityConfig(authors=["James Beck"])
        findings = check_identity("Copyright 2026 James Becker", config)
        # "James Becker" has partial overlap with "James Beck"
        assert len(findings) == 1
        assert findings[0].found_name == "James Becker"

    def test_alias_matches(self):
        config = IdentityConfig(
            authors=["James Beck"],
            aliases={"James Beck": ["J. Beck"]},
        )
        findings = check_identity("Author: J. Beck", config)
        assert findings == []

    def test_case_insensitive(self):
        config = IdentityConfig(authors=["James Beck"])
        findings = check_identity("Copyright 2026 james beck", config)
        # Pattern expects capitalized names, so lowercase won't match author pattern
        # This is intentional - we're looking for proper names
        assert findings == []  # lowercase doesn't match the capitalized pattern

    def test_copyright_symbol(self):
        config = IdentityConfig(authors=["James Beck"])
        findings = check_identity("© 2026 James", config)
        assert len(findings) == 1
        assert findings[0].match_type == IdentityMatchType.INCOMPLETE

    def test_by_context(self):
        config = IdentityConfig(authors=["James Beck"])
        findings = check_identity("Written by James", config)
        assert len(findings) == 1

    def test_author_context(self):
        config = IdentityConfig(authors=["James Beck"])
        findings = check_identity("Author: James", config)
        assert len(findings) == 1

    def test_no_config_no_findings(self):
        config = IdentityConfig()
        findings = check_identity("Copyright 2026 Anyone", config)
        assert findings == []

    def test_multiple_authors(self):
        config = IdentityConfig(authors=["James Beck", "Jane Doe"])
        # Both should be valid
        findings = check_identity("Authors: James Beck and Jane Doe", config)
        assert findings == []

    def test_org_exact_match(self):
        config = IdentityConfig(organizations=["Unpingable"])
        findings = check_identity("Copyright 2026 Unpingable", config, check_authors=False)
        assert findings == []

    def test_org_hallucinated(self):
        config = IdentityConfig(organizations=["Unpingable"])
        findings = check_identity("Copyright 2026 Unpingco", config, check_authors=False)
        assert len(findings) >= 1

    def test_org_with_suffix(self):
        config = IdentityConfig(organizations=["Acme Corp"])
        findings = check_identity("Copyright 2026 Acme Corp", config, check_authors=False)
        assert findings == []

    def test_position_tracking(self):
        config = IdentityConfig(authors=["James Beck"])
        text = "Copyright 2026 James"
        findings = check_identity(text, config)
        assert findings[0].position == text.index("James")

    def test_context_extraction(self):
        config = IdentityConfig(authors=["James Beck"])
        text = "Some prefix. Copyright 2026 James only. Some suffix."
        findings = check_identity(text, config)
        assert "Copyright" in findings[0].context
        assert "James" in findings[0].context

    def test_check_authors_false(self):
        config = IdentityConfig(authors=["James Beck"])
        findings = check_identity("Copyright 2026 Wrong Name", config, check_authors=False)
        assert findings == []

    def test_check_orgs_false(self):
        config = IdentityConfig(organizations=["Unpingable"])
        findings = check_identity("Copyright 2026 WrongOrg", config, check_orgs=False)
        assert findings == []


class TestCheckIdentityStrict:
    def test_passes_with_exact_match(self):
        config = IdentityConfig(authors=["James Beck"])
        passed, findings = check_identity_strict("Copyright 2026 James Beck", config)
        assert passed is True

    def test_fails_with_incomplete(self):
        config = IdentityConfig(authors=["James Beck"])
        passed, findings = check_identity_strict("Copyright 2026 James", config)
        assert passed is False

    def test_fails_with_unknown(self):
        config = IdentityConfig(authors=["James Beck"])
        passed, findings = check_identity_strict("Copyright 2026 John Smith", config)
        assert passed is False


class TestLoadIdentityConfig:
    def test_missing_config_file(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        config = load_identity_config(gov_dir)
        assert config.authors == []
        assert config.organizations == []

    def test_load_from_toml(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        config_path = gov_dir / "config.toml"
        config_path.write_text('''
[identity]
authors = ["James Beck"]
organizations = ["Unpingable"]
''')
        config = load_identity_config(gov_dir)
        assert config.authors == ["James Beck"]
        assert config.organizations == ["Unpingable"]

    def test_load_with_aliases(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        config_path = gov_dir / "config.toml"
        config_path.write_text('''
[identity]
authors = ["James Beck"]

[identity.aliases]
"James Beck" = ["J. Beck", "Beck, J."]
''')
        config = load_identity_config(gov_dir)
        assert "J. Beck" in config.aliases.get("James Beck", [])


class TestIdentityInvariantCheck:
    def test_no_config_passes(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        passed, msg = identity_invariant_check("Copyright 2026 Anyone", gov_dir)
        assert passed is True
        assert "No identities configured" in msg

    def test_with_config_passes(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "config.toml").write_text('''
[identity]
authors = ["James Beck"]
''')
        passed, msg = identity_invariant_check("Copyright 2026 James Beck", gov_dir)
        assert passed is True

    def test_with_config_fails(self, tmp_path):
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "config.toml").write_text('''
[identity]
authors = ["James Beck"]
''')
        passed, msg = identity_invariant_check("Copyright 2026 James", gov_dir)
        assert passed is False
        assert "Incomplete" in msg or "James" in msg


class TestRealWorldExamples:
    def test_license_file_correct(self):
        config = IdentityConfig(authors=["James Beck"])
        text = """
        Apache License 2.0

        Copyright 2026 James Beck

        Licensed under the Apache License...
        """
        findings = check_identity(text, config)
        assert findings == []

    def test_license_file_incomplete(self):
        config = IdentityConfig(authors=["James Beck"])
        text = """
        Apache License 2.0

        Copyright 2026 James

        Licensed under the Apache License...
        """
        findings = check_identity(text, config)
        assert len(findings) == 1
        assert findings[0].match_type == IdentityMatchType.INCOMPLETE

    def test_readme_author_section(self):
        config = IdentityConfig(authors=["James Beck"])
        text = """
        # MyProject

        Author: James Beck

        ## Installation
        """
        findings = check_identity(text, config)
        assert findings == []

    def test_package_json_style(self):
        config = IdentityConfig(authors=["James Beck"])
        # Package.json style doesn't match our patterns (intentionally)
        text = '"author": "james@example.com"'
        findings = check_identity(text, config)
        # Email format shouldn't trigger author name detection
        assert findings == []

    def test_git_commit_style(self):
        config = IdentityConfig(authors=["James Beck"])
        text = "Co-Authored-By: James Beck <james@example.com>"
        # The "By:" pattern should match
        findings = check_identity(text, config)
        assert findings == []

    def test_hallucinated_variations(self):
        """Test various hallucinated name patterns that AI might produce."""
        config = IdentityConfig(authors=["James Beck"])

        # First name only
        findings = check_identity("Author: James", config)
        assert len(findings) == 1
        assert findings[0].match_type == IdentityMatchType.INCOMPLETE

        # Similar but wrong last name
        findings = check_identity("Author: James Becker", config)
        assert len(findings) == 1
        # Should be flagged as partial or unknown

        # Completely different name
        findings = check_identity("Author: Robert Johnson", config)
        assert len(findings) == 1
        assert findings[0].match_type == IdentityMatchType.UNKNOWN
