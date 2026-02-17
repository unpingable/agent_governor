# SPDX-License-Identifier: Apache-2.0
"""
Evidence Validators: Grounding checks for claims.

Per NLAI, claims must be grounded in external evidence.
Validators check that claimed facts are actually true.
"""

import hashlib
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from .types import Evidence


class Validator(ABC):
    """Base class for evidence validators."""
    
    @abstractmethod
    def validate(self, claim: str, **kwargs) -> Optional[Evidence]:
        """
        Validate a claim and return evidence if valid.
        
        Returns None if the claim cannot be validated.
        """
        pass
    
    @abstractmethod
    def can_handle(self, claim: str, **kwargs) -> bool:
        """Check if this validator can handle the given claim type."""
        pass


class FileValidator(Validator):
    """
    Validates claims about file existence and content.
    
    Handles claims like:
    - "File X exists"
    - "API endpoint defined in X"
    - "Component X is in directory Y"
    """
    
    def __init__(self, git_root: Path):
        self.git_root = Path(git_root)
    
    def can_handle(self, claim: str, **kwargs) -> bool:
        """Check if claim can be validated with file evidence."""
        # If paths are explicitly provided, we can handle it
        if kwargs.get("paths"):
            return True
        # Otherwise check for file-related keywords in the claim
        keywords = ["file", "exists", "defined in", "located in", "found in", "path"]
        return any(kw in claim.lower() for kw in keywords)
    
    def validate(self, claim: str, paths: Optional[list[str]] = None, **kwargs) -> Optional[Evidence]:
        """
        Validate file existence claims.
        
        Args:
            claim: The claim being made
            paths: List of file paths that should exist to validate the claim
        """
        if not paths:
            return None
        
        validated_paths = []
        content_hashes = []
        
        for path_str in paths:
            path = self.git_root / path_str
            
            if not path.exists():
                return None  # Claim invalid - file doesn't exist
            
            if not path.is_file():
                return None  # Not a file
            
            # Hash the content for provenance
            try:
                content = path.read_bytes()
                content_hash = hashlib.sha256(content).hexdigest()[:16]
                validated_paths.append(path_str)
                content_hashes.append(content_hash)
            except Exception:
                return None
        
        # All paths validated
        return Evidence(
            type="file_exists",
            source=", ".join(validated_paths),
            content_hash=":".join(content_hashes),
        )


class TestValidator(Validator):
    """
    Validates claims by running tests.
    
    Handles claims like:
    - "Tests pass"
    - "Unit tests for X pass"
    - "Test coverage meets threshold"
    """
    
    def __init__(self, git_root: Path, test_command: str = "pytest"):
        self.git_root = Path(git_root)
        self.test_command = test_command
    
    def can_handle(self, claim: str, **kwargs) -> bool:
        """Check if claim is about tests."""
        keywords = ["test", "tests pass", "coverage", "pytest", "unittest"]
        return any(kw in claim.lower() for kw in keywords)
    
    def validate(
        self, 
        claim: str, 
        test_pattern: Optional[str] = None,
        **kwargs
    ) -> Optional[Evidence]:
        """
        Validate by actually running tests.
        
        Args:
            claim: The claim being made
            test_pattern: Optional pattern to filter tests (e.g., "test_api*")
        """
        cmd = [self.test_command]
        
        if test_pattern:
            cmd.extend(["-k", test_pattern])
        
        cmd.append("--tb=no")  # Minimal output
        cmd.append("-q")  # Quiet mode
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.git_root,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            
            if result.returncode == 0:
                # Tests passed - create evidence
                output_hash = hashlib.sha256(result.stdout.encode()).hexdigest()[:16]
                return Evidence(
                    type="test_passed",
                    source=f"command: {' '.join(cmd)}",
                    content_hash=output_hash,
                )
            else:
                # Tests failed
                return None
                
        except subprocess.TimeoutExpired:
            return None
        except FileNotFoundError:
            # Test runner not installed
            return None


class PatternValidator(Validator):
    """
    Validates claims about code patterns by checking existing usage.
    
    Handles claims like:
    - "This follows the existing pattern"
    - "This is consistent with how we do X"
    """
    
    def __init__(self, git_root: Path):
        self.git_root = Path(git_root)
    
    def can_handle(self, claim: str, **kwargs) -> bool:
        """Check if claim is about patterns."""
        keywords = ["pattern", "consistent", "follows", "matches", "like existing"]
        return any(kw in claim.lower() for kw in keywords)
    
    def validate(
        self,
        claim: str,
        pattern: Optional[str] = None,
        example_files: Optional[list[str]] = None,
        **kwargs
    ) -> Optional[Evidence]:
        """
        Validate pattern claims by checking example files contain the pattern.
        
        Args:
            claim: The claim being made
            pattern: Regex or string pattern to search for
            example_files: Files that should contain this pattern
        """
        if not pattern or not example_files:
            return None
        
        import re
        
        found_in = []
        
        for file_path in example_files:
            path = self.git_root / file_path
            if not path.exists():
                continue
            
            try:
                content = path.read_text()
                if re.search(pattern, content):
                    found_in.append(file_path)
            except Exception:
                continue
        
        if found_in:
            return Evidence(
                type="pattern_match",
                source=f"Pattern '{pattern}' found in: {', '.join(found_in)}",
            )
        
        return None


class CompositeValidator(Validator):
    """
    Combines multiple validators, trying each in order.
    """
    
    def __init__(self, validators: list[Validator]):
        self.validators = validators
    
    def can_handle(self, claim: str, **kwargs) -> bool:
        """Check if any validator can handle the claim."""
        return any(v.can_handle(claim, **kwargs) for v in self.validators)
    
    def validate(self, claim: str, **kwargs) -> Optional[Evidence]:
        """Try each validator that can handle the claim."""
        for validator in self.validators:
            if validator.can_handle(claim, **kwargs):
                evidence = validator.validate(claim, **kwargs)
                if evidence:
                    return evidence
        return None
