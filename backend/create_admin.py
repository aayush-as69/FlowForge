"""Provision the first production tenant administrator after Alembic migrations."""
import os, sys
from pathlib import Path
BACKEND = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND))
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models import Organization, User
from app.services.seed import seed_base

def main():
    email = os.environ.get("FLOWFORGE_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("FLOWFORGE_ADMIN_PASSWORD", "")
    name = os.environ.get("FLOWFORGE_ADMIN_NAME", "FlowForge Administrator").strip()
    org_name = os.environ.get("FLOWFORGE_ORG_NAME", "Your Organization").strip()
    if not email or "@" not in email: raise SystemExit("FLOWFORGE_ADMIN_EMAIL must be a valid email address.")
    if len(password) < 14: raise SystemExit("FLOWFORGE_ADMIN_PASSWORD must be at least 14 characters.")
    db = SessionLocal()
    try:
        org = db.query(Organization).first()
        if org is None:
            org = seed_base(db, include_demo_users=False)
            org.name = org_name
            db.commit()
        if db.query(User).filter(User.email == email).first():
            raise SystemExit("That administrator email already exists; refusing to overwrite it.")
        db.add(User(org_id=org.id, email=email, name=name, role="admin", department="Administration", password_hash=hash_password(password)))
        db.commit()
        print(f"Created administrator {email} for organisation {org.name!r}.")
    finally: db.close()

if __name__ == "__main__": main()
