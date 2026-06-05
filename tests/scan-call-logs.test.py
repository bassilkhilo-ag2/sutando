"""Unit tests for src/scan-call-logs.py.

Run: `python3 tests/scan-call-logs.test.py`
"""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "scan-call-logs.py"

sys.path.insert(0, str(ROOT / "src"))


def _load(workspace: Path):
    os.environ["SUTANDO_WORKSPACE"] = str(workspace)
    spec = importlib.util.spec_from_file_location("scan_call_logs", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestDetectDuplicateResponses(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_clean_transcript_returns_empty(self):
        transcript = "Sutando: Hello!\nCaller: Hi.\nSutando: How can I help?"
        self.assertEqual(self.mod.detect_duplicate_responses(transcript), [])

    def test_consecutive_identical_sutando_turns_flagged(self):
        # Two identical consecutive Sutando turns → flagged
        transcript = (
            "Sutando: Sure I can help you with that.\n"
            "Sutando: Sure I can help you with that.\n"
        )
        issues = self.mod.detect_duplicate_responses(transcript)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["pattern"], "duplicate_response")
        self.assertEqual(issues[0]["severity"], "medium")

    def test_triple_consecutive_shows_count(self):
        line = "Sutando: Processing your request now.\n"
        transcript = line * 3
        issues = self.mod.detect_duplicate_responses(transcript)
        self.assertEqual(len(issues), 1)
        self.assertIn("3x", issues[0]["summary"])

    def test_non_adjacent_same_response_not_flagged(self):
        # Same text at Sutando turn 0 and turn 2 (gap = 2) — should NOT flag
        transcript = (
            "Sutando: Sure I can help.\n"
            "Sutando: Let me look that up for you.\n"
            "Sutando: Sure I can help.\n"
        )
        self.assertEqual(self.mod.detect_duplicate_responses(transcript), [])

    def test_short_text_under_15_chars_not_counted(self):
        # Lines shorter than 15 chars are skipped
        transcript = "Sutando: Yes.\nSutando: Yes.\nSutando: Yes.\n"
        self.assertEqual(self.mod.detect_duplicate_responses(transcript), [])

    def test_empty_transcript_returns_empty(self):
        self.assertEqual(self.mod.detect_duplicate_responses(""), [])


class TestDetectAccessIssues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_access_denied_phrase_flagged(self):
        issues = self.mod.detect_access_issues("Sutando: I can't access that calendar.")
        self.assertEqual(len(issues), 1)
        self.assertIn("access_denied", issues[0]["pattern"])

    def test_not_authorized_flagged(self):
        issues = self.mod.detect_access_issues("Sutando: That action isn't authorized.")
        self.assertEqual(len(issues), 1)

    def test_owner_level_flagged(self):
        issues = self.mod.detect_access_issues("Sutando: That requires owner-level access.")
        self.assertEqual(len(issues), 1)

    def test_clean_transcript_returns_empty(self):
        self.assertEqual(self.mod.detect_access_issues("Sutando: Sure, here's the result."), [])


class TestDetectTaskTimeout(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_long_processing_phrase_flagged(self):
        issues = self.mod.detect_task_timeout("Sutando: Sorry this is taking so long.")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["pattern"], "task_timeout")

    def test_timeout_word_flagged(self):
        issues = self.mod.detect_task_timeout("Sutando: The request timed out.")
        self.assertEqual(len(issues), 1)

    def test_clean_response_returns_empty(self):
        self.assertEqual(self.mod.detect_task_timeout("Sutando: Done! Here's your result."), [])

    def test_only_first_match_returned(self):
        # Multiple timeout signals → still only one issue (break after first match)
        transcript = "Sutando: Timed out.\nSutando: Still taking a while."
        issues = self.mod.detect_task_timeout(transcript)
        self.assertEqual(len(issues), 1)


class TestDetectConfusion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_multiple_confusion_signals_flagged(self):
        transcript = (
            "Recipient: Hello? Are you there?\n"
            "Sutando: Yes I'm here.\n"
            "Recipient: What? I don't understand.\n"
            "Recipient: Hello?\n"
        )
        issues = self.mod.detect_confusion(transcript)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["pattern"], "caller_confusion")

    def test_single_confusion_signal_not_flagged(self):
        # Threshold is 2 — one signal should not flag
        transcript = "Recipient: Hello? Are you there?\nSutando: Yes!\n"
        self.assertEqual(self.mod.detect_confusion(transcript), [])

    def test_clean_transcript_returns_empty(self):
        transcript = "Recipient: Can you book a meeting?\nSutando: Sure, done."
        self.assertEqual(self.mod.detect_confusion(transcript), [])


class TestDetectFabrication(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_appointment_address_from_sutando_flagged(self):
        transcript = "Sutando: Your appointment is at 123 Main St."
        issues = self.mod.detect_fabrication(transcript)
        self.assertGreater(len(issues), 0)
        self.assertEqual(issues[0]["pattern"], "potential_fabrication")
        self.assertEqual(issues[0]["severity"], "high")

    def test_balance_figure_from_sutando_flagged(self):
        transcript = "Sutando: Your balance is $5,000."
        issues = self.mod.detect_fabrication(transcript)
        self.assertGreater(len(issues), 0)

    def test_caller_saying_address_not_flagged(self):
        # Fabrication only flagged when Sutando says it
        transcript = "Recipient: The address is 123 Main St.\nSutando: Got it."
        issues = self.mod.detect_fabrication(transcript)
        # Should not flag because Sutando didn't say it
        for issue in issues:
            self.assertNotIn("123 Main St", issue.get("summary", ""))

    def test_clean_conversation_returns_empty(self):
        transcript = "Sutando: I'll schedule that for you."
        self.assertEqual(self.mod.detect_fabrication(transcript), [])


class TestDetectReconnectLeak(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_im_back_from_sutando_flagged(self):
        issues = self.mod.detect_reconnect_leak("Sutando: I'm back! How can I help?")
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["pattern"], "reconnect_leak")

    def test_welcome_back_flagged(self):
        issues = self.mod.detect_reconnect_leak("Sutando: Welcome back! What can I do?")
        self.assertEqual(len(issues), 1)

    def test_caller_saying_im_back_not_flagged(self):
        issues = self.mod.detect_reconnect_leak("Recipient: I'm back from lunch.")
        self.assertEqual(len(issues), 0)

    def test_clean_greeting_not_flagged(self):
        issues = self.mod.detect_reconnect_leak("Sutando: Hello! How can I help you today?")
        self.assertEqual(len(issues), 0)

    def test_only_first_match_returned(self):
        # Two "I'm back" lines → still one issue (break after first)
        transcript = "Sutando: I'm back!\nSutando: I am back again!\n"
        self.assertEqual(len(self.mod.detect_reconnect_leak(transcript)), 1)


class TestDetectRepeatedCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_three_summon_requests_flagged(self):
        transcript = (
            "Recipient: Can you summon the screen?\n"
            "Recipient: Summon the screen please.\n"
            "Recipient: Please summon my screen.\n"
        )
        issues = self.mod.detect_repeated_command(transcript)
        patterns = [i["pattern"] for i in issues]
        self.assertIn("repeated_summon", patterns)

    def test_two_summon_requests_not_flagged(self):
        transcript = "Recipient: Summon.\nRecipient: Summon please.\n"
        issues = self.mod.detect_repeated_command(transcript)
        patterns = [i["pattern"] for i in issues]
        self.assertNotIn("repeated_summon", patterns)

    def test_three_tab_switch_requests_flagged(self):
        transcript = (
            "Recipient: Switch to the browser tab.\n"
            "Recipient: Switch tabs.\n"
            "Recipient: Open the next tab.\n"
        )
        issues = self.mod.detect_repeated_command(transcript)
        patterns = [i["pattern"] for i in issues]
        self.assertIn("repeated_tab_switch", patterns)

    def test_clean_transcript_returns_empty(self):
        self.assertEqual(self.mod.detect_repeated_command("Recipient: Book a meeting."), [])


class TestDetectIdentityConfusion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_claiming_owner_name_flagged(self):
        issues = self.mod.detect_identity_confusion("Sutando: Hi, I'm Chi, your assistant.")
        self.assertEqual(len(issues), 1)
        self.assertIn("claimed_owner_identity", issues[0]["pattern"])
        self.assertEqual(issues[0]["severity"], "high")

    def test_denying_ai_identity_flagged(self):
        issues = self.mod.detect_identity_confusion("Sutando: I am a human, not an AI.")
        self.assertEqual(len(issues), 1)
        self.assertIn("denied_ai_identity", issues[0]["pattern"])

    def test_caller_claiming_to_be_chi_not_flagged(self):
        issues = self.mod.detect_identity_confusion("Recipient: I'm Chi, can you help me?")
        self.assertEqual(len(issues), 0)

    def test_clean_identity_statement_not_flagged(self):
        issues = self.mod.detect_identity_confusion("Sutando: I'm an AI assistant ready to help.")
        self.assertEqual(len(issues), 0)


class TestDetectRecordingConfusion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_recording_complaints_flagged(self):
        transcript = (
            "Caller: You haven't started recording yet.\n"
            "Sutando: I'll start now.\n"
            "Caller: You still haven't started recording.\n"
        )
        issues = self.mod.detect_recording_confusion(transcript)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["pattern"], "recording_confusion")

    def test_single_complaint_flagged(self):
        issues = self.mod.detect_recording_confusion("Caller: Stop recording please.")
        self.assertEqual(len(issues), 1)

    def test_phone_menu_recording_not_confused(self):
        # "press 1 to stop recording" - menu option, not user confusion
        transcript = "Caller: entered any numbers or press 1 to stop recording."
        self.assertEqual(self.mod.detect_recording_confusion(transcript), [])

    def test_clean_call_returns_empty(self):
        self.assertEqual(self.mod.detect_recording_confusion("Recipient: Let's get started."), [])


class TestDetectScrollFrustration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_three_scroll_requests_flagged(self):
        transcript = (
            "Recipient: Scroll down.\n"
            "Recipient: Scroll down please.\n"
            "Recipient: I said scroll down!\n"
        )
        issues = self.mod.detect_scroll_frustration(transcript)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["pattern"], "scroll_frustration")

    def test_two_scroll_requests_not_flagged(self):
        transcript = "Recipient: Scroll down.\nRecipient: Scroll.\n"
        self.assertEqual(self.mod.detect_scroll_frustration(transcript), [])

    def test_clean_transcript_returns_empty(self):
        self.assertEqual(self.mod.detect_scroll_frustration("Recipient: Open the file."), [])


class TestDetectSttRetry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_similar_rephrasings_flagged(self):
        transcript = (
            "Caller: Please add a meeting tomorrow at three pm\n"
            "Caller: Add meeting tomorrow three pm\n"
            "Caller: Schedule meeting three pm tomorrow\n"
        )
        issues = self.mod.detect_stt_retry(transcript)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["pattern"], "stt_retry")

    def test_identical_lines_not_flagged_as_stt(self):
        # Exact same line = duplicate, not a rephrase (overlap 1.0 >= 0.9)
        transcript = "Caller: Add meeting\nCaller: Add meeting\n"
        issues = self.mod.detect_stt_retry(transcript)
        self.assertEqual(len(issues), 0)

    def test_short_caller_lines_not_enough_words(self):
        # Lines < 3 words skipped (len(prev_words) >= 3 guard)
        transcript = "Caller: Yes.\nCaller: Yes please.\n"
        self.assertEqual(self.mod.detect_stt_retry(transcript), [])

    def test_clean_conversation_returns_empty(self):
        transcript = "Caller: Book a meeting.\nSutando: Done.\n"
        self.assertEqual(self.mod.detect_stt_retry(transcript), [])


class TestDetectMetadataIssues(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_short_non_meeting_call_flagged(self):
        issues = self.mod.detect_metadata_issues({"duration_seconds": 5})
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["pattern"], "short_call")
        self.assertEqual(issues[0]["severity"], "medium")

    def test_short_meeting_call_not_flagged(self):
        issues = self.mod.detect_metadata_issues({"duration_seconds": 5, "is_meeting": True})
        self.assertEqual(len(issues), 0)

    def test_normal_duration_not_flagged(self):
        self.assertEqual(self.mod.detect_metadata_issues({"duration_seconds": 120}), [])

    def test_zero_duration_not_flagged(self):
        # Zero duration excluded (not > 0)
        self.assertEqual(self.mod.detect_metadata_issues({"duration_seconds": 0}), [])

    def test_missing_duration_not_flagged(self):
        self.assertEqual(self.mod.detect_metadata_issues({"callSid": "CA1"}), [])


class TestScanEntry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = _load(Path(self.tmp.name))

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_clean_entry_returns_none(self):
        entry = {"callSid": "CA1", "timestamp": "2024-01-15T10:00:00Z", "transcript": "Sutando: Hello!"}
        self.assertIsNone(self.mod.scan_entry(entry))

    def test_short_call_returns_result(self):
        entry = {"callSid": "CA1", "timestamp": "2024-01-15T10:00:00Z", "duration_seconds": 3, "transcript": ""}
        result = self.mod.scan_entry(entry)
        self.assertIsNotNone(result)
        self.assertEqual(result["callSid"], "CA1")
        self.assertGreater(result["issue_count"], 0)
        self.assertEqual(result["max_severity"], "medium")

    def test_high_severity_issue_sets_max_severity(self):
        entry = {
            "callSid": "CA2",
            "timestamp": "2024-01-15T10:00:00Z",
            "transcript": "Sutando: I am a human, not an AI.",
        }
        result = self.mod.scan_entry(entry)
        self.assertIsNotNone(result)
        self.assertEqual(result["max_severity"], "high")

    def test_result_has_required_fields(self):
        entry = {"callSid": "CA3", "timestamp": "2024-01-15T10:00:00Z", "duration_seconds": 3}
        result = self.mod.scan_entry(entry)
        self.assertIn("callSid", result)
        self.assertIn("timestamp", result)
        self.assertIn("issues", result)
        self.assertIn("issue_count", result)
        self.assertIn("max_severity", result)
        self.assertIn("transcript_preview", result)

    def test_short_transcript_skips_text_detectors(self):
        # Transcript < 20 chars skips text-based detectors; only metadata runs
        entry = {"callSid": "CA4", "transcript": "Hi.", "duration_seconds": 3}
        result = self.mod.scan_entry(entry)
        # Only short_call should appear (from metadata)
        patterns = [i["pattern"] for i in result["issues"]]
        self.assertIn("short_call", patterns)


class TestStateManagement(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.mod = _load(self.ws)
        # Override STATE_FILE to point to tmp workspace
        self.mod.STATE_FILE = self.ws / "results" / "calls" / ".scan-state.json"

    def tearDown(self):
        os.environ.pop("SUTANDO_WORKSPACE", None)
        self.tmp.cleanup()

    def test_load_state_missing_returns_default(self):
        state = self.mod.load_state()
        self.assertEqual(state, {"last_scanned_index": 0})

    def test_save_and_load_roundtrip(self):
        self.mod.save_state({"last_scanned_index": 42, "last_scan": "2024-01-15T10:00:00"})
        loaded = self.mod.load_state()
        self.assertEqual(loaded["last_scanned_index"], 42)
        self.assertEqual(loaded["last_scan"], "2024-01-15T10:00:00")

    def test_save_creates_parent_dirs(self):
        self.mod.save_state({"last_scanned_index": 1})
        self.assertTrue(self.mod.STATE_FILE.exists())


if __name__ == "__main__":
    unittest.main()
