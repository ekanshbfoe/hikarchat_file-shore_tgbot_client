from tests.helpers import OWNER_ID


async def test_recent_returns_newest_first_with_details(repos):
    await repos.audit.record(OWNER_ID, "link_created", code="abc", count=3)
    await repos.audit.record(OWNER_ID, "ban", user=55)
    lines = await repos.audit.recent(OWNER_ID)
    assert [line["action"] for line in lines] == ["ban", "link_created"]
    assert lines[0]["details"] == {"user": 55}
    assert lines[1]["details"] == {"code": "abc", "count": 3}


async def test_actions_are_kept_apart_per_actor(repos):
    await repos.audit.record(OWNER_ID, "ban", user=1)
    await repos.audit.record(7, "link_created", code="x", count=1)
    assert [line["action"] for line in await repos.audit.recent(OWNER_ID)] == ["ban"]
    assert [line["action"] for line in await repos.audit.recent(7)] == ["link_created"]


async def test_history_survives_a_disk_wipe(repos):
    await repos.audit.record(OWNER_ID, "unban", user=9)
    await repos.forget_local()
    assert (await repos.audit.recent(OWNER_ID))[0]["action"] == "unban"


async def test_ban_and_genlink_are_recorded(world):
    await world.owner.send("/genlink")
    await world.owner.send("some text")
    await world.owner.tap("collect:done")
    await world.owner.send("/ban 55")
    lines = await world.app.audit.recent(OWNER_ID)
    actions = [line["action"] for line in lines]
    assert "link_created" in actions and "ban" in actions
    ban = lines[0]
    assert ban["action"] == "ban" and ban["details"]["user"] == 55
