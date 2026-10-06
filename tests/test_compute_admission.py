"""Actual local admission controls; no DB, subprocess backend, credentials or network.

Also runnable with unittest discovery to avoid booting the full API fixture on
the overloaded Mini. Normal CI still collects these controls through pytest.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir
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
    JobOutput,
    JobRequest,
    JobState,
    OutcomeCode,
    ReasonCode,
    WorkloadClass,
    load_policy,
)
from runtime.compute_admission.backends import AdapterUnavailable, adapter_registry
from runtime.compute_admission.capacity import CapacitySnapshot, host_capacity, linux_memory_percent
from runtime.compute_admission.ledger import LedgerUnavailable
from runtime.compute_admission.models import BackendKind, JobContext

INPUTS_DIGEST = hashlib.sha256(b"local admission controls").hexdigest()


def policy(*, slots: int = 1, budget: int = 20) -> ComputePolicy:
    raw = load_policy().model_dump()
    raw["pools"]["local"]["slots"] = slots
    raw["tenants"] = {
        tenant: {
            "owner_user_ids": ["owner", "second-owner"],
            "projects": ["project", "second"],
            "session_budget_acu": budget,
            "data_locality": "cloud-ok",
        }
        for tenant in ("tenant", "other")
    }
    raw["gates"].update(
        disk_path=gettempdir(), min_free_memory_percent=10.0, min_free_disk_bytes=100
    )
    return ComputePolicy.model_validate(raw)


def request(**changes: str) -> JobRequest:
    return JobRequest.model_validate(
        {
            "owner_user_id": "owner",
            "who_pays": "antiek_hosted",
            "tenant_id": "tenant",
            "project_id": "project",
            "lane_key": "reading/a",
            "idempotency_key": "once",
            "workload_class": "dev.test_suite",
            "inputs_digest": INPUTS_DIGEST,
            **changes,
        }
    )


class ComputeTestCase(unittest.TestCase):
    def scheduler_for(self, supplied=None, **options):
        directory = TemporaryDirectory(prefix="compute-unit-")
        self.addCleanup(directory.cleanup)
        options.setdefault("ledger_path", Path(directory.name) / "ledger.jsonl")
        options.setdefault("capacity_probe", lambda _: CapacitySnapshot(50.0, 1000, 1))
        scheduler = AdmissionScheduler(supplied if supplied is not None else policy(), **options)
        if not hasattr(self, "ledger_paths"):
            self.ledger_paths = {}
        self.ledger_paths[scheduler] = options["ledger_path"]
        self.addCleanup(scheduler.close)
        return scheduler

    def rows(self, scheduler):
        return [json.loads(line) for line in self.ledger_paths[scheduler].read_text().splitlines()]


class PolicyTests(ComputeTestCase):
    def test_shipped_policy_has_no_allocated_tenants_or_prices(self):
        shipped = load_policy()
        self.assertEqual(shipped.schema_version, "antiek.compute_policy.v1")
        self.assertEqual(shipped.tenants, {})
        self.assertTrue(
            all(route.price_usd_per_unit is None for route in shipped.backends.values())
        )
        scheduler = self.scheduler_for(shipped, enabled=True)
        self.assertEqual(scheduler.submit(request()).reason, "tenant_or_project_unallocated")

    def test_schema_rejects_malformed_policy_or_unbound_region_price(self):
        mutations = [
            ("schema_version", "antiek.compute_policy.v2"),
            ("policy_version", "1.02.0"),
            ("policy_version", "2.0.0"),
            ("surprise", True),
            (
                "tenants",
                {
                    "tenant": {
                        "owner_user_ids": ["owner"],
                        "projects": ["p", "p"],
                        "session_budget_acu": 1,
                        "data_locality": "cloud-ok",
                    }
                },
            ),
            ("leases", {"heartbeat_interval_s": 30, "stale_after_s": 30}),
            ("pools", {"local": {"slots": True}}),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                ComputePolicy.model_validate({**policy().model_dump(), field: value})
        for backend in (
            {"kind": "modal", "price_usd_per_unit": None},
            {"kind": "in_process", "region": "unknown", "price_usd_per_unit": 0},
            {"kind": "in_process", "region": "unknown"},
        ):
            with self.subTest(backend=backend), self.assertRaises(ValidationError):
                ComputePolicy.model_validate(
                    {**policy().model_dump(), "backends": {"local": backend}}
                )

    def test_schema_rejects_duplicate_owners_and_unrecognized_locality_or_region(self):
        for field, value in (("owner_user_ids", ["owner", "owner"]), ("data_locality", "anywhere")):
            raw = policy().model_dump()
            raw["tenants"]["tenant"][field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                ComputePolicy.model_validate(raw)
        raw = policy().model_dump()
        raw["backends"]["local"]["region"] = "unverified"
        with self.assertRaises(ValidationError):
            ComputePolicy.model_validate(raw)

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

    def test_workload_enum_owner_and_payer_are_required(self):
        self.assertEqual(len(WorkloadClass), 14)
        for field in ("owner_user_id", "who_pays"):
            raw = request().model_dump()
            del raw[field]
            with self.subTest(field=field), self.assertRaises(ValidationError):
                JobRequest.model_validate(raw)
        for change in ({"workload_class": "invented"}, {"who_pays": "unknown"}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                request(**change)

    def test_request_cannot_choose_job_identity_or_route(self):
        for field in ("job_id", "backend", "route_alias"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                JobRequest.model_validate({**request().model_dump(), field: "caller-choice"})
        for field in ("tenant_id", "project_id", "idempotency_key", "lane_key", "inputs_digest"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                request(**{field: ""})


class AdmissionTests(ComputeTestCase):
    def setUp(self):
        self.scheduler = self.scheduler_for(enabled=True)

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
            self.assertEqual(self.scheduler_for().submit(request()).code, OutcomeCode.ADMITTED)

    def test_unknown_class_project_and_disabled_gpu_refuse_without_leases(self):
        for change in (
            {"workload_class": "research.agent_turn"},
            {"project_id": "unknown"},
            {"tenant_id": "unknown"},
            {"workload_class": "research.batch_gpu"},
        ):
            with self.subTest(change=change):
                scheduler = self.scheduler_for(enabled=True)
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
        scheduler = self.scheduler_for(policy(slots=4), enabled=True)
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
        scheduler = self.scheduler_for(policy(slots=2, budget=1), enabled=True)
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
        scheduler = self.scheduler_for(policy(slots=2), enabled=True, clock=lambda: tick[0])
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
                scheduler = self.scheduler_for(policy(slots=2), enabled=True)
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
        scheduler = self.scheduler_for(supplied, enabled=True)
        supplied.tenants.clear()
        self.assertEqual(scheduler.submit(request()).code, OutcomeCode.ADMITTED)
        with (
            patch("runtime.compute_admission.scheduler.os.getpid", return_value=os.getpid() + 1),
            self.assertRaisesRegex(RuntimeError, "different process"),
        ):
            scheduler.submit(request(idempotency_key="fork"))

    def test_queued_route_is_rechecked_and_other_route_remains_usable(self):
        raw = policy().model_dump()
        raw["backends"]["second-local"] = {
            "kind": "in_process",
            "region": "unknown",
            "price_usd_per_unit": None,
        }
        raw["classes"]["dev.build"] = {
            **raw["classes"]["dev.test_suite"],
            "backend": "second-local",
        }
        scheduler = self.scheduler_for(ComputePolicy.model_validate(raw), enabled=True)
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
        scheduler = self.scheduler_for(ComputePolicy.model_validate(raw), enabled=True)
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
            self.scheduler.submit(
                request(idempotency_key="unknown", workload_class="research.agent_turn")
            ),
            self.scheduler_for(policy(budget=0), enabled=True).submit(request()),
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


class PlacementTests(ComputeTestCase):
    def test_non_eu_antiek_user_refusal_is_typed_and_journaled_without_execution(self):
        for region in ("us", "unknown"):
            for kind in BackendKind:
                with self.subTest(region=region, kind=kind):
                    raw = policy().model_dump()
                    raw["tenants"]["tenant"]["data_locality"] = "antiek_user"
                    raw["backends"]["local"].update(region=region, kind=kind)
                    scheduler = self.scheduler_for(
                        ComputePolicy.model_validate(raw),
                        enabled=True,
                        capacity_probe=lambda _: self.fail("residency refusal sampled host"),
                    )
                    decision = scheduler.submit(request())
                    self.assertEqual(decision.code, OutcomeCode.REFUSED_POLICY)
                    self.assertEqual(decision.reason, ReasonCode.RESIDENCY)
                    scheduler.run(decision.job.job_id, lambda _: self.fail("non-EU task ran"))
                    rows = self.rows(scheduler)
                    self.assertEqual([row["state"] for row in rows], ["requested", "refused"])
                    self.assertEqual(rows[-1]["reason"], "eu_residency_required")
                    self.assertEqual(rows[-1]["attempt"], 0)
                    self.assertEqual(rows[-1]["region"], region)
                    self.assertEqual(rows[-1]["owner_user_id"], "owner")
                    self.assertEqual(rows[-1]["tenant_id"], "tenant")
                    self.assertEqual(rows[-1]["project_id"], "project")

    def test_eu_policy_control_and_owner_allocation(self):
        raw = policy().model_dump()
        raw["tenants"]["tenant"]["data_locality"] = "antiek_user"
        raw["backends"]["local"]["region"] = "eu"
        scheduler = self.scheduler_for(ComputePolicy.model_validate(raw), enabled=True)
        accepted = scheduler.submit(request())
        self.assertEqual(scheduler.run(accepted.job.job_id, lambda _: 7).value, 7)
        denied = scheduler.submit(request(owner_user_id="outsider"))
        self.assertEqual(denied.reason, ReasonCode.OWNER_UNALLOCATED)
        self.assertNotEqual(denied.job.job_id, accepted.job.job_id)
        self.assertEqual(self.rows(scheduler)[-1]["owner_user_id"], "outsider")
        another = scheduler.submit(request(owner_user_id="second-owner"))
        self.assertEqual(another.code, OutcomeCode.ADMITTED)
        self.assertNotEqual(another.job.job_id, accepted.job.job_id)

    def test_all_reserved_adapters_refuse_without_task_or_capacity_probe(self):
        registry = adapter_registry()
        self.assertEqual(set(registry), set(BackendKind))
        for kind in (BackendKind.MODAL, BackendKind.PRIME_SANDBOXES, BackendKind.MINI_NODE):
            with self.subTest(kind=kind):
                raw = policy().model_dump()
                raw["backends"]["local"].update(kind=kind, region="eu")
                scheduler = self.scheduler_for(
                    ComputePolicy.model_validate(raw),
                    enabled=True,
                    capacity_probe=lambda _: self.fail("stub sampled host"),
                )
                decision = scheduler.submit(request())
                self.assertEqual(decision.code, OutcomeCode.ROUTE_BLOCKED)
                self.assertEqual(decision.reason, ReasonCode.STUB)
                self.assertIsNone(scheduler.inspect_lease("tenant", "project", "reading/a"))
                scheduler.run(decision.job.job_id, lambda _: self.fail("stub task ran"))
                with self.assertRaises(AdapterUnavailable):
                    registry[kind].execute(
                        lambda _: self.fail("direct stub task ran"),
                        JobContext(decision.job, lambda: False),
                    )
                self.assertEqual(self.rows(scheduler)[-1]["attempt"], 0)

    def test_mini_and_unproven_retention_refuse_cloud_route(self):
        for locality, reason in (
            ("mini-only", ReasonCode.MINI_REQUIRED),
            ("cloud-ok-no-retention", ReasonCode.RETENTION_UNPROVEN),
        ):
            with self.subTest(locality=locality):
                raw = policy().model_dump()
                raw["tenants"]["tenant"]["data_locality"] = locality
                raw["backends"]["local"].update(kind="modal", region="eu")
                scheduler = self.scheduler_for(ComputePolicy.model_validate(raw), enabled=True)
                decision = scheduler.submit(request())
                self.assertEqual(decision.reason, reason)
                scheduler.run(decision.job.job_id, lambda _: self.fail("locality refusal ran"))

    def test_bead_lane_is_exact_but_not_a_beads_claim_lease(self):
        scheduler = self.scheduler_for(enabled=True)
        decision = scheduler.submit(request(bead_id="antiek-abc.12", lane_key="antiek-abc.12"))
        self.assertEqual(decision.code, OutcomeCode.ADMITTED)
        self.assertEqual(self.rows(scheduler)[0]["bead_id"], "antiek-abc.12")
        self.assertEqual(
            scheduler.submit(
                request(
                    bead_id="antiek-abc.12", lane_key="antiek-abc.12", idempotency_key="another"
                )
            ).code,
            OutcomeCode.LEASE_HELD,
        )
        with self.assertRaises(ValidationError):
            request(bead_id="antiek-abc.12", lane_key="different")

    def test_no_network_is_needed_for_submission_execution_or_stubs(self):
        with patch.object(socket.socket, "connect", side_effect=AssertionError("network")):
            scheduler = self.scheduler_for(enabled=True)
            decision = scheduler.submit(request())
            self.assertEqual(scheduler.run(decision.job.job_id, lambda _: "local").value, "local")
            for kind in ("modal", "prime_sandboxes", "mini_node"):
                raw = policy().model_dump()
                raw["backends"]["local"].update(kind=kind, region="eu")
                reserved = self.scheduler_for(ComputePolicy.model_validate(raw), enabled=True)
                refused = reserved.submit(request())
                self.assertEqual(refused.reason, ReasonCode.STUB)
                reserved.run(refused.job.job_id, lambda _: self.fail("reserved task ran"))


class CapacityTests(ComputeTestCase):
    def test_missing_bindings_never_claim_admission(self):
        scheduler = AdmissionScheduler(policy(), enabled=True)
        self.addCleanup(scheduler.close)
        decision = scheduler.submit(request())
        self.assertEqual(decision.reason, ReasonCode.LEDGER_UNBOUND)
        scheduler.run(decision.job.job_id, lambda _: self.fail("unbound task ran"))
        for field in ("disk_path", "min_free_memory_percent", "min_free_disk_bytes"):
            raw = policy().model_dump()
            raw["gates"][field] = None
            with self.subTest(field=field):
                bound = self.scheduler_for(ComputePolicy.model_validate(raw), enabled=True)
                self.assertEqual(bound.submit(request()).reason, ReasonCode.GATES_UNBOUND)
                self.assertEqual(self.rows(bound)[-1]["state"], "refused")
        raw["gates"]["disk_path"] = "relative/path"
        with self.assertRaises(ValidationError):
            ComputePolicy.model_validate(raw)

    def test_bad_headroom_queues_without_start_or_budget_charge(self):
        for sample, reason in (
            (None, ReasonCode.CAPACITY_UNKNOWN),
            (CapacitySnapshot(float("nan"), 1000), ReasonCode.CAPACITY_UNKNOWN),
            (CapacitySnapshot(101.0, 1000), ReasonCode.CAPACITY_UNKNOWN),
            (CapacitySnapshot(50.0, -1), ReasonCode.CAPACITY_UNKNOWN),
            (CapacitySnapshot(50.0, 1000, 3), ReasonCode.CAPACITY_UNKNOWN),
            (CapacitySnapshot(9.9, 1000, 1), ReasonCode.MEMORY_LOW),
            (CapacitySnapshot(50.0, 1000, 2), ReasonCode.MEMORY_LOW),
            (CapacitySnapshot(50.0, 99, 1), ReasonCode.DISK_LOW),
        ):
            with self.subTest(sample=sample):
                current = [sample]
                scheduler = self.scheduler_for(
                    policy(budget=1),
                    enabled=True,
                    capacity_probe=lambda _, current=current: current[0],
                )
                queued = scheduler.submit(request())
                self.assertEqual(queued.code, OutcomeCode.QUEUED)
                self.assertEqual(queued.reason, reason)
                scheduler.run(queued.job.job_id, lambda _: self.fail("queued task ran"))
                self.assertEqual(
                    scheduler.inspect_lease("tenant", "project", "reading/a").job_id,
                    queued.job.job_id,
                )
                current[0] = CapacitySnapshot(10.0, 100, 1)
                ready = scheduler.advance(queued.job.job_id)
                self.assertEqual(ready.code, OutcomeCode.ADMITTED)
                self.assertEqual(ready.job, queued.job)
                scheduler.run(ready.job.job_id, lambda _: None)
                self.assertEqual(self.rows(scheduler)[-1]["attempt"], 1)

    def test_headroom_loss_before_start_releases_reservation_but_keeps_lane(self):
        current = [CapacitySnapshot(50.0, 1000, 1)]
        scheduler = self.scheduler_for(
            policy(slots=1, budget=1), enabled=True, capacity_probe=lambda _: current[0]
        )
        admitted = scheduler.submit(request())
        current[0] = CapacitySnapshot(50.0, 0, 1)
        queued = scheduler.run(admitted.job.job_id, lambda _: self.fail("headroom loss ran"))
        self.assertEqual(queued.decision.state, JobState.QUEUED)
        self.assertEqual(queued.decision.attempts, 0)
        current[0] = CapacitySnapshot(50.0, 1000, 1)
        other = scheduler.submit(request(lane_key="other", idempotency_key="other"))
        self.assertEqual(other.code, OutcomeCode.ADMITTED)
        self.assertTrue(scheduler.cancel(other.job.job_id))
        self.assertEqual(scheduler.advance(admitted.job.job_id).code, OutcomeCode.ADMITTED)
        scheduler.run(admitted.job.job_id, lambda _: None)
        self.assertEqual(
            [row["state"] for row in self.rows(scheduler) if row["job_id"] == admitted.job.job_id],
            ["requested", "admitted", "queued", "admitted", "running", "succeeded"],
        )

    def test_linux_memory_uses_available_and_rejects_malformed_samples(self):
        self.assertEqual(
            linux_memory_percent("MemTotal: 1000 kB\nMemAvailable: 250 kB\nMemFree: 1 kB"), 25.0
        )
        for text in (
            "",
            "MemTotal: 0 kB\nMemAvailable: 0 kB",
            "MemTotal: 1 kB\nMemAvailable: 2 kB",
            "MemTotal: 1 kB\nMemAvailable: 1 MB",
            "MemTotal: 1 kB\nMemTotal: 1 kB\nMemAvailable: 1 kB",
        ):
            with self.subTest(text=text), self.assertRaises((ValueError, KeyError)):
                linux_memory_percent(text)

    def test_native_probe_unknown_or_expired_sample_never_returns_capacity(self):
        with patch("runtime.compute_admission.capacity.sys.platform", "darwin"):
            for failure in (subprocess.TimeoutExpired("sysctl", 2), OSError("unavailable")):
                with (
                    self.subTest(failure=failure),
                    patch(
                        "runtime.compute_admission.capacity.subprocess.run", side_effect=failure
                    ) as utility,
                ):
                    self.assertIsNone(host_capacity(Path(gettempdir())))
                    self.assertEqual(utility.call_args.kwargs["timeout"], 2)
            with patch(
                "runtime.compute_admission.capacity.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "50 3", ""),
            ):
                self.assertIsNone(host_capacity(Path(gettempdir())))

    def test_disabled_flag_has_no_file_probe_or_execution_effect(self):
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "never-created.jsonl"
            scheduler = AdmissionScheduler(
                policy(),
                enabled=False,
                ledger_path=ledger,
                capacity_probe=lambda _: self.fail("disabled probe ran"),
            )
            self.addCleanup(scheduler.close)
            decision = scheduler.submit(request())
            self.assertEqual(decision.reason, ReasonCode.DISABLED)
            scheduler.run(decision.job.job_id, lambda _: self.fail("disabled task ran"))
            self.assertFalse(ledger.exists())


class LedgerTests(ComputeTestCase):
    def test_actual_rows_are_complete_and_idempotent_terminal_refs_are_preserved(self):
        scheduler = self.scheduler_for(enabled=True)
        decision = scheduler.submit(request())
        result_path = self.ledger_paths[scheduler].parent / "result.txt"
        trace_path = result_path.with_name("trace.txt")

        def complete(context):
            result_path.write_bytes(b"42\n")
            trace_path.write_text(f"{context.job.job_id} completed the local control\n")
            return JobOutput(
                value=42,
                trace_ref=str(trace_path),
                artifact_refs=("sha256:" + hashlib.sha256(result_path.read_bytes()).hexdigest(),),
            )

        result = scheduler.run(decision.job.job_id, complete)
        artifact = "sha256:" + hashlib.sha256(result_path.read_bytes()).hexdigest()
        rows = self.rows(scheduler)
        self.assertEqual(
            [row["state"] for row in rows], ["requested", "admitted", "running", "succeeded"]
        )
        self.assertEqual(
            [row["prev_state"] for row in rows], [None, "requested", "admitted", "running"]
        )
        self.assertEqual([row["ledger_seq"] for row in rows], [1, 2, 3, 4])
        for row in rows:
            self.assertEqual(row["schema_version"], "compute_ledger.v1")
            self.assertEqual(
                (row["owner_user_id"], row["tenant_id"], row["project_id"]),
                ("owner", "tenant", "project"),
            )
            self.assertEqual(row["who_pays"], "antiek_hosted")
            self.assertIsNone(row["estimated_cost_usd"])
            self.assertIsNone(row["actual_cost_usd"])
            self.assertEqual(row["cost_source"], "unknown")
        self.assertEqual(rows[-1]["trace_ref"], str(trace_path))
        self.assertEqual(rows[-1]["artifact_refs"], [artifact])
        self.assertEqual(scheduler.submit(request()), result.decision)
        scheduler.run(decision.job.job_id, lambda _: self.fail("journal replay ran"))
        self.assertEqual(self.rows(scheduler), rows)
        self.assertEqual(self.ledger_paths[scheduler].stat().st_mode & 0o777, 0o600)

    def test_conflict_has_own_refusal_identity_without_rewriting_original(self):
        scheduler = self.scheduler_for(enabled=True)
        original = scheduler.submit(request())
        conflict = scheduler.submit(request(inputs_digest=hashlib.sha256(b"different").hexdigest()))
        self.assertNotEqual(conflict.job.job_id, original.job.job_id)
        self.assertEqual(conflict.reason, ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(scheduler.status(original.job.job_id), original)
        rows = [row for row in self.rows(scheduler) if row["job_id"] == conflict.job.job_id]
        self.assertEqual([row["state"] for row in rows], ["requested", "refused"])
        self.assertIsNone(rows[-1]["trace_ref"])
        self.assertEqual(rows[-1]["artifact_refs"], [])

    def test_credential_billing_and_interruption_have_one_terminal_row(self):
        for error, terminal in (
            (CredentialFailure, "credential_blocked"),
            (BillingFailure, "billing_blocked"),
            (KeyboardInterrupt, "failed"),
        ):
            with self.subTest(error=error):
                scheduler = self.scheduler_for(enabled=True)
                decision = scheduler.submit(request())

                def fail(_, error=error):
                    raise error("diagnostic is not journal data")

                if error is KeyboardInterrupt:
                    with self.assertRaises(KeyboardInterrupt):
                        scheduler.run(decision.job.job_id, fail)
                else:
                    scheduler.run(decision.job.job_id, fail)
                scheduler.run(decision.job.job_id, lambda _: self.fail("terminal retried"))
                rows = self.rows(scheduler)
                self.assertEqual(rows[-1]["state"], terminal)
                self.assertEqual(len(rows), 4)
                self.assertNotIn("diagnostic is not journal data", json.dumps(rows))

    def test_journal_write_failure_prevents_first_execution_and_releases_lane(self):
        scheduler = self.scheduler_for(enabled=True)
        decision = scheduler.submit(request())
        with (
            patch("runtime.compute_admission.ledger.os.write", side_effect=OSError("disk failed")),
            self.assertRaises(LedgerUnavailable),
        ):
            scheduler.run(decision.job.job_id, lambda _: self.fail("unjournaled start"))
        self.assertEqual(scheduler.status(decision.job.job_id).attempts, 0)
        self.assertEqual(scheduler.status(decision.job.job_id).reason, ReasonCode.LEDGER_FAILED)
        self.assertIsNone(scheduler.inspect_lease("tenant", "project", "reading/a"))
        with self.assertRaises(LedgerUnavailable):
            scheduler.run(decision.job.job_id, lambda _: self.fail("failed ledger retried"))

    def test_terminal_write_failure_releases_task_and_never_reexecutes(self):
        scheduler = self.scheduler_for(enabled=True)
        decision = scheduler.submit(request())
        calls = []

        def complete(_):
            calls.append("executed")
            patcher = patch(
                "runtime.compute_admission.ledger.os.write",
                side_effect=OSError("terminal write failed"),
            )
            patcher.start()
            self.addCleanup(patcher.stop)
            return 1

        with self.assertRaises(LedgerUnavailable):
            scheduler.run(decision.job.job_id, complete)
        self.assertEqual(scheduler.status(decision.job.job_id).state, JobState.SUCCEEDED)
        self.assertIsNone(scheduler.inspect_lease("tenant", "project", "reading/a"))
        with self.assertRaises(LedgerUnavailable):
            scheduler.run(decision.job.job_id, lambda _: calls.append("reexecuted"))
        self.assertEqual(calls, ["executed"])
        self.assertEqual(self.rows(scheduler)[-1]["state"], "running")

    def test_exclusive_writer_and_nonregular_or_corrupt_files_refuse_without_start(self):
        holder = self.scheduler_for(enabled=True)
        holder.submit(request())
        contender = self.scheduler_for(enabled=True, ledger_path=self.ledger_paths[holder])
        with self.assertRaises(LedgerUnavailable):
            contender.submit(request())
        for kind in ("symlink", "fifo", "public", "truncated", "bad-transition", "identity-drift"):
            with self.subTest(kind=kind), TemporaryDirectory() as directory:
                path = Path(directory) / "ledger.jsonl"
                if kind == "symlink":
                    path.symlink_to(self.ledger_paths[holder])
                elif kind == "fifo":
                    os.mkfifo(path, 0o600)
                elif kind == "public":
                    path.touch(mode=0o644)
                elif kind == "truncated":
                    path.write_text('{"incomplete":')
                    path.chmod(0o600)
                else:
                    rows = self.rows(holder)
                    if kind == "bad-transition":
                        rows[-1]["state"] = "succeeded"
                    else:
                        rows[-1]["owner_user_id"] = "changed-owner"
                    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                    path.chmod(0o600)
                scheduler = self.scheduler_for(enabled=True, ledger_path=path)
                with self.assertRaises(LedgerUnavailable):
                    scheduler.submit(request())

    def test_restart_cannot_reexecute_a_historical_key_or_unfinished_job(self):
        for unfinished in (False, True):
            with self.subTest(unfinished=unfinished):
                predecessor = self.scheduler_for(enabled=True)
                job = predecessor.submit(request())
                if unfinished:
                    captured = self.ledger_paths[predecessor].read_bytes()
                else:
                    predecessor.run(job.job.job_id, lambda _: None)
                path = self.ledger_paths[predecessor]
                predecessor.close()
                if unfinished:
                    path.write_bytes(captured)
                before = path.read_bytes()
                successor = self.scheduler_for(enabled=True, ledger_path=path)
                with self.assertRaises(LedgerUnavailable):
                    successor.submit(request(idempotency_key="new" if unfinished else "once"))
                self.assertEqual(path.read_bytes(), before)

    def test_partial_write_is_retained_and_holds_all_further_execution(self):
        scheduler = self.scheduler_for(enabled=True)
        decision = scheduler.submit(request())
        write = os.write

        def partial(fd, payload):
            return write(fd, payload[:12])

        with (
            patch("runtime.compute_admission.ledger.os.write", side_effect=partial),
            self.assertRaises(LedgerUnavailable),
        ):
            scheduler.run(decision.job.job_id, lambda _: self.fail("partial journal start ran"))
        data = self.ledger_paths[scheduler].read_bytes()
        self.assertFalse(data.endswith(b"\n"))
        with self.assertRaises(LedgerUnavailable):
            scheduler.submit(request(idempotency_key="another"))
        self.assertEqual(self.ledger_paths[scheduler].read_bytes(), data)

    def test_append_after_clean_close_preserves_prior_bytes_and_sequence(self):
        scheduler = self.scheduler_for(enabled=True)
        decision = scheduler.submit(request())
        scheduler.run(decision.job.job_id, lambda _: None)
        path = self.ledger_paths[scheduler]
        before = path.read_bytes()
        scheduler.close()
        successor = self.scheduler_for(enabled=True, ledger_path=path)
        next_job = successor.submit(request(idempotency_key="new-intentional-work"))
        self.assertEqual(next_job.code, OutcomeCode.ADMITTED)
        self.assertTrue(path.read_bytes().startswith(before))
        self.assertEqual(self.rows(successor)[-1]["ledger_seq"], 6)


if __name__ == "__main__":
    unittest.main()
