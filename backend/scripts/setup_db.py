import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

conn = psycopg2.connect(host='127.0.0.1', port=5432, user='postgres', password='password', dbname='postgres')
conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur = conn.cursor()

cur.execute("SELECT 1 FROM pg_database WHERE datname='absensi_dprd'")
if not cur.fetchone():
    cur.execute("CREATE DATABASE absensi_dprd")
    print("Database 'absensi_dprd' created!")
else:
    print("Database 'absensi_dprd' already exists.")

cur.execute("SELECT 1 FROM pg_roles WHERE rolname='dprd_user'")
if not cur.fetchone():
    cur.execute("CREATE USER dprd_user WITH PASSWORD 'strongpassword'")
    cur.execute("GRANT ALL PRIVILEGES ON DATABASE absensi_dprd TO dprd_user")
    print("User 'dprd_user' created and granted!")
else:
    cur.execute("ALTER USER dprd_user WITH PASSWORD 'strongpassword'")
    print("User 'dprd_user' updated!")

conn.close()

conn2 = psycopg2.connect(host='127.0.0.1', port=5432, user='postgres', password='password', dbname='absensi_dprd')
conn2.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
cur2 = conn2.cursor()
cur2.execute("GRANT ALL ON SCHEMA public TO dprd_user")
cur2.execute("GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO dprd_user")
cur2.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO dprd_user")
conn2.close()
print("PostgreSQL setup completed successfully!")
