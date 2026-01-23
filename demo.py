#!/usr/bin/env python3
"""
Demo: Agent Governor catching agent hallucinations.

This demonstrates the core value proposition:
- Agent can't claim files exist when they don't
- Agent can't contradict prior architectural decisions
- All rejections are logged for proof/debugging
"""

import tempfile
from pathlib import Path

from governor import AgentGovernor, Evidence


def main():
    # Create a temporary "project" directory
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir)
        
        # Create some actual files
        (project_root / "package.json").write_text('{"dependencies": {"react": "^18.0.0"}}')
        (project_root / "src").mkdir()
        (project_root / "src" / "App.jsx").write_text("export default function App() {}")
        
        # Initialize governor
        governor = AgentGovernor(project_root)
        
        print("=" * 60)
        print("EPISTEMIC GOVERNOR DEMO")
        print("=" * 60)
        print()
        
        # ===== SCENARIO 1: Valid commitment =====
        print("SCENARIO 1: Agent claims React is the framework (valid)")
        print("-" * 40)
        
        result = governor.propose(
            claim="Using React for frontend framework",
            topic="framework",
            paths=["package.json", "src/App.jsx"],  # These files exist (relative to git_root)
        )
        
        print(f"  Claim: {result.claim}")
        print(f"  Status: {result.status.value}")
        print(f"  Evidence: {result.evidence.type if result.evidence else 'None'}")
        print()
        
        # ===== SCENARIO 2: Hallucinated file =====
        print("SCENARIO 2: Agent claims API file exists (HALLUCINATION)")
        print("-" * 40)
        
        result = governor.propose(
            claim="API endpoint defined in api/users.py",
            topic="api",
            paths=["api/users.py"],  # This file does NOT exist
        )
        
        print(f"  Claim: {result.claim}")
        print(f"  Status: {result.status.value}")
        print(f"  Rejection: {result.rejection_reason}")
        print()
        
        # ===== SCENARIO 3: Architectural contradiction =====
        print("SCENARIO 3: Agent tries to use Vue (CONTRADICTION)")
        print("-" * 40)
        
        # First, let's make a Vue file exist to make the evidence pass
        (project_root / "src" / "App.vue").write_text("<template><div>Vue</div></template>")
        
        result = governor.propose(
            claim="Using Vue for frontend framework",
            topic="framework",
            paths=["src/App.vue"],  # File exists, but contradicts React commitment
        )
        
        print(f"  Claim: {result.claim}")
        print(f"  Status: {result.status.value}")
        print(f"  Contradiction: {result.contradiction}")
        print()
        
        # ===== SCENARIO 4: Query context =====
        print("SCENARIO 4: Agent queries architectural context")
        print("-" * 40)
        
        context = governor.get_context()
        print(context)
        
        # ===== STATS =====
        print("=" * 60)
        print("TELEMETRY")
        print("=" * 60)
        print(f"  Total commitments: {governor.stats['total_commitments']}")
        print(f"  Total rejections: {governor.stats['total_rejections']}")
        print(f"  Rejection rate: {governor.stats['rejection_rate']:.1%}")
        print()
        
        # ===== REJECTION LOG =====
        print("REJECTION LOG (proof of hallucination prevention)")
        print("-" * 40)
        for rejection in governor.get_rejection_log():
            print(f"  [{rejection['timestamp'][:19]}]")
            print(f"    Claim: {rejection['claim']}")
            print(f"    Reason: {rejection['reason']}")
            print()


if __name__ == "__main__":
    main()
