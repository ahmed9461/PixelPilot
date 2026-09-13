import asyncio

from pixelpilot.db import Database


def test_db_set_get_and_generation(tmp_path):
    async def scenario():
        db = Database(tmp_path / "state.sqlite3")
        await db.init()
        await db.set("instance.id", 999)
        assert await db.get("instance.id") == 999
        assert await db.get("missing", "x") == "x"
        await db.event("test", {"ok": True})

        gen_id = await db.create_generation(prompt="hello", seed=10, instance_id=999, status="created", result={"x": 1})
        assert gen_id == 1
        await db.update_generation(gen_id, status="completed", prompt_id="p1", result={"images": []})
        row = await db.get_generation(gen_id)
        assert row["status"] == "completed"
        assert row["prompt_id"] == "p1"
        assert row["result"] == {"images": []}

    asyncio.run(scenario())
