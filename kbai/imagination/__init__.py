"""Imagination — propose new research domains by reading cluster shape.

Stage 10. Reasons over *absence*: what's structurally missing from a cluster.
Unlike retrieve/expand/connect tools which surface what's present, imagination
identifies the conceptual frontier and asks where to push next.

Architecture matches Council Mode (Stage 5.6): this layer is pure data —
cluster signature extraction + mode-specific synthesizer prompt. The LLM call
is Claude reading the ImaginationEvidence bundle via the /imagine slash
command. No separate synthesis agent.

Five modes — complete coverage across the conceptual compass:
  extend       — sideways. What neighbouring domain extends this?
  fracture     — adversarial. What would break this cluster's assumptions?
  bridge       — cross-cluster. What connects this to a distant cluster?
  deepen       — downward. What mechanism sits under this?
  historicise  — backward. What intellectual lineage does this inherit?
"""

from kbai.imagination.signature import extract_cluster_signature
from kbai.imagination.prompts import build_synthesis_prompt, MODES
from kbai.imagination.imagine import imagine

__all__ = [
    "extract_cluster_signature",
    "build_synthesis_prompt",
    "imagine",
    "MODES",
]
