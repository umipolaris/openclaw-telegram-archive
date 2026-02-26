#!/usr/bin/env python3
"""초기 관리자 계정을 생성/갱신한다.

사용 예시:
  python scripts/bootstrap_admin.py --username admin --password 'ChangeMe123!'
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.security import hash_password
from app.db.models import User, UserRole
from app.db.session import SessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap local admin account")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="")
    parser.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.ADMIN.value)
    parser.add_argument("--reset-password", action="store_true")
    parser.add_argument("--activate", action="store_true", default=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    role = UserRole(args.role)

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.username == args.username)).scalar_one_or_none()

        if user:
            changed = False

            if user.role != role:
                user.role = role
                changed = True

            if args.activate and not user.is_active:
                user.is_active = True
                changed = True

            if args.reset_password:
                if not args.password:
                    raise SystemExit("--reset-password 사용 시 --password는 필수입니다.")
                user.password_hash = hash_password(args.password)
                changed = True

            if changed:
                db.add(user)
                db.commit()
                print(f"updated user: {user.username} role={user.role.value}")
            else:
                print(f"user already exists: {user.username} role={user.role.value}")
            return

        if not args.password:
            raise SystemExit("신규 생성 시 --password는 필수입니다.")

        user = User(
            username=args.username,
            password_hash=hash_password(args.password),
            role=role,
            is_active=True,
            created_by=None,
        )
        db.add(user)
        db.commit()
        print(f"created user: {user.username} role={user.role.value}")


if __name__ == "__main__":
    main()
