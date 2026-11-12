import pytest

from bot.db.links import Item, StaleEditError, is_valid_code, new_code
from bot.db.roles import AddResult, Role, RolesRepo
from bot.db.targets import TELEGRAM, YOUTUBE, AddStatus
from tests.helpers import OWNER_ID

# --- users ---


async def test_touch_creates_and_updates_user(repos):
    await repos.users.touch(1, "Alice", "Al")
    assert await repos.users.find_id_by_username("@alice") == 1
    await repos.users.touch(1, "Renamed", "Al")
    assert await repos.users.find_id_by_username("alice") is None
    assert await repos.users.find_id_by_username("renamed") == 1


async def test_ban_is_seen_immediately_and_after_wipe(repos):
    await repos.users.touch(1, None, None)
    assert not await repos.users.is_banned(1)
    await repos.users.set_banned(1, True)
    assert await repos.users.is_banned(1)
    await repos.forget_local()
    assert await repos.users.is_banned(1)
    await repos.users.set_banned(1, False)
    assert not await repos.users.is_banned(1)


async def test_ban_unknown_user_by_id_keeps_them_banned_when_they_arrive(repos):
    await repos.users.set_banned(55, True)
    await repos.users.touch(55, "late", "Late")
    assert await repos.users.is_banned(55)


async def test_blocked_user_is_skipped_until_they_return(repos):
    for user_id in (1, 2, 3):
        await repos.users.touch(user_id, None, None)
    await repos.users.deactivate(2)
    await repos.users.set_banned(3, True)
    assert await repos.users.reachable_after(0) == [1]
    await repos.users.touch(2, None, None)
    assert await repos.users.reachable_after(0) == [1, 2]
    assert await repos.users.reachable_after(1) == [2]


async def test_pending_round_trip(repos):
    await repos.users.touch(1, None, None)
    assert await repos.users.get_pending(1) is None
    await repos.users.set_pending(1, "abc")
    assert await repos.users.get_pending(1) == "abc"
    await repos.users.set_pending(1, None)
    assert await repos.users.get_pending(1) is None


# --- roles ---


async def test_owner_comes_from_config(repos):
    assert await repos.roles.resolve(OWNER_ID, None) == Role.OWNER


async def test_extra_owners_have_the_owner_role(repos):
    roles = RolesRepo(repos.store, OWNER_ID, [7, 8])
    assert await roles.resolve(7, None) == Role.OWNER
    assert await roles.resolve(8, "anyone") == Role.OWNER
    assert await roles.resolve(9, None) == Role.USER


async def test_extra_owner_cannot_be_added_as_moderator(repos):
    roles = RolesRepo(repos.store, OWNER_ID, [7])
    assert await roles.add_by_id(7, OWNER_ID) == AddResult.IS_OWNER
    await repos.users.touch(7, "dev_one", "Dev")
    assert await roles.add_by_username("dev_one", OWNER_ID) == AddResult.IS_OWNER


async def test_stranger_is_user(repos):
    assert await repos.roles.resolve(5, "someone") == Role.USER


async def test_moderator_added_by_username_before_first_contact(repos):
    assert await repos.roles.add_by_username("@Mod_One", OWNER_ID) == AddResult.ADDED
    assert await repos.roles.resolve(5, "mod_one") == Role.MODERATOR
    assert await repos.roles.resolve(6, "other") == Role.USER


async def test_rename_keeps_access_and_new_holder_of_old_name_gets_nothing(repos):
    await repos.roles.add_by_username("modname", OWNER_ID)
    assert await repos.roles.resolve(5, "modname") == Role.MODERATOR
    assert await repos.roles.resolve(5, "brandnew") == Role.MODERATOR
    assert await repos.roles.resolve(6, "modname") == Role.USER
    await repos.forget_local()
    assert await repos.roles.resolve(6, "modname") == Role.USER
    assert await repos.roles.resolve(5, None) == Role.MODERATOR


async def test_adding_known_user_binds_id_at_once(repos):
    await repos.users.touch(7, "known", None)
    await repos.roles.add_by_username("known", OWNER_ID)
    assert await repos.roles.resolve(7, None) == Role.MODERATOR


async def test_cannot_add_twice_or_owner_or_nonsense(repos):
    await repos.users.touch(OWNER_ID, "boss", None)
    assert await repos.roles.add_by_username("boss", OWNER_ID) == AddResult.IS_OWNER
    await repos.roles.add_by_username("x_mod", OWNER_ID)
    assert await repos.roles.add_by_username("X_MOD", OWNER_ID) == AddResult.ALREADY
    assert await repos.roles.add_by_username("not a name!", OWNER_ID) == AddResult.INVALID
    assert await repos.roles.add_by_username("", OWNER_ID) == AddResult.INVALID


async def test_add_moderator_by_id_works_without_a_username(repos):
    assert await repos.roles.add_by_id(55, OWNER_ID) == AddResult.ADDED
    assert await repos.roles.resolve(55, None) == Role.MODERATOR  # No username at all.
    moderator = (await repos.roles.list_moderators())[0]
    assert moderator["user_id"] == 55 and moderator["username"] is None


async def test_add_moderator_by_id_rejects_duplicates_owner_and_nonsense(repos):
    await repos.roles.add_by_id(55, OWNER_ID)
    assert await repos.roles.add_by_id(55, OWNER_ID) == AddResult.ALREADY
    assert await repos.roles.add_by_id(OWNER_ID, OWNER_ID) == AddResult.IS_OWNER
    assert await repos.roles.add_by_id(0, OWNER_ID) == AddResult.INVALID
    assert await repos.roles.add_by_id(-5, OWNER_ID) == AddResult.INVALID


async def test_removal_takes_effect_immediately(repos):
    await repos.roles.add_by_username("gone", OWNER_ID)
    assert await repos.roles.resolve(9, "gone") == Role.MODERATOR
    moderator = (await repos.roles.list_moderators())[0]
    assert await repos.roles.remove(moderator["id"]) == (True, 9)
    assert await repos.roles.resolve(9, "gone") == Role.USER


async def test_removing_twice_is_harmless(repos):
    await repos.roles.add_by_username("gone", OWNER_ID)
    moderator = (await repos.roles.list_moderators())[0]
    await repos.roles.remove(moderator["id"])
    assert await repos.roles.remove(moderator["id"]) == (False, None)


async def test_env_seed_runs_once_so_removed_moderators_stay_removed(repos):
    await repos.roles.seed(["seeded"])
    moderator = (await repos.roles.list_moderators())[0]
    await repos.roles.remove(moderator["id"])
    await repos.roles.seed(["seeded"])
    assert await repos.roles.list_moderators() == []
    await repos.roles.seed(["seeded", "second"])
    assert [m["username"] for m in await repos.roles.list_moderators()] == ["second"]


# --- settings ---


async def test_settings_default_and_false_values(repos):
    assert await repos.settings.get("protect", "fallback") == "fallback"
    await repos.settings.set("protect", False)
    assert await repos.settings.get("protect", True) is False
    await repos.forget_local()
    assert await repos.settings.get("protect", True) is False


async def test_several_settings_are_read_in_one_round_trip(repos, monkeypatch):
    await repos.settings.set("caption", "hello")
    await repos.settings.set("button", {"text": "Join", "url": "https://t.me/x"})
    await repos.forget_local()

    reads = 0
    real = repos.store.db.read

    async def counting(operation):
        nonlocal reads
        reads += 1
        return await real(operation)

    monkeypatch.setattr(repos.store.db, "read", counting)
    wanted = await repos.settings.get_many("caption", "button", "missing")
    assert wanted == {
        "caption": "hello",
        "button": {"text": "Join", "url": "https://t.me/x"},
        "missing": None,
    }
    assert reads == 1
    assert (await repos.settings.get_many("caption", "button"))["caption"] == "hello"
    assert reads == 1  # The second look was answered locally.


# --- links ---


def items(*ids):
    return [Item(channel_id=-100, message_id=i) for i in ids]


def test_codes_are_valid_deep_links():
    code = new_code()
    assert len(code) == 12 and is_valid_code(code)
    assert not is_valid_code("bad code!")
    assert not is_valid_code("x" * 65)
    assert not is_valid_code("")


async def test_link_round_trip_and_wipe(repos):
    code = await repos.links.create("genlink", OWNER_ID, items(5, 6))
    link = await repos.links.get(code)
    assert [i["message_id"] for i in link["items"]] == [5, 6]
    await repos.forget_local()
    assert [i["message_id"] for i in (await repos.links.get(code))["items"]] == [5, 6]


async def test_missing_or_junk_codes_return_none(repos):
    assert await repos.links.get("nosuchcode") is None
    assert await repos.links.get("../../etc") is None


async def test_old_item_keeps_its_own_channel(repos):
    code = await repos.links.create("genlink", OWNER_ID, [Item(channel_id=-1, message_id=1)])
    await repos.links.append(code, [Item(channel_id=-2, message_id=1)])
    assert [i["channel_id"] for i in (await repos.links.get(code))["items"]] == [-1, -2]


async def test_append_is_visible_after_a_cached_read(repos):
    code = await repos.links.create("batch", OWNER_ID, items(1))
    await repos.links.get(code)
    await repos.links.append(code, items(2))
    assert len((await repos.links.get(code))["items"]) == 2


async def test_second_editor_of_special_link_is_refused(repos):
    code = await repos.links.create("special", OWNER_ID, items(1, 2), title="T")
    link = await repos.links.get(code)
    new_version = await repos.links.replace_items(code, link["items"][:1], link["version"])
    assert new_version == link["version"] + 1
    with pytest.raises(StaleEditError):
        await repos.links.replace_items(code, [], link["version"])
    assert len((await repos.links.get(code))["items"]) == 1


async def test_reorder_rewrites_positions(repos):
    code = await repos.links.create("special", OWNER_ID, items(1, 2, 3))
    link = await repos.links.get(code)
    await repos.links.replace_items(code, list(reversed(link["items"])), link["version"])
    assert [i["message_id"] for i in (await repos.links.get(code))["items"]] == [3, 2, 1]


async def test_deleted_link_disappears_from_cache(repos):
    code = await repos.links.create("special", OWNER_ID, items(1))
    await repos.links.get(code)
    await repos.links.delete(code)
    assert await repos.links.get(code) is None


async def test_list_special_counts_items(repos):
    await repos.links.create("genlink", OWNER_ID, items(1))
    code = await repos.links.create("special", OWNER_ID, items(1, 2), title="Pack")
    assert await repos.links.list_special() == [{"code": code, "title": "Pack", "items": 2}]


async def test_export_contains_every_link(repos):
    code = await repos.links.create("genlink", OWNER_ID, items(1))
    exported = await repos.links.export_all()
    assert exported == [{"code": code, "kind": "genlink", "title": None, "items": [[-100, 1]]}]


# --- targets and verification versions ---


async def add_youtube(repos, identity="@one", name="One"):
    return await repos.targets.add(YOUTUBE, identity, name, f"https://youtube.com/{identity}")


async def valid(repos, user_id, target):
    versions = await repos.targets.verified_versions(user_id)
    current = await repos.targets.get(target["id"])
    return versions.get(str(target["id"])) == current["version"]


async def test_new_target_needs_verification_but_others_remain_valid(repos):
    one, status = await add_youtube(repos)
    assert status == AddStatus.ADDED
    await repos.targets.mark_verified(1, one, "screenshot")
    two, _ = await add_youtube(repos, "@two", "Two")
    assert await valid(repos, 1, one)
    assert not await valid(repos, 1, two)


async def test_adding_duplicate_is_reported(repos):
    await add_youtube(repos)
    _, status = await add_youtube(repos)
    assert status == AddStatus.ALREADY
    assert len(await repos.targets.list_active()) == 1


async def test_removed_target_leaves_list_at_once(repos):
    one, _ = await add_youtube(repos)
    await repos.targets.list_active()
    await repos.targets.remove(one["id"])
    assert await repos.targets.list_active() == []


async def test_removing_and_readding_same_channel_keeps_verification(repos):
    one, _ = await add_youtube(repos)
    await repos.targets.mark_verified(1, one, "screenshot")
    await repos.targets.remove(one["id"])
    again, status = await add_youtube(repos)
    assert status == AddStatus.READDED and again["id"] == one["id"]
    assert await valid(repos, 1, again)


async def test_replacing_with_different_channel_requires_verification(repos):
    one, _ = await add_youtube(repos)
    await repos.targets.mark_verified(1, one, "screenshot")
    new, status = await repos.targets.replace(one["id"], "@new", "New", "https://youtube.com/@new")
    assert status == AddStatus.ADDED
    assert [t["identity"] for t in await repos.targets.list_active()] == ["@new"]
    assert not await valid(repos, 1, new)


async def test_replacing_with_channel_already_listed_is_harmless(repos):
    one, _ = await add_youtube(repos)
    await add_youtube(repos, "@two", "Two")
    _, status = await repos.targets.replace(one["id"], "@two", "Two", "u")
    assert status == AddStatus.ALREADY
    assert [t["identity"] for t in await repos.targets.list_active()] == ["@two"]


async def test_fixing_name_or_link_does_not_ask_again(repos):
    one, _ = await add_youtube(repos)
    await repos.targets.mark_verified(1, one, "screenshot")
    await repos.targets.rename(one["id"], "Better Name")
    await repos.targets.set_url(one["id"], "https://youtube.com/@one/")
    assert await valid(repos, 1, one)
    assert (await repos.targets.list_active())[0]["display_name"] == "Better Name"


async def test_ask_everyone_again_only_touches_that_channel(repos):
    one, _ = await add_youtube(repos)
    two, _ = await add_youtube(repos, "@two", "Two")
    await repos.targets.mark_verified(1, one, "screenshot")
    await repos.targets.mark_verified(1, two, "screenshot")
    await repos.targets.ask_everyone_again(one["id"])
    assert not await valid(repos, 1, one)
    assert await valid(repos, 1, two)


async def test_verification_survives_disk_wipe(repos):
    one, _ = await add_youtube(repos)
    await repos.targets.mark_verified(1, one, "screenshot")
    await repos.forget_local()
    assert await valid(repos, 1, one)


async def test_failures_count_up_and_reset_on_success(repos):
    one, _ = await add_youtube(repos)
    assert await repos.targets.record_failure(1, one) == 1
    assert await repos.targets.record_failure(1, one) == 2
    await repos.targets.mark_verified(1, one, "screenshot")
    assert await valid(repos, 1, one)
    await repos.targets.ask_everyone_again(one["id"])
    current = await repos.targets.get(one["id"])
    assert await repos.targets.record_failure(1, current) == 1


async def test_failure_does_not_count_as_verified(repos):
    one, _ = await add_youtube(repos)
    await repos.targets.record_failure(1, one)
    assert not await valid(repos, 1, one)


async def test_group_upgrade_moves_chat_id_and_keeps_verification(repos):
    group, _ = await repos.targets.add(TELEGRAM, "-5", "Group", "u", chat_id=-5)
    await repos.targets.mark_verified(1, group, "join_request")
    await repos.targets.migrate_chat(-5, -1005)
    moved = await repos.targets.find_by_chat(-1005)
    assert moved["id"] == group["id"]
    assert await valid(repos, 1, moved)
    assert await repos.targets.find_by_chat(-5) is None


async def test_numbers_are_not_usernames(repos):
    assert await repos.roles.add_by_username("12345", OWNER_ID) == AddResult.INVALID
    assert await repos.roles.add_by_username("_name", OWNER_ID) == AddResult.INVALID
    assert await repos.roles.add_by_username("a" * 33, OWNER_ID) == AddResult.INVALID


async def test_reachable_count_skips_blocked_and_banned(repos):
    for user_id in (1, 2, 3):
        await repos.users.touch(user_id, None, None)
    await repos.users.deactivate(1)
    await repos.users.set_banned(2, True)
    assert await repos.users.count_reachable() == 1
