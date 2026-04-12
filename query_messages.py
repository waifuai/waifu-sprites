#!/usr/bin/env python3
"""Query messages for a session from hermes state.db"""
import sqlite3, json, sys

if len(sys.argv) < 3:
    print(json.dumps({"error": "Usage: query_messages.py <db_path> <session_id>"}))
    sys.exit(1)

db_path = sys.argv[1]
session_id = sys.argv[2]

try:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
      WITH RECURSIVE session_tree AS (
        SELECT id FROM sessions WHERE id = ?
        UNION ALL
        SELECT s.id FROM sessions s
        INNER JOIN session_tree st ON s.parent_session_id = st.id
      )
      SELECT role, content, tool_name, tool_calls, tool_call_id, timestamp
      FROM messages
      WHERE session_id IN (SELECT id FROM session_tree)
      ORDER BY timestamp, id
    """, [session_id])
    
    rows = cursor.fetchall()
    messages = []
    for row in rows:
        if row['role'] in ['user', 'assistant'] and row['content'] and row['content'].strip():
            messages.append({
                'role': row['role'],
                'content': row['content'] or '',
                'timestamp': row['timestamp']
            })
    
    conn.close()
    print(json.dumps(messages))
except Exception as e:
    print(json.dumps({"error": str(e)}))
    sys.exit(1)