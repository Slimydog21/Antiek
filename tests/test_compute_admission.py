"""Actual local admission controls; no DB, subprocess backend, credentials or network.

Also runnable with unittest discovery to avoid booting the full API fixture on
the overloaded Mini. Normal CI still collects these controls through pytest.
"""

from __future__ import annotations

import hashlib
import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID

import yaml
from pydantic import ValidationError

from runtime.compute_admission import (
    ENABLE_ENV,
    AdmissionScheduler,
    BillingFailure,
    ComputePolicy,
    CredentialFailure,
    JobRequest,
    JobState,
    OutcomeCode,
    load_policy,
)

INPUTS_DIGEST = hashlib.sha256(b"local admission controls").hexdigest()


def policy(*, slots: int = 1, budget: int = 20) -> ComputePolicy:
    raw = load_policy().model_dump()
    raw["pools"]["local"]["slots"] = slots
    raw["tenants"] = {
        tenant: {"projects": ["project", "second"], "session_budget_acu": budget}
        for tenant in ("tenant", "other")
    }
    return ComputePolicy.model_validate(raw)


def request(**changes: str) -> JobRequest:
    return JobRequest.model_validate(
        {
            "tenant_id": "tenant",
            "project_id": "project",
            "lane_key": "reading/a",
            "idempotency_key": "once",
            "workload_class": "dev.test_suite",
            "inputs_digest": INPUTS_DIGEST,
            **changes,
        }
    )


class PolicyTests(unittest.TestCase):
    def test_shipped_policy_has_no_allocated_tenants_or_prices(self):
        shipped = load_policy()
        self.assertEqual(shipped.schema_version, "antiek.compute_policy.v1")
        self.assertEqual(shipped.tenants, {})
        self.assertTrue(
            all(route.price_usd_per_unit is None for route in shipped.backends.values())
        )
        scheduler = AdmissionScheduler(shipped, enabled=True)
        self.assertEqual(scheduler.submit(request()).reason, "tenant_or_project_unallocated")

    def test_schema_rejects_unpriced_remote_or_malformed_policy(self):
        mutations = [
            ("schema_version", "antiek.compute_policy.v2"),
            ("policy_version", "1.02.0"),
            ("policy_version", "2.0.0"),
            ("surprise", True),
            ("tenants", {"tenant": {"projects": ["p", "p"], "session_budget_acu": 1}}),
            ("leases", {"heartbeat_interval_s": 30, "stale_after_s": 30}),
            ("pools", {"local": {"slots": True}}),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                ComputePolicy.model_validate({**policy().model_dump(), field: value})
        for backend in (
            {"kind": "modal", "price_usd_per_unit": None},
            {"kind": "in_process", "price_usd_per_unit": 0},
        ):
            with self.subTest(backend=backend), self.assertRaises(ValidationError):
                ComputePolicy.model_validate(
                    {**policy().model_dump(), "backends": {"local": backend}}
                )

    def test_policy_rejects_unknown_route_and_impossible_slot_cost(self):
        for field, value in (("backend", "missing"), ("pool", "missing"), ("slot_cost", 2)):
            raw = policy().model_dump()
            raw["classes"]["dev.test_suite"][field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                ComputePolicy.model_validate(raw)

    def test_yaml_duplicate_keys_and_unsafe_tags_are_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "policy.yaml"
            for text in (
                "schema_version: antiek.compute_policy.v1\nschema_version: ignored\n",
                "pools:\n  local:\n    slots: 1\n    slots: 20\n",
                "!!python/object/apply:os.system ['false']\n",
            ):
                path.write_text(text)
                with self.subTest(text=text), self.assertRaises(yaml.YAMLError):
                    load_policy(path)

    def test_request_cannot_choose_job_identity_or_route(self):
        for field in ("job_id", "backend", "route_alias"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                JobRequest.model_validate({**request().model_dump(), field: "caller-choice"})
        for field in ("tenant_id", "project_id", "idempotency_key", "lane_key", "inputs_digest"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                request(**{field: ""})


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.scheduler = AdmissionScheduler(policy(), enabled=True)

    def test_flag_defaults_off_and_refusal_never_runs(self):
        with patch.dict(os.environ, {}, clear=True):
            scheduler = AdmissionScheduler(policy())
        decision = scheduler.submit(request())
        self.assertEqual(decision.code, OutcomeCode.REFUSED_POLICY)
        self.assertEqual(decision.reason, "compute_layer_disabled")
        report = scheduler.run(decision.job.job_id, lambda _: self.fail("disabled task ran"))
        self.assertEqual(report.decision.attempts, 0)
        self.assertIsNone(scheduler.inspect_lease("tenant", "project", "reading/a"))
        for value in ("0", "false", "typo"):
            with self.subTest(value=value), patch.dict(os.environ, {ENABLE_ENV: value}):
                self.assertEqual(AdmissionScheduler(policy()).submit(request()).code, decision.code)
        with patch.dict(os.environ, {ENABLE_ENV: "1"}):
            self.assertEqual(
                AdmissionScheduler(policy()).submit(request()).code, OutcomeCode.ADMITTED
            )

    def test_unknown_class_project_and_disabled_gpu_refuse_without_leases(self):
        for change in (
            {"workload_class": "missing"},
            {"project_id": "unknown"},
            {"tenant_id": "unknown"},
            {"workload_class": "research.batch_gpu"},
        ):
            with self.subTest(change=change):
                scheduler = AdmissionScheduler(policy(), enabled=True)
                decision = scheduler.submit(request(**change))
                self.assertEqual(decision.code, OutcomeCode.REFUSED_POLICY)
                scheduler.run(decision.job.job_id, lambda _: self.fail("refused task ran"))

    def test_scheduler_mints_identity_and_replays_without_second_execution(self):
        first = self.scheduler.submit(request())
        self.assertEqual(UUID(first.job.job_id).version, 4)
        self.assertEqual(first, self.scheduler.submit(request()))
        calls = []
        report = self.scheduler.run(
            first.job.job_id, lambda ctx: calls.append(ctx.job.job_id) or 42
        )
        self.assertEqual(report.value, 42)
        self.assertEqual(report.decision.state, JobState.SUCCEEDED)
        replay = self.scheduler.submit(request())
        self.assertEqual(replay, report.decision)
        second = self.scheduler.run(first.job.job_id, lambda _: self.fail("retried started job"))
        self.assertEqual(second.value, 42)
        self.assertEqual(calls, [first.job.job_id])
        self.assertEqual(second.decision.attempts, 1)
        self.assertIsNone(self.scheduler.inspect_lease("tenant", "project", "reading/a"))

    def test_conflicting_idempotency_key_does_not_mutate_original(self):
        first = self.scheduler.submit(request())
        for change in (
            {"lane_key": "different"},
            {"workload_class": "research.batch_gpu"},
            {"inputs_digest": hashlib.sha256(b"changed inputs").hexdigest()},
        ):
            with self.subTest(change=change):
                refused = self.scheduler.submit(request(**change))
                self.assertEqual(refused.code, OutcomeCode.REFUSED_POLICY)
                self.assertEqual(refused.reason, "idempotency_conflict")
                self.assertEqual(self.scheduler.status(first.job.job_id), first)

    def test_lane_is_owned_across_keys_and_queue_preserves_identity(self):
        first = self.scheduler.submit(request())
        denied = self.scheduler.submit(request(idempotency_key="duplicate"))
        self.assertEqual(denied.code, OutcomeCode.LEASE_HELD)
        queued = self.scheduler.submit(request(lane_key="another", idempotency_key="next"))
        self.assertEqual(queued.code, OutcomeCode.QUEUED)
        self.assertEqual(self.scheduler.advance(queued.job.job_id), queued)
        self.scheduler.run(queued.job.job_id, lambda _: self.fail("queued task ran"))
        self.scheduler.run(first.job.job_id, lambda _: None)
        admitted = self.scheduler.advance(queued.job.job_id)
        self.assertEqual(admitted.code, OutcomeCode.ADMITTED)
        self.assertEqual(admitted.job, queued.job)
        # A refused submission stays refused even after the first holder completes.
        self.assertEqual(self.scheduler.submit(request(idempotency_key="duplicate")), denied)

    def test_namespace_uses_tuples_without_filename_collisions(self):
        scheduler = AdmissionScheduler(policy(slots=4), enabled=True)
        submissions = [
            request(),
            request(lane_key="reading_a", idempotency_key="second-lane"),
            request(project_id="second"),
            request(tenant_id="other"),
        ]
        decisions = [scheduler.submit(item) for item in submissions]
        self.assertTrue(all(item.code == OutcomeCode.ADMITTED for item in decisions))
        self.assertEqual(len({item.job.job_id for item in decisions}), 4)

    def test_budget_reserves_admission_charges_start_and_refunds_only_unstarted(self):
        scheduler = AdmissionScheduler(policy(slots=2, budget=1), enabled=True)
        first = scheduler.submit(request())
        blocked = scheduler.submit(request(lane_key="second", idempotency_key="blocked"))
        self.assertEqual(blocked.code, OutcomeCode.BUDGET_BLOCKED)
        self.assertIsNone(scheduler.inspect_lease("tenant", "project", "second"))
        self.assertTrue(scheduler.cancel(first.job.job_id))
        replacement = scheduler.submit(request(idempotency_key="replacement"))
        self.assertEqual(replacement.code, OutcomeCode.ADMITTED)
        scheduler.run(replacement.job.job_id, lambda _: None)
        self.assertFalse(scheduler.cancel(replacement.job.job_id))
        exhausted = scheduler.submit(request(idempotency_key="after-start"))
        self.assertEqual(exhausted.code, OutcomeCode.BUDGET_BLOCKED)

    def test_queued_cancel_releases_lane_without_freeing_somebody_elses_slot(self):
        first = self.scheduler.submit(request())
        queued = self.scheduler.submit(request(lane_key="queued", idempotency_key="queued"))
        self.assertTrue(self.scheduler.cancel(queued.job.job_id))
        replacement = self.scheduler.submit(
            request(lane_key="queued", idempotency_key="replacement")
        )
        self.assertEqual(replacement.code, OutcomeCode.QUEUED)
        self.scheduler.run(first.job.job_id, lambda _: None)
        self.assertEqual(self.scheduler.advance(replacement.job.job_id).code, OutcomeCode.ADMITTED)

    def test_concurrent_submissions_acquire_exactly_one_lane(self):
        barrier = threading.Barrier(2, timeout=10)

        def submit(key):
            barrier.wait()
            return self.scheduler.submit(request(idempotency_key=key))

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(submit, key) for key in ("left", "right")]
            results = [future.result(timeout=15) for future in futures]
        self.assertEqual(
            {result.code for result in results}, {OutcomeCode.ADMITTED, OutcomeCode.LEASE_HELD}
        )

    def test_concurrent_run_and_stale_live_holder_never_start_second_attempt(self):
        tick = [0.0]
        scheduler = AdmissionScheduler(policy(slots=2), enabled=True, clock=lambda: tick[0])
        first = scheduler.submit(request())
        started, release = threading.Event(), threading.Event()

        def task(context):
            self.assertTrue(context.heartbeat())
            started.set()
            self.assertTrue(release.wait(15))
            return "local completion"

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(scheduler.run, first.job.job_id, task)
            try:
                self.assertTrue(started.wait(10))
                tick[0] = 30.0
                lease = scheduler.inspect_lease("tenant", "project", "reading/a")
                self.assertTrue(lease.stale)
                self.assertTrue(lease.holder_alive)
                self.assertEqual(lease.holder_pid, os.getpid())
                self.assertIsNotNone(lease.holder_thread_id)
                self.assertEqual(
                    scheduler.run(
                        first.job.job_id, lambda _: self.fail("second start")
                    ).decision.state,
                    JobState.RUNNING,
                )
                self.assertFalse(scheduler.cancel(first.job.job_id))
                self.assertEqual(
                    scheduler.submit(request(idempotency_key="new")).code, OutcomeCode.LEASE_HELD
                )
                self.assertTrue(scheduler.heartbeat(first.job.job_id))
                self.assertFalse(scheduler.inspect_lease("tenant", "project", "reading/a").stale)
            finally:
                release.set()
            self.assertEqual(future.result(timeout=15).value, "local completion")
        self.assertFalse(scheduler.heartbeat(first.job.job_id))

    def test_credential_and_billing_block_route_even_for_already_admitted_jobs(self):
        for error, state in (
            (CredentialFailure, JobState.CREDENTIAL_BLOCKED),
            (BillingFailure, JobState.BILLING_BLOCKED),
        ):
            with self.subTest(error=error):
                scheduler = AdmissionScheduler(policy(slots=2), enabled=True)
                first = scheduler.submit(request())
                second = scheduler.submit(request(lane_key="second", idempotency_key="second"))

                def fail(_, exception=error):
                    raise exception("private diagnostic must not appear in receipt")

                failed = scheduler.run(first.job.job_id, fail).decision
                self.assertEqual(failed.state, state)
                self.assertEqual(failed.code, OutcomeCode.ROUTE_BLOCKED)
                self.assertEqual(failed.attempts, 1)
                self.assertNotIn("private diagnostic", repr(failed))
                scheduler.run(first.job.job_id, lambda _: self.fail("retry"))
                denied = scheduler.run(
                    second.job.job_id, lambda _: self.fail("blocked route ran")
                ).decision
                self.assertEqual(denied.code, OutcomeCode.ROUTE_BLOCKED)
                self.assertEqual(denied.attempts, 0)
                fresh = scheduler.submit(request(project_id="second", idempotency_key="fresh"))
                self.assertEqual(fresh.code, OutcomeCode.ROUTE_BLOCKED)
                other_tenant = scheduler.submit(request(tenant_id="other"))
                self.assertEqual(other_tenant.code, OutcomeCode.ADMITTED)

    def test_task_failure_is_terminal_but_does_not_block_route(self):
        first = self.scheduler.submit(request())

        def fail(_):
            raise ValueError("task error")

        failed = self.scheduler.run(first.job.job_id, fail)
        self.assertEqual(failed.decision.state, JobState.FAILED)
        self.scheduler.run(first.job.job_id, lambda _: self.fail("retry"))
        replacement = self.scheduler.submit(request(idempotency_key="replacement"))
        self.assertEqual(replacement.code, OutcomeCode.ADMITTED)

    def test_interruption_releases_lease_and_never_retries(self):
        first = self.scheduler.submit(request())

        def interrupt(_):
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.scheduler.run(first.job.job_id, interrupt)
        self.assertEqual(self.scheduler.status(first.job.job_id).state, JobState.FAILED)
        self.assertIsNone(self.scheduler.inspect_lease("tenant", "project", "reading/a"))
        self.scheduler.run(first.job.job_id, lambda _: self.fail("interrupted task retried"))

    def test_policy_is_snapshotted_and_fork_copy_refuses(self):
        supplied = policy()
        scheduler = AdmissionScheduler(supplied, enabled=True)
        supplied.tenants.clear()
        self.assertEqual(scheduler.submit(request()).code, OutcomeCode.ADMITTED)
        with (
            patch("runtime.compute_admission.scheduler.os.getpid", return_value=os.getpid() + 1),
            self.assertRaisesRegex(RuntimeError, "different process"),
        ):
            scheduler.submit(request(idempotency_key="fork"))

    def test_queued_route_is_rechecked_and_other_route_remains_usable(self):
        raw = policy().model_dump()
        raw["backends"]["second-local"] = {"kind": "in_process", "price_usd_per_unit": None}
        raw["classes"]["dev.build"] = {
            **raw["classes"]["dev.test_suite"],
            "backend": "second-local",
        }
        scheduler = AdmissionScheduler(ComputePolicy.model_validate(raw), enabled=True)
        first = scheduler.submit(request())
        queued = scheduler.submit(request(lane_key="next", idempotency_key="next"))
        self.assertEqual(queued.code, OutcomeCode.QUEUED)

        def deny(_):
            raise BillingFailure

        scheduler.run(first.job.job_id, deny)
        self.assertEqual(scheduler.advance(queued.job.job_id).code, OutcomeCode.ROUTE_BLOCKED)
        scheduler.run(queued.job.job_id, lambda _: self.fail("blocked queued task ran"))
        other = scheduler.submit(request(idempotency_key="build", workload_class="dev.build"))
        self.assertEqual(other.code, OutcomeCode.ADMITTED)
        self.assertEqual(
            scheduler.run(other.job.job_id, lambda _: "build control").value, "build control"
        )

    def test_old_heartbeat_cannot_touch_new_holder_on_same_lane(self):
        first = self.scheduler.submit(request())
        self.scheduler.run(first.job.job_id, lambda _: None)
        second = self.scheduler.submit(request(idempotency_key="second"))
        self.assertFalse(self.scheduler.heartbeat(first.job.job_id))
        lease = self.scheduler.inspect_lease("tenant", "project", "reading/a")
        self.assertEqual(lease.job_id, second.job.job_id)
        self.assertTrue(self.scheduler.heartbeat(second.job.job_id))

    def test_weighted_slots_and_budget_are_shared_across_projects(self):
        raw = policy(slots=3, budget=3).model_dump()
        raw["classes"]["dev.test_suite"].update(slot_cost=2, acu_units=2)
        scheduler = AdmissionScheduler(ComputePolicy.model_validate(raw), enabled=True)
        first = scheduler.submit(request())
        blocked = scheduler.submit(request(project_id="second"))
        self.assertEqual(blocked.code, OutcomeCode.BUDGET_BLOCKED)
        other = scheduler.submit(request(tenant_id="other"))
        self.assertEqual(other.code, OutcomeCode.QUEUED)
        scheduler.run(first.job.job_id, lambda _: None)
        self.assertEqual(scheduler.advance(other.job.job_id).code, OutcomeCode.ADMITTED)

    def test_all_six_outcomes_are_stable_and_not_retry_instructions(self):
        first = self.scheduler.submit(request())
        results = [
            first,
            self.scheduler.submit(request(idempotency_key="same-lane")),
            self.scheduler.submit(request(lane_key="queued", idempotency_key="queued")),
            self.scheduler.submit(request(idempotency_key="unknown", workload_class="unknown")),
            AdmissionScheduler(policy(budget=0), enabled=True).submit(request()),
        ]

        def deny(_):
            raise CredentialFailure

        results.append(self.scheduler.run(first.job.job_id, deny).decision)
        self.assertEqual(
            {result.code.value for result in results},
            {
                "admitted",
                "queued",
                "refused_policy",
                "lease_held",
                "route_blocked",
                "budget_blocked",
            },
        )
        self.assertTrue(all(result.retryable is False for result in results))


if __name__ == "__main__":
    unittest.main()
