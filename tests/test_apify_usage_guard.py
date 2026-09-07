import ast
import tempfile
import threading
import unittest
from pathlib import Path

from ugc_tagger.apify_usage_guard import (
    APIFY_LIMITS_URL,
    ApifyFallbackBusyError,
    ApifyGuardConfig,
    ApifyOwnerEmailConfig,
    ApifyUsageBlockedError,
    ApifyUsageSnapshot,
    ApifyUsageUnavailableError,
    _reset_apify_guard_for_tests,
    active_apify_fallback,
    apify_batch_owner,
    apify_capacity_state,
    apify_fallback_slot,
    configure_apify_guard,
    effective_stop_usd,
    effective_emergency_stop_usd,
    fetch_apify_usage,
    notify_apify_owner_if_needed,
)


def usage(used=1.0, maximum=10.0, active_jobs=0):
    return ApifyUsageSnapshot(
        monthly_usage_usd=used,
        max_monthly_usage_usd=maximum,
        cycle_start_at="2026-08-01T00:00:00.000Z",
        cycle_end_at="2026-09-01T00:00:00.000Z",
        active_actor_job_count=active_jobs,
        checked_at="2026-08-29T00:00:00+00:00",
    )


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class _SMTPClient:
    def __init__(self, calls, host, port, timeout):
        self.calls = calls
        self.calls.append(("connect", host, port, timeout))

    def starttls(self, *, context):
        self.calls.append(("starttls", bool(context)))

    def login(self, username, password):
        self.calls.append(("login", username, password))

    def send_message(self, message):
        self.calls.append(("message", message))

    def quit(self):
        self.calls.append(("quit",))


class ApifyUsageGuardTests(unittest.TestCase):
    def setUp(self):
        _reset_apify_guard_for_tests()

    def tearDown(self):
        _reset_apify_guard_for_tests()

    def test_usage_request_uses_authorization_header_without_query_token(self):
        observed = {}

        def fake_get(url, *, headers, timeout):
            observed.update(url=url, headers=headers, timeout=timeout)
            return _Response({
                "data": {
                    "monthlyUsageCycle": {
                        "startAt": "2026-08-01T00:00:00.000Z",
                        "endAt": "2026-09-01T00:00:00.000Z",
                    },
                    "limits": {"maxMonthlyUsageUsd": 5},
                    "current": {
                        "monthlyUsageUsd": 2.25,
                        "activeActorJobCount": 1,
                    },
                }
            })

        snapshot = fetch_apify_usage("secret-token", http_get=fake_get)

        self.assertEqual(observed["url"], APIFY_LIMITS_URL)
        self.assertNotIn("secret-token", observed["url"])
        self.assertEqual(observed["headers"], {"Authorization": "Bearer secret-token"})
        self.assertEqual(snapshot.monthly_usage_usd, 2.25)
        self.assertEqual(snapshot.max_monthly_usage_usd, 5.0)
        self.assertEqual(snapshot.active_actor_job_count, 1)

    def test_capacity_states_follow_beta_thresholds(self):
        config = ApifyGuardConfig(
            warning_usd=8.0,
            stop_usd=8.7,
            emergency_stop_usd=9.5,
        )
        self.assertEqual(apify_capacity_state(usage(7.99), config), "available")
        self.assertEqual(apify_capacity_state(usage(8.0), config), "warning")
        self.assertEqual(apify_capacity_state(usage(8.7), config), "restricted")
        self.assertEqual(apify_capacity_state(usage(9.5), config), "blocked")

    def test_account_hard_limit_caps_the_effective_stop(self):
        config = ApifyGuardConfig(
            warning_usd=8.0,
            stop_usd=8.7,
            emergency_stop_usd=9.5,
        )
        snapshot = usage(8.6, maximum=9.0)
        self.assertEqual(effective_stop_usd(snapshot, config), 8.7)
        self.assertEqual(effective_emergency_stop_usd(snapshot, config), 9.0)
        self.assertEqual(apify_capacity_state(usage(9.0, 9.0), config), "blocked")

    def test_warning_email_is_private_and_sent_only_once_per_cycle(self):
        calls = []
        with tempfile.TemporaryDirectory() as state_dir:
            email_config = ApifyOwnerEmailConfig(
                enabled=True,
                owner_email="owner@example.com",
                sender_email="tagger@example.com",
                smtp_host="smtp.example.com",
                smtp_username="tagger@example.com",
                smtp_password="secret-password",
                state_dir=state_dir,
            )

            def factory(host, port, timeout):
                return _SMTPClient(calls, host, port, timeout)

            first = notify_apify_owner_if_needed(
                usage(8.0),
                guard_config=ApifyGuardConfig(
                    warning_usd=8.0,
                    stop_usd=8.7,
                    emergency_stop_usd=9.5,
                ),
                email_config=email_config,
                smtp_factory=factory,
            )
            second = notify_apify_owner_if_needed(
                usage(8.5),
                guard_config=ApifyGuardConfig(
                    warning_usd=8.0,
                    stop_usd=8.7,
                    emergency_stop_usd=9.5,
                ),
                email_config=email_config,
                smtp_factory=factory,
            )

        messages = [item[1] for item in calls if item[0] == "message"]
        self.assertEqual(first, "sent")
        self.assertEqual(second, "already_sent")
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["To"], "owner@example.com")
        self.assertIn("$8.00", messages[0].get_content())
        self.assertIn(("starttls", True), calls)
        self.assertIn(
            ("login", "tagger@example.com", "secret-password"),
            calls,
        )
        self.assertNotIn("secret-password", messages[0].as_string())
        self.assertNotIn("secret-password", repr(email_config))

    def test_warning_restriction_and_emergency_emails_are_distinct(self):
        calls = []
        with tempfile.TemporaryDirectory() as state_dir:
            email_config = ApifyOwnerEmailConfig(
                enabled=True,
                owner_email="owner@example.com",
                sender_email="tagger@example.com",
                smtp_host="smtp.example.com",
                state_dir=state_dir,
            )

            def factory(host, port, timeout):
                return _SMTPClient(calls, host, port, timeout)

            warning_status = notify_apify_owner_if_needed(
                usage(8.0),
                email_config=email_config,
                smtp_factory=factory,
            )
            restricted_status = notify_apify_owner_if_needed(
                usage(8.7),
                email_config=email_config,
                smtp_factory=factory,
            )
            emergency_status = notify_apify_owner_if_needed(
                usage(9.5),
                email_config=email_config,
                smtp_factory=factory,
            )

        messages = [item[1] for item in calls if item[0] == "message"]
        self.assertEqual(
            (warning_status, restricted_status, emergency_status),
            ("sent", "sent", "sent"),
        )
        self.assertEqual(len(messages), 3)
        self.assertIn("warning", messages[0]["Subject"].lower())
        self.assertIn("restricted", messages[1]["Subject"].lower())
        self.assertIn("paused", messages[2]["Subject"].lower())
        self.assertIn("$8.00", messages[0].get_content())
        self.assertIn("$8.70", messages[1].get_content())
        self.assertIn("$9.50", messages[2].get_content())

    def test_usage_jump_sends_every_newly_reached_threshold_email(self):
        calls = []
        with tempfile.TemporaryDirectory() as state_dir:
            email_config = ApifyOwnerEmailConfig(
                enabled=True,
                owner_email="owner@example.com",
                sender_email="tagger@example.com",
                smtp_host="smtp.example.com",
                state_dir=state_dir,
            )

            def factory(host, port, timeout):
                return _SMTPClient(calls, host, port, timeout)

            status = notify_apify_owner_if_needed(
                usage(8.7),
                email_config=email_config,
                smtp_factory=factory,
            )

        messages = [item[1] for item in calls if item[0] == "message"]
        self.assertEqual(status, "sent")
        self.assertEqual(len(messages), 2)
        self.assertIn("warning", messages[0]["Subject"].lower())
        self.assertIn("restricted", messages[1]["Subject"].lower())

    def test_owner_email_is_optional_and_failure_does_not_break_guard(self):
        self.assertEqual(
            notify_apify_owner_if_needed(
                usage(8.0),
                email_config=ApifyOwnerEmailConfig(),
            ),
            "not_configured",
        )
        with tempfile.TemporaryDirectory() as state_dir:
            email_config = ApifyOwnerEmailConfig(
                enabled=True,
                owner_email="owner@example.com",
                sender_email="tagger@example.com",
                smtp_host="smtp.example.com",
                state_dir=state_dir,
            )

            def failing_factory(host, port, timeout):
                raise OSError("SMTP unavailable")

            first = notify_apify_owner_if_needed(
                usage(8.0),
                email_config=email_config,
                smtp_factory=failing_factory,
            )
            second = notify_apify_owner_if_needed(
                usage(8.0),
                email_config=email_config,
                smtp_factory=failing_factory,
            )
        self.assertEqual(first, "failed")
        self.assertEqual(second, "retry_later")

    def test_streamlit_capacity_notice_does_not_reveal_spend(self):
        root = Path(__file__).resolve().parents[1]
        module = ast.parse((root / "app.py").read_text(encoding="utf-8"))
        function = next(
            node
            for node in module.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "_render_apify_beta_safeguard_v68_97"
        )
        source = ast.get_source_segment(
            (root / "app.py").read_text(encoding="utf-8"),
            function,
        )
        self.assertNotIn("st.warning(", source)
        self.assertNotIn("st.error(", source)
        self.assertNotIn("$", source)
        self.assertNotIn("monthly_usage_usd", source)

    def test_blocked_usage_prevents_paid_call_body(self):
        body_called = False
        with self.assertRaisesRegex(ApifyUsageBlockedError, "APIFY_BETA_USAGE_LIMIT"):
            with apify_fallback_slot(
                "token",
                purpose="test actor",
                usage_provider=lambda _token: usage(9.5),
            ):
                body_called = True
        self.assertFalse(body_called)
        self.assertEqual(active_apify_fallback(), {})

    def test_admitted_batch_continues_while_second_batch_is_restricted(self):
        with apify_batch_owner("batch-a"):
            with apify_fallback_slot(
                "token",
                purpose="admit batch a",
                usage_provider=lambda _token: usage(8.6),
            ):
                pass
            with apify_fallback_slot(
                "token",
                purpose="continue batch a",
                usage_provider=lambda _token: usage(8.7),
            ):
                pass

        with apify_batch_owner("batch-b"):
            with self.assertRaisesRegex(
                ApifyUsageBlockedError,
                "APIFY_BETA_USAGE_LIMIT",
            ):
                with apify_fallback_slot(
                    "token",
                    purpose="restrict batch b",
                    usage_provider=lambda _token: usage(8.7),
                ):
                    self.fail("a second paid batch must not start")

    def test_emergency_stop_also_pauses_the_admitted_batch(self):
        with apify_batch_owner("batch-a"):
            with apify_fallback_slot(
                "token",
                purpose="admit batch a",
                usage_provider=lambda _token: usage(8.6),
            ):
                pass
            with self.assertRaisesRegex(
                ApifyUsageBlockedError,
                "emergency safety threshold",
            ):
                with apify_fallback_slot(
                    "token",
                    purpose="emergency stop batch a",
                    usage_provider=lambda _token: usage(9.5),
                ):
                    self.fail("no paid batch may start at the emergency stop")

    def test_unavailable_usage_fails_closed_by_default(self):
        def unavailable(_token):
            raise RuntimeError("network unavailable")

        with self.assertRaisesRegex(
            ApifyUsageUnavailableError,
            "APIFY_USAGE_CHECK_UNAVAILABLE",
        ):
            with apify_fallback_slot(
                "token",
                purpose="test actor",
                usage_provider=unavailable,
            ):
                self.fail("paid body must not run")

    def test_account_level_active_actor_prevents_another_paid_start(self):
        with self.assertRaisesRegex(ApifyFallbackBusyError, "APIFY_FALLBACK_BUSY"):
            with apify_fallback_slot(
                "token",
                purpose="second app instance",
                usage_provider=lambda _token: usage(1.0, active_jobs=1),
            ):
                self.fail("paid body must not run while another Actor is active")

    def test_guard_can_be_disabled_for_controlled_maintenance(self):
        configure_apify_guard(ApifyGuardConfig(enabled=False))
        provider_called = False

        def provider(_token):
            nonlocal provider_called
            provider_called = True
            return usage(5.0)

        with apify_fallback_slot(
            "token",
            purpose="maintenance",
            usage_provider=provider,
        ) as snapshot:
            self.assertIsNone(snapshot)
        self.assertFalse(provider_called)

    def test_empty_token_bypasses_guard_for_injected_test_clients(self):
        provider_called = False

        def provider(_token):
            nonlocal provider_called
            provider_called = True
            return usage(5.0)

        with apify_fallback_slot(
            "",
            purpose="injected client",
            usage_provider=provider,
        ):
            pass
        self.assertFalse(provider_called)

    def test_only_one_paid_call_owns_the_process_slot(self):
        entered = threading.Event()
        release = threading.Event()
        errors = []

        def holder():
            try:
                with apify_fallback_slot(
                    "token",
                    purpose="first beta batch",
                    usage_provider=lambda _token: usage(1.0),
                ):
                    entered.set()
                    release.wait(timeout=2)
            except Exception as exc:  # pragma: no cover - assertion captures it
                errors.append(exc)

        thread = threading.Thread(target=holder)
        thread.start()
        self.assertTrue(entered.wait(timeout=2))
        self.assertEqual(
            active_apify_fallback().get("purpose"),
            "first beta batch",
        )
        with self.assertRaisesRegex(ApifyFallbackBusyError, "APIFY_FALLBACK_BUSY"):
            with apify_fallback_slot(
                "token",
                purpose="second beta batch",
                usage_provider=lambda _token: usage(1.0),
            ):
                self.fail("second paid body must not run")
        release.set()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(active_apify_fallback(), {})

    def test_every_runtime_actor_start_is_inside_the_shared_guard(self):
        root = Path(__file__).resolve().parents[1]
        runtime_files = (
            root / "ugc_tagger" / "final_update2_backend_source.py",
            root / "ugc_tagger" / "instagram_reels_adapter.py",
            root / "ugc_tagger" / "creator_profile_enrichment.py",
        )

        class ActorCallVisitor(ast.NodeVisitor):
            def __init__(self):
                self.guard_depth = 0
                self.actor_calls = 0
                self.unguarded_lines = []

            @staticmethod
            def _is_guard(item):
                expression = item.context_expr
                return (
                    isinstance(expression, ast.Call)
                    and isinstance(expression.func, ast.Name)
                    and expression.func.id == "apify_fallback_slot"
                )

            @staticmethod
            def _is_actor_call(node):
                return (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "call"
                    and isinstance(node.func.value, ast.Call)
                    and isinstance(node.func.value.func, ast.Attribute)
                    and node.func.value.func.attr == "actor"
                )

            def visit_With(self, node):
                guarded = any(self._is_guard(item) for item in node.items)
                self.guard_depth += int(guarded)
                self.generic_visit(node)
                self.guard_depth -= int(guarded)

            def visit_Call(self, node):
                if self._is_actor_call(node):
                    self.actor_calls += 1
                    if self.guard_depth <= 0:
                        self.unguarded_lines.append(node.lineno)
                self.generic_visit(node)

        total_calls = 0
        for path in runtime_files:
            visitor = ActorCallVisitor()
            visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
            total_calls += visitor.actor_calls
            self.assertEqual(
                visitor.unguarded_lines,
                [],
                f"unguarded Actor starts in {path.name}",
            )
        self.assertGreaterEqual(total_calls, 4)


if __name__ == "__main__":
    unittest.main()
