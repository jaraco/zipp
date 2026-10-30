Cache a directory index on the first ``Path.iterdir()`` call for read-only
archives, avoiding repeated archive-wide scans during subsequent traversal.
Release the directory index when the archive closes.
