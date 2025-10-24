# db_session.py
import json
import asyncpg
from telethon.sessions import MemorySession


class PostgresSession(MemorySession):
    def __init__(self, phone: str, db_pool):
        super().__init__()  # <== WAJIB! agar _state dibuat oleh Telethon
        self.phone = phone
        self.db_pool = db_pool

    async def load(self):
        """Load session dari PostgreSQL"""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT session_data FROM telethon_sessions WHERE phone=$1",
                self.phone,
            )
            if not row or not row["session_data"]:
                print(f"[DB] No saved session for {self.phone}")
                return

            try:
                data = row["session_data"].decode() if isinstance(row["session_data"], (bytes, bytearray)) else row["session_data"]
                self._load(data)  # built-in dari MemorySession
                print(f"[DB] Loaded session for {self.phone}")
            except Exception as e:
                print(f"[WARN] Failed to load session: {e}")

    async def save_state(self):
        """Simpan session ke PostgreSQL"""
        try:
            # cek apakah session punya auth_key
            if not hasattr(self, "_state") or not self._state or not self._state.auth_key:
                print(f"[PostgresSession.save_state] skip saving empty session for {self.phone}")
                return

            data = self.save()  # MemorySession.save() -> string
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO telethon_sessions (phone, session_data, updated_at)
                    VALUES ($1, $2::bytea, NOW())
                    ON CONFLICT (phone)
                    DO UPDATE SET
                        session_data = EXCLUDED.session_data,
                        updated_at = NOW();
                    """,
                    self.phone,
                    data.encode(),
                )
            print(f"[DB] Session saved for {self.phone}")
        except Exception as e:
            print(f"[WARN] Failed to save session: {e}")

    async def delete(self):
        """Hapus session dari PostgreSQL"""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM telethon_sessions WHERE phone=$1",
                self.phone,
            )
        print(f"[DB] Session deleted for {self.phone}")

    async def close(self):
        await self.save_state()
        await super().close()