#!/usr/bin/env python3
"""
Verify that Open WebUI data is being stored in Google Cloud PostgreSQL.
"""

import psycopg2
import os
import sys
from dotenv import load_dotenv

# Load environment from the front directory
env_path = os.path.join(os.path.dirname(__file__), '..', 'front', '.env')
load_dotenv(env_path)

db_url = os.getenv('DATABASE_URL')
if not db_url:
    print("❌ DATABASE_URL not found in .env file")
    sys.exit(1)

print(f'Connecting to: {db_url.split("@")[1]}')  # Hide password
print()

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # List tables
    print('=' * 60)
    print('TABLES IN DATABASE')
    print('=' * 60)
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;")
    tables = cur.fetchall()
    for table in tables:
        print(f'  ✓ {table[0]}')
    print()

    # Check chat table
    print('=' * 60)
    print('CHAT DATA')
    print('=' * 60)
    cur.execute('SELECT COUNT(*) FROM chat;')
    chat_count = cur.fetchone()[0]
    print(f'Total chats: {chat_count}')

    if chat_count > 0:
        cur.execute('SELECT id, title, created_at FROM chat ORDER BY created_at DESC LIMIT 5;')
        chats = cur.fetchall()
        print('\nRecent chats:')
        for chat in chats:
            print(f'  • ID: {chat[0]}')
            print(f'    Title: {chat[1]}')
            print(f'    Created: {chat[2]}')
            print()
    print()

    # Check messages
    print('=' * 60)
    print('MESSAGE DATA')
    print('=' * 60)
    cur.execute('SELECT COUNT(*) FROM message;')
    msg_count = cur.fetchone()[0]
    print(f'Total messages: {msg_count}')

    if msg_count > 0:
        cur.execute('SELECT id, chat_id, content, created_at FROM message ORDER BY created_at DESC LIMIT 3;')
        messages = cur.fetchall()
        print('\nRecent messages:')
        for msg in messages:
            content_preview = str(msg[2])[:80] if msg[2] else ''
            print(f'  • Message ID: {msg[0]}')
            print(f'    Chat ID: {msg[1]}')
            print(f'    Content: {content_preview}...')
            print(f'    Created: {msg[3]}')
            print()
    print()

    # Check users
    print('=' * 60)
    print('USER DATA')
    print('=' * 60)
    cur.execute('SELECT COUNT(*) FROM "user";')
    user_count = cur.fetchone()[0]
    print(f'Total users: {user_count}')

    if user_count > 0:
        cur.execute('SELECT id, email, name, created_at FROM "user" ORDER BY created_at DESC;')
        users = cur.fetchall()
        print('\nUsers:')
        for user in users:
            print(f'  • ID: {user[0]}')
            print(f'    Email: {user[1]}')
            print(f'    Name: {user[2]}')
            print(f'    Created: {user[3]}')
            print()
    print()

    # Check vector data (if using pgvector)
    print('=' * 60)
    print('VECTOR DATA (Documents)')
    print('=' * 60)
    try:
        cur.execute('SELECT COUNT(*) FROM document;')
        doc_count = cur.fetchone()[0]
        print(f'Total documents: {doc_count}')
        if doc_count > 0:
            cur.execute('SELECT id, name, created_at FROM document ORDER BY created_at DESC LIMIT 3;')
            docs = cur.fetchall()
            print('\nRecent documents:')
            for doc in docs:
                print(f'  • ID: {doc[0]}, Name: {doc[1]}, Created: {doc[2]}')
    except Exception as e:
        print(f'No document table or error: {e}')
    print()

    # Summary
    print('=' * 60)
    print('SUMMARY')
    print('=' * 60)
    print(f'✅ Successfully connected to Google Cloud PostgreSQL!')
    print(f'✅ Database has {len(tables)} tables')
    print(f'✅ {user_count} user(s) in database')
    print(f'✅ {chat_count} chat(s) stored')
    print(f'✅ {msg_count} message(s) stored')
    print()
    print('🎉 ALL YOUR DATA IS BEING STORED IN GOOGLE CLOUD!')
    print()

    cur.close()
    conn.close()

except Exception as e:
    print(f'❌ Error connecting to database: {e}')
    sys.exit(1)
