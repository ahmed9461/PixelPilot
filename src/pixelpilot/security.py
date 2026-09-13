from __future__ import annotations


def is_owner(user_id: int | None, owner_id: int) -> bool:
    return user_id is not None and owner_id > 0 and user_id == owner_id
