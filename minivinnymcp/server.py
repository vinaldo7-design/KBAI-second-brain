import os
import sys
import sqlite3
from pathlib import Path

_vault_root = Path(os.environ["VAULT_ROOT"])
sys.path.insert(0, str(_vault_root))

import sqlite_vec
from sentence_transformers import SentenceTransformer
from mcp.server.fastmcp import FastMCP

from vault_search import serialize_embedding, QUERY_PREFIX, MODEL_NAME

_DB_PATH = _vault_root / "06-Maps" / "vault-embeddings.db"
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


app = FastMCP("mini-vinny")


@app.tool()
def vault_search(query: str, top_k: int = 5) -> list[dict]:
    """Semantic search over vault note summaries."""
    qvec = _get_model().encode(QUERY_PREFIX + query, normalize_embeddings=True)

    db = sqlite3.connect(_DB_PATH)
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)

    rows = db.execute(
        """
        SELECT v.note_id, v.distance, n.title, n.summary, n.filepath
        FROM note_vectors v
        JOIN notes n ON n.id = v.note_id
        WHERE v.embedding MATCH ? AND k = ?
        ORDER BY v.distance
        """,
        (serialize_embedding(qvec), top_k),
    ).fetchall()
    db.close()

    return [
        {
            "note_id": nid,
            "score": float(dist),
            "title": title,
            "summary": summary,
            "filepath": fp,
        }
        for nid, dist, title, summary, fp in rows
    ]


if __name__ == "__main__":
    app.run()
