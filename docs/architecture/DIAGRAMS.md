# Architecture Diagrams

Generated from system structure. If these drift from reality, regenerate — don't hand-edit.

---

## Run Lifecycle

```mermaid
stateDiagram-v2
    [*] --> DRAFT: propose
    DRAFT --> PROPOSED: submit
    PROPOSED --> VERIFIED: verify (receipts produced)
    PROPOSED --> REJECTED: verify (evidence insufficient)
    VERIFIED --> APPLIED: apply (writes committed)
    REJECTED --> [*]
    APPLIED --> [*]
```

## Claim Promotion

```mermaid
stateDiagram-v2
    [*] --> PROPOSED: agent claims
    PROPOSED --> SUPPORTED: evidence attached
    SUPPORTED --> CONTESTED: contradiction found
    CONTESTED --> SUPPORTED: resolved in favor
    CONTESTED --> INVALIDATED: refuted
    SUPPORTED --> STALE: TTL expired
    STALE --> SUPPORTED: revalidated
    STALE --> EXPIRED: not revalidated
    PROPOSED --> REFUSED: rejected at gate
    INVALIDATED --> [*]
    EXPIRED --> [*]
    REFUSED --> [*]
```

## Invariant Hierarchy

```mermaid
graph TD
    K[Kernel Constraints<br><i>law — cannot be disabled</i>] --> A
    A[Anchors<br><i>decisions — persist until revised</i>] --> P
    P[Profile<br><i>UX preferences — adjustable</i>] --> U
    U[UI Controls<br><i>convenience — ephemeral</i>]

    style K fill:#d32f2f,color:#fff
    style A fill:#f57c00,color:#fff
    style P fill:#1976d2,color:#fff
    style U fill:#388e3c,color:#fff
```

## Regime Detection

```mermaid
stateDiagram-v2
    ELASTIC --> WARM: tool_gain rising
    WARM --> DUCTILE: sustained pressure
    DUCTILE --> UNSTABLE: thresholds breached
    UNSTABLE --> DUCTILE: pressure easing
    DUCTILE --> WARM: recovery
    WARM --> ELASTIC: stable
    UNSTABLE --> ELASTIC: emergency reset
```

## Interferometry Flow

```mermaid
graph LR
    P[Prompt] --> M1[Model A]
    P --> M2[Model B]
    M1 --> E1[Claim Extraction]
    M2 --> E2[Claim Extraction]
    E1 --> D{Claim Diff}
    E2 --> D
    D --> S[Shared Claims]
    D --> U[Unique Claims]
    D --> C[Conflicts]
    C --> R[Risk Markers]
    S --> L[Ledger Promotion]
```

## Capsule Structure (Session Continuity)

```mermaid
graph TD
    subgraph Capsule
        L[Ledger Layer<br><i>decisions, anchors, facts</i>]
        W[Workspace Layer<br><i>file hashes, dirty state</i>]
        T[Transcript Layer<br><i>compacted summary</i>]
    end

    L --> Resume[Resume Session]
    W --> Resume
    T --> Resume

    Capsule --> F[Fork]
    F --> Child[Child Capsule]
    Child --> Promote[Promote to Mainline]
```

## Adaptive Control Loop

```mermaid
graph TD
    H[Homeostat<br><i>exploration budgets</i>] -->|TuningIntent| U[Ultrastability<br><i>S₁ parameters</i>]
    U -->|freeze feedback| H
    U --> R[Regime Detector<br><i>ELASTIC→UNSTABLE</i>]
    R --> B[Boil Controller<br><i>GREEN_TEA→BOIL</i>]
    B --> G[Governance Gates<br><i>strict/exploratory</i>]
```

## Fiction Governor

```mermaid
graph TD
    B[Story Bible<br><i>characters, world, tone</i>] --> V[Verifiers]
    C[Canon Ledger<br><i>events, threads</i>] --> V
    V --> IC[InCharacterVerifier]
    V --> TV[TropeVerifier]
    V --> TN[ToneVerifier]
    V --> NV[NarrativeVerifier]
    IC --> R{Result}
    TV --> R
    TN --> R
    NV --> R
    R -->|pass| Accept
    R -->|fail| Violation[Violation + Resolution]
```
