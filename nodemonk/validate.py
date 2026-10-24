"""Schema validation for extraction dicts.  Honesty requires guardrails.

Every extractor product must fit:
  {"nodes": [{"id", "label", "file_type", "source_file", "source_location"?}],
   "edges": [{"source", "target", "relation", "confidence", "confidence_score"?}]}
Confidence is one of EXTRACTED | INFERRED | AMBIGUOUS - never invented.
"""

from __future__ import annotations

from typing import Any

VALID_FILE_TYPES = {"code", "document", "paper", "image", "data", "media", "rationale"}
VALID_CONFIDENCE = {"EXTRACTED", "INFERRED", "AMBIGUOUS"}


def validate_extraction(data: dict[str, Any], origin: str = "<unknown>") -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"{origin}: extraction is not an object"]

    seen: set[str] = set()
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        errors.append(f"{origin}: 'nodes' must be a list")
        nodes = []
    for i, node in enumerate(nodes):
        if not isinstance(node, dict):
            errors.append(f"{origin}: node[{i}] not an object")
            continue
        nid = node.get("id")
        if not nid or not isinstance(nid, str):
            errors.append(f"{origin}: node[{i}] missing string 'id'")
            continue
        if nid in seen:
            errors.append(f"{origin}: duplicate node id {nid!r}")
        seen.add(nid)
        if not node.get("label"):
            errors.append(f"{origin}: node[{i}] ({nid}) missing 'label'")
        ft = node.get("file_type")
        if ft is not None and ft not in VALID_FILE_TYPES:
            errors.append(f"{origin}: node[{i}] ({nid}) bad file_type {ft!r}")

    edges = data.get("edges")
    if not isinstance(edges, list):
        errors.append(f"{origin}: 'edges' must be a list")
        edges = []
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"{origin}: edge[{i}] not an object")
            continue
        if not edge.get("source") or not edge.get("target"):
            errors.append(f"{origin}: edge[{i}] missing source/target")
            continue
        if edge.get("source") not in seen or edge.get("target") not in seen:
            # tolerate: build() will auto-create endpoints, but flag suspicious
            errors.append(
                f"{origin}: edge[{i}] references unknown node "
                f"{edge.get('source')!r}->{edge.get('target')!r}"
            )
        conf = edge.get("confidence")
        if conf is not None and conf not in VALID_CONFIDENCE:
            errors.append(f"{origin}: edge[{i}] bad confidence {conf!r} (EXTRACTED|INFERRED|AMBIGUOUS)")

    hyperedges = data.get("hyperedges")
    if hyperedges is not None and not isinstance(hyperedges, list):
        errors.append(f"{origin}: 'hyperedges' must be a list when present")
    return errors


def assert_valid(data: dict[str, Any], origin: str = "<unknown>") -> None:
    errors = validate_extraction(data, origin)
    if errors:
        preview = "; ".join(errors[:10])
        raise ValueError(f"invalid extraction from {origin}: {preview} (+{max(0, len(errors) - 10)} more)")
