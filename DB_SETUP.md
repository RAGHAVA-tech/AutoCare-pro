DB setup — Postgres privileges

If you encounter "permission denied for schema public" when the app tries to create tables, run the grants below as a Postgres superuser.

PowerShell (recommended on Windows):

```powershell
# Run the helper script (it will prompt for the postgres superuser password)
.\scripts\grant_privileges.ps1
```

Interactive psql (prompts for password):

```bash
psql -U postgres -h localhost -p 5432 -d autocare -c "GRANT USAGE ON SCHEMA public TO autocare_user; GRANT CREATE ON SCHEMA public TO autocare_user;"
```

Non-interactive one-liner (be careful with embedding passwords):

```bash
psql "postgresql://postgres:SUPERPASS@localhost:5432/autocare" -c "GRANT USAGE ON SCHEMA public TO autocare_user; GRANT CREATE ON SCHEMA public TO autocare_user;"
```

After applying grants, run the app or execute:

```bash
python -c "from db import init_db; init_db()"
```

Notes:
- These commands must be run as a superuser (for managed DBs use your cloud provider console or ask your DBA).
- If you can't get CREATE privileges for `public`, consider creating a schema owned by `autocare_user` and setting the search_path for the role.
