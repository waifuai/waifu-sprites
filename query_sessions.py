#!/usr/bin/env python3
"""Query sessions from hermes state.db"""
import sqlite3, json, sys

if len(sys.argv) < 4:
    print(json.dumps({"error": "Usage: query_sessions.py <db_path> <limit> <offset>"}))
    sys.exit(1)

db_path = sys.argv[1]
limit = int(sys.argv[2])
offset = int(sys.argv[3])

try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
      SELECT s.*,
        COALESCE(
          (SELECT SUBSTR(REPLACE(REPLACE(m.content, X'0A', ' '), X'0D', ' '), 1, 63)
           FROM messages m
           WHERE m.session_id = s.id AND m.role = 'user' AND m.content IS NOT NULL
           ORDER BY m.timestamp, m.id LIMIT 1),
          ''
        ) AS _preview_raw,
        COALESCE(
          (SELECT MAX(m2.timestamp) FROM messages m2 WHERE m2.session_id = s.id),
          s.started_at
        ) AS last_active
      FROM sessions s
      WHERE s.parent_session_id IS NULL
      ORDER BY s.started_at DESC
      LIMIT ? OFFSET ?
    """, [limit, offset])
    
    rows = cursor.fetchall()
    sessions = []
    for row in rows:
        raw = (row['_preview_raw'] or '').strip()
        sessions.append({
            'id': row['id'],
            'source': row['source'],
            'user_id': row['user_id'],
            'model': row['model'],
            'title': row['title'],
            'started_at': row['started_at'],
            'ended_at': row['ended_at'],
            'end_reason': row['end_reason'],
            'parent_session_id': row['parent_session_id'],
            'preview': (raw[:60] + '...') if len(raw) > 60 else raw,
            'last_active': row['last_active']
        })
    
    conn.close()
    print(json.dumps(sessions))
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)