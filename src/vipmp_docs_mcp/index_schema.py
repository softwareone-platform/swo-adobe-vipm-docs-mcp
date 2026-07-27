"""
On-disk schema version for the structured index.

Kept in its own leaf module because both `index.py` (which writes and reads
the snapshot) and `remote_index.py` (which rejects a GitHub-fetched copy
whose version doesn't match) need it. Holding it here lets both import it
at module level instead of reaching for each other lazily, which is what
previously made the two modules mutually dependent.

Bump this whenever the on-disk shape of the index changes, so a stale
cached or remote copy is rejected instead of silently misread.
"""

from __future__ import annotations

INDEX_SCHEMA_VERSION = 5  # v5 added `status_codes` (resource lifecycle states, 1000-1026).
