"""Unit tests for src/discord_config.py.

Run: `python3 tests/discord-config.test.py`
"""
import importlib.util
import json
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "discord_config.py"

sys.path.insert(0, str(ROOT / "src"))


def _load(workspace: Path):
    os.environ["SUTANDO_WORKSPACE"] = str(workspace)
    os.environ.pop("SUTANDO_DM_OWNER_ID", None)
    spec = importlib.util.spec_from_file_location("discord_config", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestConfigPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        os.environ.pop("SUTANDO_DM_OWNER_ID", None)
        self.tmp.cleanup()

    def test_path_under_workspace_state(self):
        path = self.mod.config_path()
        self.assertEqual(path.parent.name, "state")
        self.assertEqual(path.name, "discord-config.json")
        self.assertTrue(str(path).startswith(str(self.ws)))


class TestLoadConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        os.environ.pop("SUTANDO_DM_OWNER_ID", None)
        self.tmp.cleanup()

    def _write_config(self, data: dict):
        path = self.mod.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(self.mod.load_config(), {})

    def test_reads_valid_json(self):
        self._write_config({"owner": "U123", "tierMap": {"U456": "team"}})
        cfg = self.mod.load_config()
        self.assertEqual(cfg["owner"], "U123")
        self.assertEqual(cfg["tierMap"]["U456"], "team")

    def test_corrupted_file_returns_empty_dict(self):
        path = self.mod.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json }{")
        self.assertEqual(self.mod.load_config(), {})


class TestSaveConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        os.environ.pop("SUTANDO_DM_OWNER_ID", None)
        self.tmp.cleanup()

    def test_creates_state_dir_if_missing(self):
        self.mod.save_config({"owner": "U999"})
        self.assertTrue(self.mod.config_path().exists())

    def test_round_trips_data(self):
        self.mod.save_config({"owner": "U888", "tierMap": {"U777": "owner"}})
        cfg = self.mod.load_config()
        self.assertEqual(cfg["owner"], "U888")
        self.assertEqual(cfg["tierMap"]["U777"], "owner")

    def test_overwrites_existing_config(self):
        self.mod.save_config({"owner": "U111"})
        self.mod.save_config({"owner": "U222"})
        self.assertEqual(self.mod.load_config()["owner"], "U222")


class TestResolveOwnerId(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        os.environ.pop("SUTANDO_DM_OWNER_ID", None)
        self.tmp.cleanup()

    def test_env_var_wins_over_everything(self):
        os.environ["SUTANDO_DM_OWNER_ID"] = "U_ENV"
        result = self.mod.resolve_owner_id(
            {"owner": "U_ACCESS", "allowFrom": ["U_ACCESS"]},
            config={"owner": "U_CONFIG"},
        )
        self.assertEqual(result, "U_ENV")

    def test_workspace_owner_field(self):
        result = self.mod.resolve_owner_id(
            {},
            config={"owner": "U_WS"},
        )
        self.assertEqual(result, "U_WS")

    def test_workspace_tier_map_owner(self):
        result = self.mod.resolve_owner_id(
            {"allowFrom": ["U_A", "U_B"]},
            config={"tierMap": {"U_A": "team", "U_B": "owner"}},
        )
        self.assertEqual(result, "U_B")

    def test_legacy_access_owner_field(self):
        result = self.mod.resolve_owner_id(
            {"owner": "U_LEGACY"},
            config={},
        )
        self.assertEqual(result, "U_LEGACY")

    def test_legacy_tier_map_owner(self):
        result = self.mod.resolve_owner_id(
            {"allowFrom": ["U_X", "U_Y"], "tierMap": {"U_X": "team", "U_Y": "owner"}},
            config={},
        )
        self.assertEqual(result, "U_Y")

    def test_returns_none_when_no_candidates(self):
        result = self.mod.resolve_owner_id({}, config={})
        self.assertIsNone(result)

    def test_env_var_whitespace_stripped(self):
        os.environ["SUTANDO_DM_OWNER_ID"] = "  U_TRIM  "
        result = self.mod.resolve_owner_id({}, config={})
        self.assertEqual(result, "U_TRIM")

    def test_workspace_owner_whitespace_stripped(self):
        result = self.mod.resolve_owner_id({}, config={"owner": "  U_WS_TRIM  "})
        self.assertEqual(result, "U_WS_TRIM")

    def test_resolution_priority_env_over_ws_owner(self):
        os.environ["SUTANDO_DM_OWNER_ID"] = "U_ENV"
        result = self.mod.resolve_owner_id({}, config={"owner": "U_WS"})
        self.assertEqual(result, "U_ENV")

    def test_resolution_priority_ws_owner_over_ws_tiermap(self):
        result = self.mod.resolve_owner_id(
            {"allowFrom": ["U_T"]},
            config={"owner": "U_WS", "tierMap": {"U_T": "owner"}},
        )
        self.assertEqual(result, "U_WS")

    def test_resolution_priority_ws_tiermap_over_legacy_owner(self):
        result = self.mod.resolve_owner_id(
            {"owner": "U_LEGACY", "allowFrom": ["U_T"]},
            config={"tierMap": {"U_T": "owner"}},
        )
        self.assertEqual(result, "U_T")

    def test_empty_string_owner_not_returned(self):
        result = self.mod.resolve_owner_id({}, config={"owner": ""})
        self.assertIsNone(result)

    def test_allow_from_not_in_tier_map_not_returned(self):
        # allowFrom entry with no tierMap match → None (no allowFrom[0] fallback here)
        result = self.mod.resolve_owner_id(
            {"allowFrom": ["U_UNKNOWN"]},
            config={},
        )
        self.assertIsNone(result)

    def test_reads_disk_config_when_none_passed(self):
        state = self.ws / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "discord-config.json").write_text(json.dumps({"owner": "U_DISK"}))
        result = self.mod.resolve_owner_id({})
        self.assertEqual(result, "U_DISK")


class TestAutoSeedIfMissing(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        self.log = logging.getLogger("test")

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        os.environ.pop("SUTANDO_DM_OWNER_ID", None)
        self.tmp.cleanup()

    def test_seeds_from_access_owner_field(self):
        cfg = self.mod.auto_seed_if_missing(
            {"owner": "U_LEGACY", "allowFrom": ["U_LEGACY"]},
            logger_=self.log,
        )
        self.assertEqual(cfg["owner"], "U_LEGACY")
        self.assertTrue(self.mod.config_path().exists())

    def test_seeds_from_tier_map(self):
        cfg = self.mod.auto_seed_if_missing(
            {"allowFrom": ["U_A", "U_B"], "tierMap": {"U_A": "team", "U_B": "owner"}},
            logger_=self.log,
        )
        self.assertEqual(cfg["owner"], "U_B")

    def test_falls_back_to_allow_from_zero(self):
        cfg = self.mod.auto_seed_if_missing(
            {"allowFrom": ["U_FIRST"]},
            logger_=self.log,
        )
        self.assertEqual(cfg["owner"], "U_FIRST")

    def test_empty_access_data_writes_empty_config(self):
        cfg = self.mod.auto_seed_if_missing({}, logger_=self.log)
        self.assertNotIn("owner", cfg)

    def test_idempotent_when_file_exists(self):
        # Write config first
        self.mod.auto_seed_if_missing({"owner": "U_FIRST"}, logger_=self.log)
        # Second call with different access data should NOT overwrite
        cfg2 = self.mod.auto_seed_if_missing({"owner": "U_SECOND"}, logger_=self.log)
        self.assertEqual(cfg2["owner"], "U_FIRST")

    def test_mirrors_tier_map_when_present(self):
        cfg = self.mod.auto_seed_if_missing(
            {"owner": "U_OWN", "tierMap": {"U_A": "team", "U_B": "owner"}},
            logger_=self.log,
        )
        self.assertIn("tierMap", cfg)
        self.assertEqual(cfg["tierMap"]["U_A"], "team")

    def test_no_tier_map_in_access_means_none_in_seed(self):
        cfg = self.mod.auto_seed_if_missing(
            {"owner": "U_OWN"},
            logger_=self.log,
        )
        self.assertNotIn("tierMap", cfg)


if __name__ == "__main__":
    unittest.main()
