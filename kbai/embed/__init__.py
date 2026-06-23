"""kbai.embed — per-note embedding indexer + on-write reindex hook.

Public surface:
  embed_note  — embed/refresh one note's summary into the sqlite-vec index.
  get_model   — lazy, cached SentenceTransformer(MODEL_NAME) getter.
  hash_summary — SHA-256(16-hex) summary hash shared with vault_embed.
"""

from kbai.embed.indexer import embed_note, get_model, hash_summary

__all__ = ["embed_note", "get_model", "hash_summary"]
