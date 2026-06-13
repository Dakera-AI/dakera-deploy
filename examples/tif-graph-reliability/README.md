# T-I-F Graph Reliability Handoff

This note is a Phase 4 handoff for the Dakera T-I-F decision provenance RFC:

https://github.com/Dakera-AI/dakera-deploy/issues/161

It is intentionally documentation-only. It does not request an engine rewrite,
SDK schema change, recall filter, or new server endpoint.

The goal is to leave a compact build path for a future graph-reliability
validation package.

## Core Question

Phase 1 and Phase 2 asked:

```text
Should this recalled memory be reused?
```

Phase 4 asks:

```text
Should this association path be trusted?
```

Dakera already has graph primitives where reliability can be evaluated at more
than one layer:

| Layer | Dakera surface | Reliability question |
|---|---|---|
| Memory node | `metadata.reliability` | Is this memory reliable before reuse? |
| Graph edge | edge type and edge weight | Is this association reliable? |
| Traversal path | graph path / associated recall | Is this multi-hop path trustworthy? |
| Neighborhood | associated memories | Does nearby context confirm, weaken, or contradict the primary result? |

## Dakera Surfaces To Inspect

The most relevant existing surfaces are:

- `dakera_recall_associated`
- `include_associated=true`
- `associated_memories_depth`
- `associated_memories_min_weight`
- `dakera_graph_traverse`
- `dakera_graph_path`
- `dakera_graph_link_memory`
- `dakera_graph_export`
- `dakera_knowledge_graph`
- cross-agent knowledge network support

The useful edge concepts are:

- `related_to`
- `shares_entity`
- `precedes`
- `linked_by`
- edge `weight`
- traversal `depth`

## Suggested Build Order

### 1. Keep Node Reliability Stable

Do not change the Phase 3 T-I-F v1 contract.

Use existing memory-level reliability:

```json
{
  "metadata": {
    "reliability": {
      "truth": 0.75,
      "indeterminacy": 0.10,
      "falsity": 0.15,
      "classification": "confident_reuse",
      "feedback_count": 12
    }
  }
}
```

Node reliability answers whether one memory is safe to reuse.

### 2. Derive Edge Reliability Agent-Side

Do not add engine behavior first. Start with a validation script that derives
edge reliability from existing graph output:

```text
edge type
edge weight
explicit link versus inferred similarity
source node reliability
target node reliability
session evidence
feedback history
```

First-pass rule:

```text
explicit linked_by edge:
  truth += 0.15

related_to edge:
  truth += edge.weight
  indeterminacy += 1.0 - edge.weight

shares_entity edge:
  truth += 0.55
  indeterminacy += 0.30

precedes edge:
  truth += 0.50
  indeterminacy += 0.35

if source or target node falsity >= 0.50:
  edge falsity = max(edge falsity, 0.50)
```

Clamp values to `[0.0, 1.0]`.

### 3. Derive Path Reliability

For a path:

```text
A -> B -> C
```

start conservatively:

```text
path.truth = min(all node truth, all edge truth)
path.indeterminacy = max(all node indeterminacy, all edge indeterminacy, hop penalty)
path.falsity = max(all node falsity, all edge falsity)
```

Example hop penalty:

```text
0 hops -> 0.00
1 hop  -> 0.05
2 hops -> 0.12
3 hops -> 0.20
```

This makes the path no more reliable than its weakest required support.

### 4. Preserve Contradiction Evidence

High-falsity memories should remain visible as diagnostic graph evidence.

Do not silently delete or hide them.

Expected behavior:

```text
primary memory: reusable
associated memory: high falsity
agent result: reuse with surfaced contradiction evidence, or verify_before_use
```

## Validation Scenarios

### Reliable Node, Weak Edge

Goal:

Show that a reliable memory should not be reused confidently when the
association that brought it into context is weak.

Expected result:

```text
node-only action: confident_reuse
graph-aware action: verify_before_use
```

### Contradiction Neighbor

Goal:

Show that associated recall can surface a contradicted memory as evidence.

Expected result:

```text
primary action: reuse current memory
graph diagnostic: surface outdated memory as contradiction evidence
```

### Multi-Hop Uncertainty

Goal:

Show that useful memories reached through uncertain intermediate nodes should
carry caveats.

Expected result:

```text
node-only action: reuse
graph-aware action: ask_clarification or verify_before_use
```

### Cross-Agent Similarity Caveat

Goal:

Show that cross-agent network links should be treated more cautiously than
same-agent explicit links unless reinforced by feedback or session evidence.

Expected result:

```text
cross-agent association: reuse_with_caveat
```

## NSS Reading Path

These sources are the recommended mathematical reading order for continuing the
graph track.

1. Start with connection-level cognitive maps:

   https://fs.unm.edu/NSS/ANewNeutrosophicCognitiveMap-NSS.22.pdf

   This is the closest source for Dakera because it treats relations and
   connections as neutrosophic objects. That maps well to memory associations
   and edge reliability.

2. Then read the general graph foundation:

   https://fs.unm.edu/NSS/NeutrosophicGraphs22.pdf

   This gives the broader graph frame where vertices and edges can carry truth,
   indeterminacy, and falsity.

3. Then inspect structural graph measures:

   https://fs.unm.edu/NSS/IntroductionToTopological4.pdf

   This is useful for path, degree, connectivity, and traversal reliability.

4. Finally, use this as a practical cognitive-map example:

   https://fs.unm.edu/NSS/27CognitiveMaps.pdf

   This helps keep the graph direction practical: identify concepts, model
   relations, compare consensus, disagreement, and indeterminacy.

## Non-Goals

This handoff does not propose:

- engine changes;
- SDK schema changes;
- recall filters;
- new MCP tools;
- graph database migration;
- quaternion, Euler, or Riemann implementation;
- deletion or filtering of contradiction memories.

## Suggested Future Artifact

If this track continues later, the smallest useful package would be:

```text
examples/tif-graph-reliability/
  validate_tif_graph_reliability.py
  phase4_graph_scenarios.json
  README.md
  VALIDATION_RESULTS.md
```

The validator should score node, edge, path, and neighborhood reliability
outside the engine, then report whether graph-aware decisions differ from
node-only decisions.

## Boundary

This is a handoff. It is designed so maintainers can continue independently
from the source links and build path above.
