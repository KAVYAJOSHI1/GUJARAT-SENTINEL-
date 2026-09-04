#!/usr/bin/env python3
"""
Idempotent database seed for a fresh SENTINEL deployment.

Creates the initial admin user (and optionally a watchlist entry) from
environment variables. Running it twice does not create duplicates.

Env:
    DATABASE_URL        postgresql+psycopg2://user:pass@host:5432/db
    ADMIN_USERNAME      (default "admin")
    ADMIN_EMAIL         (default "admin@sentinel.local")
    ADMIN_PASSWORD      REQUIRED -- no default, never hard-coded
    ADMIN_ROLE          ADMIN | OFFICER | OPERATOR   (default ADMIN)
    SEED_WATCHLIST_PLATE optional demo watchlist plate (e.g. GJ01AB1234)

Usage:
    cd backend && DATABASE_URL=... ADMIN_PASSWORD=... python ../scripts/seed_db.py
    # or from repo root with PYTHONPATH=backend
"""
import os
import sys

# allow running from repo root or backend/
_HERE = os.path.dirname(os.path.abspath(__file__))
for cand in (os.path.join(_HERE, "..", "backend"), os.path.join(_HERE, "..")):
    if os.path.isdir(os.path.join(cand, "app")):
        sys.path.insert(0, os.path.abspath(cand))
        break


def main() -> int:
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.core.security import hash_password
    from app.models.base import UserRole
    from app.models.user import User

    username = os.getenv("ADMIN_USERNAME", "admin")
    email = os.getenv("ADMIN_EMAIL", "admin@sentinel.local")
    password = os.getenv("ADMIN_PASSWORD")
    role_name = os.getenv("ADMIN_ROLE", "ADMIN").upper()

    if not password:
        print("ERROR: ADMIN_PASSWORD is required (not hard-coded).", file=sys.stderr)
        return 2
    if role_name not in UserRole.__members__:
        print(f"ERROR: ADMIN_ROLE must be one of {list(UserRole.__members__)}", file=sys.stderr)
        return 2

    created = 0
    with SessionLocal() as db:
        existing = db.execute(
            select(User).where((User.username == username) | (User.email == email))
        ).scalars().first()

        if existing is None:
            db.add(User(
                username=username,
                email=email,
                hashed_password=hash_password(password),
                role=UserRole[role_name],
                is_active=True,
            ))
            db.commit()
            created += 1
            print(f"created user '{username}' ({role_name})")
        else:
            print(f"user '{existing.username}' already exists — left unchanged")

        plate = os.getenv("SEED_WATCHLIST_PLATE")
        if plate:
            from app.models.watchlist import Watchlist
            from app.models.base import PriorityLevel
            from app.services.plate_utils import normalize_plate

            norm = normalize_plate(plate)
            wl = db.execute(
                select(Watchlist).where(Watchlist.plate_number_normalized == norm)
            ).scalars().first()
            if wl is None:
                db.add(Watchlist(
                    plate_number=plate,
                    plate_number_normalized=norm,
                    offense_category=os.getenv("SEED_WATCHLIST_CATEGORY", "Demo Watchlist"),
                    priority_level=PriorityLevel.HIGH,
                    active=True,
                ))
                db.commit()
                created += 1
                print(f"created watchlist entry '{norm}'")
            else:
                print(f"watchlist entry '{norm}' already exists — left unchanged")

    print(f"seed complete ({created} row(s) created)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
