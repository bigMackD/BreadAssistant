"""Store round trips, migrations and invalid data preservation."""

from copy import deepcopy

import pytest
from homeassistant.exceptions import ConfigEntryError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.bread_assistant.const import DOMAIN
from custom_components.bread_assistant.coordinator import BakeCoordinator
from custom_components.bread_assistant.models import DomainError
from custom_components.bread_assistant.serialization import (
    bake_from_dict,
    bake_to_dict,
    migrate_payload,
)
from custom_components.bread_assistant.storage import BakeStorage

from .test_schedule import START, bake


def test_additive_starter_migration():
    record = bake_to_dict(bake())
    del record["starter_id"]
    del record["starter_workflow"]
    payload = migrate_payload({"bake": record}, 1)
    restored = bake_from_dict(payload["bake"])
    assert restored.starter_id is None
    assert restored.starter_workflow == "feed"
    with pytest.raises(DomainError, match="Unsupported"):
        migrate_payload(payload, 99)


async def test_real_store_roundtrip(hass, hass_storage):
    store = BakeStorage(hass)
    original = bake(starter_id="rye", starter_workflow="prepared")
    await store.async_save(original, [])
    restored, archives = await BakeStorage(hass).async_load()
    assert restored == original
    assert archives == []
    assert hass_storage["bread_assistant.bakes"]["version"] == 2


async def test_legacy_archives_and_retention_limit(hass, hass_storage):
    legacy = {"id": "old-summary", "done_count": 21}
    archives = [legacy] + [{"id": f"bake-{i}"} for i in range(50)]
    await BakeStorage(hass).async_save(bake(), archives)
    _, restored = await BakeStorage(hass).async_load()
    assert restored == archives[-50:]
    await BakeStorage(hass).async_save(bake(), [legacy])
    _, restored = await BakeStorage(hass).async_load()
    assert restored == [legacy]


async def test_live_activity_metadata_roundtrip_and_old_v2_default(hass, hass_storage):
    from custom_components.bread_assistant.models import LiveActivity

    store = BakeStorage(hass)
    original = bake()
    records = [LiveActivity(original.id, "notify.mobile_app_iphone", START)]
    await store.async_save(original, [], live_activities=records)
    restored = BakeStorage(hass)
    assert (await restored.async_load())[0] == original
    assert restored.live_activities == records
    del hass_storage["bread_assistant.bakes"]["data"]["live_activities"]
    old = BakeStorage(hass)
    assert (await old.async_load())[0] == original
    assert old.live_activities == []


@pytest.mark.parametrize("metadata", [None, {}, [{"bake_id": "broken"}]])
async def test_invalid_live_metadata_does_not_overwrite_store(
    hass, hass_storage, metadata
):
    await BakeStorage(hass).async_save(bake(), [])
    hass_storage["bread_assistant.bakes"]["data"]["live_activities"] = metadata
    original = deepcopy(hass_storage["bread_assistant.bakes"])
    with pytest.raises(DomainError, match="Invalid live activity"):
        await BakeStorage(hass).async_load()
    assert hass_storage["bread_assistant.bakes"] == original


async def test_store_v1_migration(hass, hass_storage):
    record = bake_to_dict(bake())
    del record["starter_id"]
    hass_storage["bread_assistant.bakes"] = {
        "version": 1,
        "minor_version": 1,
        "key": "bread_assistant.bakes",
        "data": {"bake": record, "archives": []},
    }
    restored, _ = await BakeStorage(hass).async_load()
    assert restored.starter_id is None


async def test_corrupt_payload_fails_without_overwrite(hass, hass_storage):
    store = BakeStorage(hass)
    await store.async_save(bake(), [])
    hass_storage["bread_assistant.bakes"]["data"]["bake"]["step_runs"] = {}
    stored = deepcopy(hass_storage["bread_assistant.bakes"])
    coordinator = BakeCoordinator(hass, MockConfigEntry(domain=DOMAIN), lambda: START)
    with pytest.raises(ConfigEntryError, match="Cannot restore"):
        await coordinator.async_load()
    assert hass_storage["bread_assistant.bakes"] == stored


async def test_future_store_version_is_not_overwritten(hass, hass_storage):
    from homeassistant.exceptions import UnsupportedStorageVersionError

    hass_storage["bread_assistant.bakes"] = {
        "version": 99,
        "minor_version": 1,
        "key": "bread_assistant.bakes",
        "data": {"schema_version": 99, "bake": None},
    }
    original = deepcopy(hass_storage["bread_assistant.bakes"])
    with pytest.raises(UnsupportedStorageVersionError):
        await BakeStorage(hass).async_load()
    assert hass_storage["bread_assistant.bakes"] == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("notification_generation", -1),
        ("planned_at", None),
        ("status", "impossible"),
        ("step_id", "other_step"),
    ],
)
def test_invalid_step_snapshot(field, value):
    record = bake_to_dict(bake())
    record["step_runs"]["feed_starter"][field] = value
    with pytest.raises(DomainError, match="Invalid stored bake"):
        bake_from_dict(record)
