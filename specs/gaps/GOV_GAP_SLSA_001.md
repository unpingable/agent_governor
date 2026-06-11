# GOV-GAP-SLSA-001: Supply-Chain Provenance Ingestion

Status: `open` (3.x — requires principal_ref, auth_method from v2.6 placeholders)

## Problem

Governor can verify "did tests pass?" and "is the lockfile committed?" but
cannot answer "is this artifact's provenance chain intact?" CI receipts prove
local execution. They don't prove the artifact wasn't tampered with between
build and deploy, or that dependencies are what they claim to be.

The supply-chain provenance ecosystem (SLSA, in-toto, Sigstore, SBOMs) already
solves the hard problems: attestation formats, signing, transparency logs. Governor
doesn't need to reinvent any of this. It needs to **require** these artifacts,
**parse** them, **bind** them into receipts, and **refuse to proceed** without them.

## What This Is

Governor as a **provenance admissibility checker**: given a set of supply-chain
attestations, determine whether the artifact's story is coherent and meets policy.

## What This Is NOT

- Not a build system (CI is the actuator — see GOV_GAP_CI_LANE_001)
- Not a signing service (Sigstore/cosign does that)
- Not a transparency log (Rekor does that)
- Not an SBOM generator (Syft, Trivy, etc. do that)
- Not a PKI (Fulcio does that)

Governor **consumes** these artifacts. It doesn't produce them.

## Background: The Ecosystem

### SLSA v1.0 (Supply-chain Levels for Software Artifacts)

Four levels of build integrity:

| Level | What It Means | Governor Relevance |
|-------|--------------|-------------------|
| L0 | No guarantees | Not admissible |
| L1 | Provenance exists, build documented | Minimum: attestation parses, subject matches |
| L2 | Source-aware, signed artifacts | Signer identity verified, builder ID present |
| L3 | Hardened build, source-derived definitions | Full provenance chain, insider threat mitigation |

SLSA provenance is an **in-toto predicate** — a typed metadata schema bound
to an artifact subject via the in-toto attestation framework.

### in-toto Attestation Framework

Four-layer composable structure:

1. **Predicate** — type-specific metadata (SLSA provenance, SBOM, etc.)
2. **Statement** — binds predicate to artifact subject (hash + type)
3. **Envelope** — authentication wrapper (DSSE — Dead Simple Signing Envelope)
4. **Bundle** — groups multiple attestations

Governor cares about layers 1-3: parse the envelope, verify the statement
binds to the artifact, validate the predicate contents against policy.

### Sigstore (keyless signing)

- Cosign creates ephemeral keypair (20-minute lifetime)
- OIDC identity verification (GitHub Actions, Google, etc.)
- Fulcio issues short-lived cert binding key → identity
- Rekor logs signing event (transparency)
- Verification: certificate identity + OIDC issuer + Rekor entry

Governor verifies: "is the signer's identity in the approved set?" Not
"is the cryptography correct?" (cosign/sigstore libraries handle that).

### SBOMs (SPDX / CycloneDX)

| | SPDX | CycloneDX |
|--|------|-----------|
| Origin | Linux Foundation (ISO 5962) | OWASP |
| Strength | License compliance | Vulnerability management |
| Format | JSON/RDF/tag-value | JSON/XML |

Governor doesn't prefer one. It requires: parses, binds to artifact digest,
contains dependency inventory. Format is policy, not architecture.

## Design: Two Phases

### Phase A: Integrity Checks (v3.0 — no identity binding)

Add `EvidenceType` values that `governor ci verify` and `governor gate check`
can require. Initially enforce only structural integrity:

```python
class EvidenceType(str, Enum):
    # ... existing types ...
    SLSA_PROVENANCE = "slsa_provenance"       # in-toto SLSA predicate
    COSIGN_ATTESTATION = "cosign_attestation" # Sigstore bundle
    SBOM_SPDX = "sbom_spdx"                  # SPDX document
    SBOM_CYCLONEDX = "sbom_cyclonedx"         # CycloneDX BOM
    INTOTO_ATTESTATION = "intoto_attestation" # Generic in-toto envelope
```

For each, verification checks:

1. **Exists** — attestation file present
2. **Parses** — valid JSON/envelope structure
3. **Binds** — subject digest matches artifact digest
4. **Predicate valid** — required fields present, timestamps sane

These are **mechanical checks**, not identity verification. A malicious
attestation with valid structure passes Phase A. That's fine — Phase A
is "chain intact," not "chain trustworthy."

#### Attestation verifiers

```python
@dataclass(frozen=True)
class AttestationVerifyResult:
    evidence_type: EvidenceType
    artifact_digest: str          # sha256:<hex>
    subject_match: bool           # attestation subject == artifact
    predicate_type: str           # e.g. "https://slsa.dev/provenance/v1"
    builder_id: str | None        # from SLSA provenance
    source_ref: str | None        # git SHA from provenance
    timestamp: str | None         # ISO 8601
    issues: list[str]             # parse/validation warnings
```

One verifier per evidence type. All pure functions, no network calls.
Parsing libraries: `json` for SLSA/in-toto/CycloneDX, `spdx-tools` for
SPDX (or just JSON parsing if SPDX JSON format).

#### Policy integration

```ini
[ci.release]
required_attestations = slsa_provenance, sbom_spdx
artifact_digest_algorithm = sha256
min_slsa_level = 1
```

`governor ci verify` checks: required attestation types present, all
bind to the same artifact digest, all pass structural verification.

#### Receipt binding

Attestation verify results become evidence entries in the CI lane's
meta-receipt. `evidence_hash` includes attestation digests. The receipt
doesn't contain the attestation — it references it by digest.

### Phase B: Identity Binding (v3.x — requires auth_method + principal_ref)

This is where the v2.6 bake-in placeholders pay rent.

#### Signer identity verification

```python
@dataclass(frozen=True)
class SignerPolicy:
    allowed_identities: list[str]      # OIDC subjects (email, repo URI)
    allowed_issuers: list[str]         # OIDC issuer URLs
    allowed_builders: list[str]        # SLSA builder IDs
    require_rekor_entry: bool = True   # Transparency log inclusion
```

Verification: "is the signer's OIDC identity in the approved set, issued
by an approved provider, for an approved builder?" This is the
`principal_ref` use case — the receipt's `principal_ref` becomes
`H(signer_identity)`.

#### Trust model

Governor doesn't trust attestations because they're signed. It trusts
them because:

1. The signer identity is in the policy's approved set
2. The signing event is in a transparency log
3. The attestation binds to the artifact
4. The predicate contents are structurally valid

This is **policy-based trust**, not **cryptographic trust**. Governor
delegates crypto verification to Sigstore libraries and makes
admissibility decisions based on the result.

#### auth_method mapping

| Source | auth_method | principal_ref |
|--------|------------|---------------|
| Local CI (no signing) | `"local"` | `None` |
| GitHub Actions OIDC | `"oidc"` | `sha256:H(repo_uri)` |
| Cosign keyless | `"sigstore"` | `sha256:H(oidc_subject)` |
| Manual key signing | `"mtls"` or `"key"` | `sha256:H(public_key)` |

## Implementation Scope

### Phase A (v3.0)

| Item | Size | Depends On |
|------|------|-----------|
| `EvidenceType` additions | XS | evidence_gate.py |
| SLSA provenance verifier | S | json parsing only |
| in-toto envelope verifier | S | json parsing only |
| SBOM verifiers (SPDX + CycloneDX) | S | json parsing only |
| Cosign bundle verifier | S | json parsing only |
| `ci verify --attestations` flag | S | GOV_GAP_CI_LANE_001 |
| Policy pack attestation requirements | S | ci.conf |
| Receipt binding for attestations | S | gate_receipt.py |

No new dependencies. All verifiers parse JSON. Crypto verification
(signature checking) is Phase B.

### Phase B (v3.x)

| Item | Size | Depends On |
|------|------|-----------|
| Sigstore verification integration | M | `sigstore-python` dep |
| Signer policy model | S | — |
| principal_ref population from signer | S | gate_receipt.py |
| auth_method population from source | S | daemon.py |
| Rekor transparency log check | M | network call |
| SLSA level determination | S | provenance verifier |

Phase B adds the `sigstore-python` dependency (or shells out to `cosign`).
This is the first external trust dependency.

## SLSA Level Mapping

Governor can determine and enforce SLSA levels based on available evidence:

| Governor Check | SLSA Level |
|---------------|-----------|
| Provenance attestation exists, parses | L1 |
| + signed by approved builder identity | L2 |
| + source ref matches, build hermetic | L3 |

L3 requires build-system cooperation (hermetic builds, pinned deps).
Governor can't enforce hermeticity — it can require the builder to
**attest** to it and refuse to proceed without that attestation.

## Explicitly Out of Scope

- Generating attestations (build tools do that)
- Running a transparency log (Rekor does that)
- Key management (Sigstore/Fulcio does that)
- SBOM generation (Syft, Trivy, etc. do that)
- VEX (Vulnerability Exploitability eXchange) — future gap if needed
- Multi-repo supply chain graphs (PaaS territory)

## References

- [SLSA v1.0 specification](https://slsa.dev/spec/v1.0/)
- [in-toto attestation framework](https://github.com/in-toto/attestation)
- [Sigstore documentation](https://docs.sigstore.dev/)
- [SPDX specification (ISO 5962)](https://spdx.dev/specifications/)
- [CycloneDX specification](https://cyclonedx.org/specification/overview/)
- See also: `docs/REFERENCES.md` (design ancestors — tamper-evident logs)
