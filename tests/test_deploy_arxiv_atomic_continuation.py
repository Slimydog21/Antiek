"""Contracts for preserving an interrupted arXiv oneshot across atomic deploys."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml
from jinja2 import Environment

PLAYBOOK = Path(__file__).resolve().parents[1] / "infrastructure/ansible/playbooks/deploy_atomic.yml"


def _flow() -> tuple[list[dict], list[dict]]:
    tasks = yaml.safe_load(PLAYBOOK.read_text())[1]["tasks"]
    quiesce = next(task for task in tasks if task.get("name") == "quiesce, migrate, cut over, and verify")
    return quiesce["block"], quiesce["rescue"]


def _task(tasks: list[dict], name: str) -> dict:
    return next(task for task in tasks if task.get("name") == name)


def _position(tasks: list[dict], name: str) -> int:
    return tasks.index(_task(tasks, name))


def test_candidate_pauses_timer_before_capture_and_resumes_after_public_parity() -> None:
    candidate, _ = _flow()
    assert _position(candidate, "stop the arxiv timer before observing its service") < _position(
        candidate, "remember arxiv timer policy before pause"
    ) < _position(candidate, "capture arxiv service and timer before pause"
    ) < _position(candidate, "pause the arxiv service before cutover") < _position(
        candidate, "pause every release-path consumer before cutover"
    )
    timer_stop = _task(candidate, "stop the arxiv timer before observing its service")["ansible.builtin.shell"]
    assert timer_stop.index("systemctl show") < timer_stop.index("systemctl disable --now")
    assert _position(candidate, "run blocking public parity on the candidate") < _position(
        candidate, "resume the arxiv timer after candidate verification"
    ) < _position(candidate, "resume the interrupted arxiv run on the verified candidate")
    assert _position(candidate, "resume background consumers after candidate is active") < _position(
        candidate, "GET public health from the candidate"
    )
    capture = _task(candidate, "capture arxiv service and timer before pause")["ansible.builtin.shell"]
    assert "--property=ActiveState,Job,ExecMainStartTimestampMonotonic" in capture
    assert "TimerLastTrigger=" in capture
    running = _task(candidate, "remember whether an arxiv run was interrupted")
    assert "active|activating" in running["ansible.builtin.set_fact"]["arxiv_was_running"]
    assert "PendingJobType=start" in running["ansible.builtin.set_fact"]["arxiv_was_running"]
    consumers = _task(candidate, "pause every release-path consumer before cutover")["loop"]
    assert "antiek-arxiv-oai-sync.timer" in consumers
    assert "antiek-arxiv-oai-sync.service" in consumers


@pytest.mark.parametrize("pre_state, should_resume", [
    ("activating", True), ("active", True), ("inactive", False), ("failed", False),
])
def test_candidate_restart_requires_interrupted_run_and_verified_path(
    pre_state: str, should_resume: bool,
) -> None:
    candidate, _ = _flow()
    fact = _task(candidate, "remember whether an arxiv run was interrupted")
    expression = fact["ansible.builtin.set_fact"]["arxiv_was_running"]
    jinja = Environment()
    jinja.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
    rendered = jinja.from_string(expression).render(
        arxiv_before_pause={"stdout": f"ActiveState={pre_state}\nJob=\nTimerLastTrigger=123"}
    )
    assert (rendered == "True") is should_resume
    observe = _task(candidate, "observe arxiv timer after candidate verification")
    assert "NextElapseUSecRealtime" in observe["ansible.builtin.shell"]
    conditions = observe["when"]
    for gate in (
        "arxiv_timer_pause_result is not skipped",
        "arxiv_pause_result is not skipped",
        "candidate_health is not skipped",
        "candidate_parity is not skipped",
        "arxiv_candidate_timer_resume is not skipped",
        "arxiv_timer_was_active | bool",
    ):
        assert gate in conditions
    resume = _task(candidate, "resume the interrupted arxiv run on the verified candidate")
    assert resume["ansible.builtin.systemd"]["no_block"] is True
    assert resume["ansible.builtin.systemd"]["name"] == "antiek-arxiv-oai-sync.service"
    assert "arxiv_was_running | default(false) | bool" in resume["when"]
    assert "arxiv_timer_before == (arxiv_candidate_timer.stdout | default('') | trim)" in resume["when"][-1]


def test_queued_timer_start_is_classified_as_interrupted() -> None:
    candidate, _ = _flow()
    expression = _task(candidate, "remember whether an arxiv run was interrupted")[
        "ansible.builtin.set_fact"
    ]["arxiv_was_running"]
    jinja = Environment()
    jinja.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
    assert jinja.from_string(expression).render(
        arxiv_before_pause={"stdout": "ActiveState=inactive\nJob=42\nPendingJobType=start\nTimerLastTrigger=123"}
    ) == "True"


def test_candidate_enqueue_is_bounded_and_failure_enters_rescue() -> None:
    candidate, rescue = _flow()
    observation = _task(candidate, "observe the candidate arxiv run started by timer or deploy")
    assert observation["retries"] == 12
    assert observation["delay"] == 1
    assert "MainPID=[1-9][0-9]*" in str(observation["until"])
    assert "ActiveState=activating" in str(observation["until"])
    assert "ExecMainStartTimestampMonotonic" in str(observation["until"])
    assert _position(rescue, "re-quiesce candidate consumers before rollback") < _position(
        rescue, "restore the previous release pointer"
    )
    assert _task(
        rescue, "re-quiesce arxiv service before rollback"
    )["ansible.builtin.systemd"]["name"] == "antiek-arxiv-oai-sync.service"


@pytest.mark.parametrize("pre_state", ["inactive", "failed"])
@pytest.mark.parametrize("timer_fired", [False, True])
def test_missed_timer_run_is_observed_without_manual_restart(
    pre_state: str, timer_fired: bool,
) -> None:
    candidate, rescue = _flow()
    jinja = Environment()
    jinja.tests["changed"] = lambda value: bool(value.get("changed"))
    jinja.tests["skipped"] = lambda value: bool(value.get("skipped"))
    jinja.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
    jinja.filters["bool"] = bool
    pre_state_template = _task(candidate, "remember whether an arxiv run was interrupted")[
        "ansible.builtin.set_fact"
    ]["arxiv_was_running"]
    was_running = jinja.from_string(pre_state_template).render(
        arxiv_before_pause={"stdout": f"ActiveState={pre_state}\nJob=\nTimerLastTrigger=100"}
    ) == "True"
    assert was_running is False
    for tasks, timer_name, resume_name, observation_name in (
        (candidate, "arxiv_candidate_timer", "arxiv_candidate_resume",
         "observe the candidate arxiv run started by timer or deploy"),
        (rescue, "arxiv_rollback_timer", "arxiv_rollback_resume",
         "observe the rollback arxiv run started by timer or deploy"),
    ):
        resume = _task(tasks, "resume the interrupted arxiv run on the verified candidate"
                       if tasks is candidate else
                       "resume the interrupted arxiv run on the compatible previous release")
        manual_restart_gate = jinja.compile_expression(resume["when"][0])
        assert manual_restart_gate(arxiv_was_running=was_running) is False
        observation = _task(tasks, observation_name)
        fired_gate = jinja.compile_expression(observation["when"][-1])
        values = {
            "arxiv_timer_before": "100",
            "arxiv_timer_was_active": True,
            timer_name: {"stdout": "200" if timer_fired else "100", "rc": 0},
            resume_name: {"skipped": True},
            "arxiv_candidate_timer_resume": {"skipped": False},
            "arxiv_rollback_timer_resume": {"skipped": False},
        }
        assert bool(fired_gate(**values)) is timer_fired, pre_state


def test_timer_observation_accepts_new_success_and_rejects_failed_or_stale_result() -> None:
    candidate, rescue = _flow()
    jinja = Environment()
    jinja.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
    jinja.filters["regex_findall"] = lambda value, pattern: re.findall(pattern, value)
    cases = (
        ("ActiveState=activating\nMainPID=123\nResult=success\nExecMainStartTimestampMonotonic=200", True),
        ("ActiveState=inactive\nMainPID=0\nResult=success\nExecMainStartTimestampMonotonic=200", True),
        ("ActiveState=failed\nMainPID=0\nResult=exit-code\nExecMainStartTimestampMonotonic=200", False),
        ("ActiveState=inactive\nMainPID=0\nResult=success\nExecMainStartTimestampMonotonic=100", False),
    )
    for tasks, name, status_var in (
        (candidate, "observe the candidate arxiv run started by timer or deploy", "arxiv_candidate_status"),
        (rescue, "observe the rollback arxiv run started by timer or deploy", "arxiv_rollback_status"),
    ):
        observation = _task(tasks, name)
        assert observation["retries"] == 12
        assert observation["delay"] == 1
        for stdout, expected in cases:
            context = {status_var: {"stdout": stdout}, "arxiv_service_start_before": "100"}
            assert all(bool(jinja.compile_expression(condition)(**context))
                       for condition in observation["until"]) is expected
    rollback_observation = _task(rescue, "observe the rollback arxiv run started by timer or deploy")
    assert rollback_observation["ignore_errors"] is True
    disabled = _task(rescue, "disable arxiv timer after failed rollback continuation")
    stopped = _task(rescue, "stop arxiv service after failed rollback continuation")
    assert disabled["ansible.builtin.systemd"]["enabled"] is False
    assert disabled["ansible.builtin.systemd"]["state"] == "stopped"
    assert stopped["ansible.builtin.systemd"]["name"] == "antiek-arxiv-oai-sync.service"
    assert "(arxiv_rollback_status | default({})) is failed" in disabled["when"][0]
    assert "(arxiv_rollback_status | default({})) is failed" in stopped["when"][0]


@pytest.mark.parametrize("mode, expected_rc, expected_stdout", [
    ("safe_future", 0, "100"),
    ("fired_first", 0, "200"),
    ("due_then_fired", 0, "200"),
    ("ambiguous", 1, ""),
])
def test_timer_settle_requires_changed_trigger_or_future_elapse(
    tmp_path: Path, mode: str, expected_rc: int, expected_stdout: str,
) -> None:
    candidate, rescue = _flow()
    fake_systemctl = tmp_path / "systemctl"
    fake_systemctl.write_text("""#!/bin/bash
count=$(cat "$FAKE_TIMER_COUNT" 2>/dev/null || echo 0)
count=$((count + 1))
printf '%s\\n' "$count" > "$FAKE_TIMER_COUNT"
last=100
next=due
if [ "$FAKE_TIMER_MODE" = safe_future ]; then next=future; fi
if [ "$FAKE_TIMER_MODE" = fired_first ] ||
   { [ "$FAKE_TIMER_MODE" = due_then_fired ] && [ "$count" -gt 1 ]; }; then
  last=200
fi
printf 'ActiveState=active\\nSubState=waiting\\nLastTriggerUSecMonotonic=%s\\nNextElapseUSecRealtime=%s\\n' "$last" "$next"
""")
    fake_date = tmp_path / "date"
    fake_date.write_text("""#!/bin/bash
if [ "$*" = '-u +%s' ]; then echo 1000; exit 0; fi
if [ "$*" = '-u -d future +%s' ]; then echo 1020; exit 0; fi
if [ "$*" = '-u -d due +%s' ]; then echo 1000; exit 0; fi
exit 1
""")
    fake_sleep = tmp_path / "sleep"
    fake_sleep.write_text("#!/bin/bash\nexit 0\n")
    for fake in (fake_systemctl, fake_date, fake_sleep):
        fake.chmod(0o755)
    for tasks, name in (
        (candidate, "observe arxiv timer after candidate verification"),
        (rescue, "observe arxiv timer after compatible rollback"),
    ):
        (tmp_path / "count").unlink(missing_ok=True)
        script = _task(tasks, name)["ansible.builtin.shell"]
        env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}",
               "FAKE_TIMER_COUNT": str(tmp_path / "count"), "FAKE_TIMER_MODE": mode,
               "ARXIV_TIMER_BEFORE": "100"}
        result = subprocess.run(["/bin/bash", "-c", script], env=env,
                                capture_output=True, text=True, check=False)
        assert result.returncode == expected_rc, result.stderr
        assert result.stdout.strip() == expected_stdout


def test_rescue_proves_old_parser_and_source_before_timer_or_service() -> None:
    _, rescue = _flow()
    assert _position(rescue, "verify public health after rollback") < _position(
        rescue, "prove the previous arxiv parser can read the current cursor and source"
    ) < _position(rescue, "resume the arxiv timer on a compatible previous release") < _position(
        rescue, "resume the interrupted arxiv run on the compatible previous release"
    )
    check = _task(rescue, "prove the previous arxiv parser can read the current cursor and source")
    script = check["ansible.builtin.command"]["argv"][2]
    for token in ("load_arxiv_bulk_progress", "verify_snapshot", "assert_physical_boundary",
                  "source.sha256", "source.size"):
        assert token in script
    assert check["failed_when"] is False
    timer = _task(rescue, "resume the arxiv timer on a compatible previous release")
    restart = _task(rescue, "resume the interrupted arxiv run on the compatible previous release")
    assert "NextElapseUSecRealtime" in _task(rescue, "observe arxiv timer after compatible rollback")["ansible.builtin.shell"]
    assert "arxiv_rollback_compatibility.rc | default(1) == 0" in timer["when"]
    assert "arxiv_rollback_timer.rc | default(1) == 0" in restart["when"][-1]
    ambiguous_timer = _task(rescue, "disable an ambiguous arxiv timer after rollback")
    ambiguous_service = _task(rescue, "stop an ambiguous arxiv service after rollback")
    assert ambiguous_timer["ansible.builtin.systemd"]["enabled"] is False
    assert ambiguous_timer["ansible.builtin.systemd"]["state"] == "stopped"
    assert ambiguous_service["ansible.builtin.systemd"]["name"] == "antiek-arxiv-oai-sync.service"
    assert "arxiv_rollback_timer is failed" in ambiguous_timer["when"]
    assert "arxiv_rollback_timer is failed" in ambiguous_service["when"]
    compatibility_gate = Environment().compile_expression(
        "arxiv_rollback_compatibility.rc | default(1) == 0"
    )
    assert compatibility_gate(arxiv_rollback_compatibility={"rc": 0}) is True
    assert compatibility_gate(arxiv_rollback_compatibility={"rc": 1}) is False
    assert compatibility_gate(arxiv_rollback_compatibility={"skipped": True}) is False
    assert restart["ansible.builtin.systemd"]["no_block"] is True
    assert "arxiv_timer_before == (arxiv_rollback_timer.stdout | default('') | trim)" in restart["when"][-1]
    assert "antiek-arxiv-oai-sync.timer" not in _task(rescue, "resume consumers on the previous release")["loop"]
    failure = _task(rescue, "fail the deploy after a verified rollback")["ansible.builtin.fail"]["msg"]
    assert "The arXiv timer is disabled and no automatic sync restart was" in failure
    assert "timer was disabled and service stopped" in failure
    assert "stopped and timer disabled for operator investigation" in failure


def test_rescue_disables_timer_before_cutover_rollback_work() -> None:
    _, rescue = _flow()
    disable_task = _task(rescue, "disable the arxiv timer before rollback")
    disable = disable_task["ansible.builtin.systemd"]
    assert disable == {"name": "antiek-arxiv-oai-sync.timer", "state": "stopped", "enabled": False}
    assert "arxiv_loop_timer_pause_attempted | default(false) | bool" in disable_task["when"]
    assert _position(rescue, "disable the arxiv timer before rollback") < _position(
        rescue, "re-quiesce candidate consumers before rollback"
    ) < _position(rescue, "resume the arxiv timer on a compatible previous release")
    assert _task(rescue, "resume the arxiv timer on a compatible previous release")[
        "ansible.builtin.systemd"
    ]["enabled"] == "{{ arxiv_timer_was_enabled }}"


@pytest.mark.parametrize("unit_file_state,active_state,disable_rc,expected_stop", [
    ("enabled", "active", 0, True),
    ("disabled", "inactive", 0, True),
    ("enabled", "active", 1, True),
    ("masked", "inactive", 0, False),
    ("enabled", "failed", 0, False),
])
def test_direct_start_at_timer_stop_captures_policy_before_mutation(
    tmp_path: Path, unit_file_state: str, active_state: str, disable_rc: int, expected_stop: bool,
) -> None:
    candidate, rescue = _flow()
    fake_systemctl = tmp_path / "systemctl"
    fake_systemctl.write_text("""#!/bin/bash
if [ "$1" = show ]; then
  printf 'UnitFileState=%s\\nActiveState=%s\\n' "$FAKE_UNIT_FILE_STATE" "$FAKE_ACTIVE_STATE"
elif [ "$1" = disable ]; then
  touch "$FAKE_STOP_MARKER"
  exit "$FAKE_DISABLE_RC"
else
  exit 99
fi
""")
    fake_systemctl.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "FAKE_UNIT_FILE_STATE": unit_file_state,
        "FAKE_ACTIVE_STATE": active_state,
        "FAKE_DISABLE_RC": str(disable_rc),
        "FAKE_STOP_MARKER": str(tmp_path / "timer-stopped"),
    }
    # Only the named task runs, as with --start-at-task at this mutator.
    script = _task(candidate, "stop the arxiv timer before observing its service")["ansible.builtin.shell"]
    result = subprocess.run(["/bin/bash", "-c", script], env=environment,
                            capture_output=True, text=True, check=False)
    assert (tmp_path / "timer-stopped").exists() is expected_stop
    assert (result.returncode == 0) is (expected_stop and disable_rc == 0)
    if expected_stop:
        assert result.stdout.splitlines()[:2] == [
            f"UnitFileState={unit_file_state}", f"ActiveState={active_state}"
        ]
        jinja = Environment()
        jinja.filters["bool"] = bool
        jinja.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
        pause_result = {"stdout": result.stdout, "stdout_lines": result.stdout.splitlines(), "rc": result.returncode}
        recovery = _task(rescue, "recover arxiv timer policy from attempted stop")
        assert all(jinja.compile_expression(gate)(arxiv_timer_pause_result=pause_result)
                   for gate in recovery["when"])
        restore = _task(rescue, "restore arxiv timer policy before service pause")
        assert all(jinja.compile_expression(gate)(arxiv_timer_pause_result=pause_result,
                   arxiv_service_pause_attempted=False, arxiv_timer_was_enabled=unit_file_state == "enabled",
                   arxiv_timer_was_active=active_state == "active") for gate in restore["when"])
    else:
        assert result.stdout == ""


@pytest.mark.parametrize(
    "stage,timer_enabled,timer_active,restore,disable,stop_service,check_compatibility",
    [
        ("before_timer_stop", True, True, False, False, False, False),
        ("after_timer_stop", True, True, True, False, False, False),
        ("after_timer_stop_disabled", False, False, True, False, False, False),
        ("after_service_stop", True, True, False, True, True, True),
        ("partial_consumer_pause", False, False, False, True, True, True),
    ],
)
def test_rescue_stage_keeps_an_unpaused_sync_running(
    stage: str, timer_enabled: bool, timer_active: bool,
    restore: bool, disable: bool, stop_service: bool, check_compatibility: bool,
) -> None:
    candidate, rescue = _flow()
    jinja = Environment()
    jinja.filters["bool"] = bool
    jinja.tests["skipped"] = lambda result: bool(result.get("skipped"))
    jinja.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
    context = {
        "antiek_previous_sha": "previous",
        "arxiv_timer_pause_result": ({"stdout": f"UnitFileState={'enabled' if timer_enabled else 'disabled'}\n"
                                        f"ActiveState={'active' if timer_active else 'inactive'}\n",
                                       "stdout_lines": [f"UnitFileState={'enabled' if timer_enabled else 'disabled'}",
                                                         f"ActiveState={'active' if timer_active else 'inactive'}"]}
                                       if stage != "before_timer_stop" else {}),
        "arxiv_service_pause_attempted": stage in {"after_service_stop", "partial_consumer_pause"},
        "arxiv_timer_was_enabled": timer_enabled,
        "arxiv_timer_was_active": timer_active,
        "rollback_health": {"status": 200},
    }

    def runs(task: dict) -> bool:
        conditions = task.get("when", [])
        if isinstance(conditions, str):
            conditions = [conditions]
        return all(bool(jinja.compile_expression(condition)(**context)) for condition in conditions)

    assert runs(_task(rescue, "restore arxiv timer policy before service pause")) is restore
    assert runs(_task(rescue, "disable the arxiv timer before rollback")) is disable
    assert runs(_task(rescue, "re-quiesce arxiv service before rollback")) is stop_service
    assert runs(_task(rescue, "prove the previous arxiv parser can read the current cursor and source")) is check_compatibility

    for name in ("restore arxiv timer policy before service pause",
                 "resume the arxiv timer on a compatible previous release"):
        timer = _task(rescue, name)["ansible.builtin.systemd"]
        assert jinja.from_string(timer["enabled"]).render(**context) == str(timer_enabled)
        assert jinja.from_string(timer["state"]).render(**context) == (
            "started" if timer_active else "stopped"
        )
    timer = _task(candidate, "resume the arxiv timer after candidate verification")["ansible.builtin.systemd"]
    assert jinja.from_string(timer["enabled"]).render(**context) == str(timer_enabled)
    assert jinja.from_string(timer["state"]).render(**context) == (
        "started" if timer_active else "stopped"
    )


def test_direct_start_at_service_pause_requires_completed_timer_stop(tmp_path: Path) -> None:
    candidate, rescue = _flow()
    task = _task(candidate, "pause the arxiv service before cutover")
    guard = task["environment"]["ARXIV_TIMER_STOP_OK"]
    assert Environment().from_string(guard).render() == "0"
    assert Environment().from_string(guard).render(arxiv_timer_pause_result={"rc": 1}) == "0"
    assert Environment().from_string(guard).render(arxiv_timer_pause_result={"rc": 0}) == "1"
    fake_systemctl = tmp_path / "systemctl"
    fake_systemctl.write_text("#!/bin/bash\ntouch \"$FAKE_SERVICE_STOP_MARKER\"\nexit \"$FAKE_SERVICE_STOP_RC\"\n")
    fake_systemctl.chmod(0o755)
    script = task["ansible.builtin.shell"]
    base_environment = {
        **os.environ,
        "PATH": f"{tmp_path}:{os.environ['PATH']}",
        "FAKE_SERVICE_STOP_MARKER": str(tmp_path / "service-stopped"),
    }
    classification = _task(rescue, "classify arxiv service pause stage")["ansible.builtin.set_fact"][
        "arxiv_service_pause_attempted"
    ]
    jinja = Environment()
    jinja.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
    assert jinja.from_string(classification).render() == "False"
    for completed, stop_rc in ((False, 0), (True, 0), (True, 1)):
        result = subprocess.run(["/bin/bash", "-c", script],
                                env={**base_environment, "ARXIV_TIMER_STOP_OK": str(int(completed)),
                                     "FAKE_SERVICE_STOP_RC": str(stop_rc)},
                                capture_output=True, text=True, check=False)
        assert (result.returncode == 0) is (completed and stop_rc == 0)
        assert (tmp_path / "service-stopped").exists() is completed
        assert ("ServicePauseAttempted=1" in result.stdout) is completed
        assert (jinja.from_string(classification).render(
            arxiv_service_pause_result={"stdout": result.stdout}
        ) == "True") is completed


@pytest.mark.parametrize("paused_items,service_attempted,timer_attempted", [
    ([], False, False),
    ([{"item": "antiek-arxiv-oai-sync.timer", "skipped": True},
      {"item": "antiek-arxiv-oai-sync.service", "skipped": True}], False, False),
    ([{"item": "antiek-arxiv-oai-sync.timer"}], False, True),
    ([{"item": "antiek-arxiv-oai-sync.timer"},
      {"item": "antiek-arxiv-oai-sync.service"}], True, True),
])
def test_direct_start_at_consumer_loop_is_classified_for_fail_closed_rescue(
    paused_items: list[dict], service_attempted: bool, timer_attempted: bool,
) -> None:
    _, rescue = _flow()
    facts = _task(rescue, "classify arxiv service pause stage")["ansible.builtin.set_fact"]
    jinja = Environment()
    jinja.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
    context = {"arxiv_pause_result": {"results": paused_items}}
    assert (jinja.from_string(facts["arxiv_service_pause_attempted"]).render(**context) == "True") is service_attempted
    assert (jinja.from_string(facts["arxiv_loop_timer_pause_attempted"]).render(**context) == "True") is timer_attempted


def test_direct_start_at_consumer_loop_skips_every_item_then_fails_before_cutover() -> None:
    candidate, rescue = _flow()
    loop_task = _task(candidate, "pause every release-path consumer before cutover")
    stage_assertion = _task(candidate, "require complete consumer pause before schema or cutover")
    assert _position(candidate, loop_task["name"]) < _position(candidate, stage_assertion["name"]) < _position(
        candidate, "stop antiek before schema migrate"
    )
    jinja = Environment()
    assert not all(jinja.compile_expression(gate)() for gate in loop_task["when"])
    skipped_results = {"results": [{"item": item, "skipped": True} for item in loop_task["loop"]]}
    assert not all(jinja.compile_expression(gate)(arxiv_pause_result=skipped_results)
                   for gate in stage_assertion["ansible.builtin.assert"]["that"])
    facts = _task(rescue, "classify arxiv service pause stage")["ansible.builtin.set_fact"]
    jinja.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
    assert jinja.from_string(facts["arxiv_loop_timer_pause_attempted"]).render(
        arxiv_pause_result=skipped_results
    ) == "False"
    assert jinja.from_string(facts["arxiv_service_pause_attempted"]).render(
        arxiv_pause_result=skipped_results
    ) == "False"

    completed = {
        "arxiv_timer_was_enabled": True,
        "arxiv_timer_was_active": True,
        "arxiv_timer_pause_result": {"rc": 0},
        "arxiv_service_pause_result": {"rc": 0},
        "arxiv_pause_result": {"results": [{"item": item} for item in loop_task["loop"]]},
    }
    assert all(jinja.compile_expression(gate)(**completed) for gate in loop_task["when"])
    assert all(jinja.compile_expression(gate)(**completed)
               for gate in stage_assertion["ansible.builtin.assert"]["that"])


def test_early_rescue_failure_message_does_not_claim_timer_was_disabled() -> None:
    _, rescue = _flow()
    message = _task(rescue, "fail the deploy after a verified rollback")["ansible.builtin.fail"]["msg"]
    jinja = Environment()
    jinja.filters["bool"] = bool
    jinja.tests["failed"] = lambda value: bool(value.get("failed"))
    for service_pause_attempted in (False, True):
        rendered = jinja.from_string(message).render(
            antiek_target_sha="candidate", antiek_previous_sha="previous",
            antiek_state_dir="/srv/antiek", arxiv_service_pause_attempted=service_pause_attempted,
            arxiv_rollback_compatibility={"rc": 1},
        )
        assert ("The arXiv timer is disabled" in rendered) is service_pause_attempted
        assert ("its original timer policy was retained" in rendered) is (not service_pause_attempted)


def test_inactive_timer_skips_settle_but_restarts_an_interrupted_service() -> None:
    candidate, rescue = _flow()
    jinja = Environment()
    jinja.filters["bool"] = bool
    jinja.tests["skipped"] = lambda result: bool(result.get("skipped"))
    jinja.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
    for tasks, observation, restart, resume_result in (
        (candidate, "observe arxiv timer after candidate verification",
         "resume the interrupted arxiv run on the verified candidate", "arxiv_candidate_timer_resume"),
        (rescue, "observe arxiv timer after compatible rollback",
         "resume the interrupted arxiv run on the compatible previous release", "arxiv_rollback_timer_resume"),
    ):
        settle_gate = jinja.compile_expression(_task(tasks, observation)["when"][-1])
        assert settle_gate(arxiv_timer_was_active=False) is False
        restart_gate = jinja.compile_expression(_task(tasks, restart)["when"][-1])
        assert restart_gate(arxiv_timer_was_active=False) is True
        assert restart_gate(
            arxiv_timer_was_active=True,
            arxiv_timer_before="100",
            **{resume_result.replace("timer_resume", "timer"): {"stdout": "200"}},
        ) is False


def test_rescue_failure_gates_leave_timer_disabled() -> None:
    _, rescue = _flow()
    jinja = Environment()
    jinja.tests["failed"] = lambda result: bool(result.get("failed"))
    for name, result_name in (
        ("disable an ambiguous arxiv timer after rollback", "arxiv_rollback_timer"),
        ("disable arxiv timer after failed rollback continuation", "arxiv_rollback_status"),
    ):
        task = _task(rescue, name)
        assert task["ansible.builtin.systemd"]["enabled"] is False
        fail_gate = jinja.compile_expression(task["when"][-1])
        assert fail_gate(**{result_name: {"failed": True}}) is True
        assert fail_gate(**{result_name: {"failed": False}}) is False
    compatible_timer = _task(rescue, "resume the arxiv timer on a compatible previous release")
    compatible_gate = jinja.compile_expression(compatible_timer["when"][-1])
    assert compatible_gate(arxiv_rollback_compatibility={"rc": 1}) is False
    assert compatible_gate(arxiv_rollback_compatibility={"rc": 0}) is True


def test_tagged_runs_cannot_resume_without_matching_pause_and_verification() -> None:
    candidate, rescue = _flow()
    for name in ("stop the arxiv timer before observing its service",
                 "capture arxiv service and timer before pause",
                 "pause every release-path consumer before cutover",
                 "resume the arxiv timer after candidate verification",
                 "observe arxiv timer after candidate verification",
                 "resume the interrupted arxiv run on the verified candidate"):
        assert "code" in _task(candidate, name)["tags"]
    for name in ("run blocking public parity on the candidate", "GET public health from the candidate"):
        assert "verify" in _task(candidate, name)["tags"]
    for name in ("prove the previous arxiv parser can read the current cursor and source",
                 "resume the arxiv timer on a compatible previous release",
                 "resume the interrupted arxiv run on the compatible previous release"):
        assert "rollback" in _task(rescue, name)["tags"]
    compatibility = _task(rescue, "prove the previous arxiv parser can read the current cursor and source")
    assert "arxiv_service_pause_attempted | default(false) | bool" in compatibility["when"]
    assert "rollback_health is not skipped" in compatibility["when"]
    assert "arxiv_rollback_compatibility.rc | default(1) == 0" in _task(
        rescue, "observe arxiv timer after compatible rollback"
    )["when"]


def test_no_backup_service_auto_restart() -> None:
    candidate, rescue = _flow()
    for tasks in (candidate, rescue):
        for task in tasks:
            systemd = task.get("ansible.builtin.systemd", {})
            if systemd.get("state") == "started":
                assert systemd.get("name") != "antiek-backup.service"
                assert "antiek-backup.service" not in task.get("loop", [])


def test_systemd_run_keeps_the_existing_whole_run_lock() -> None:
    root = PLAYBOOK.parents[3]
    service = (root / "infrastructure/ansible/templates/antiek-arxiv-oai-sync.service.j2").read_text()
    sync = (root / "tools/arxiv_oai_sync.py").read_text()
    lock = (root / "tools/arxiv_bulk_resume.py").read_text()
    assert "-m tools.arxiv_oai_sync incremental --bulk" in service
    assert "--reset-state" not in service
    assert "with whole_run_lock(resolved_db):" in sync
    assert "fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)" in lock


@pytest.mark.parametrize("mode,expected_rc,expected_type", [
    ("start", 0, "start"), ("stop", 0, "stop"),
    ("none", 0, "none"), ("active", 0, "none"),
    ("activating", 0, "none"), ("failed", 0, "none"),
    ("missing-job", 1, None), ("missing-state", 1, None),
    ("missing-time", 1, None), ("duplicate-job", 1, None),
    ("invalid-job", 1, None), ("zero-job", 1, None),
    ("invalid-state", 1, None), ("invalid-time", 1, None), ("vanished", 1, None), ("replaced", 1, None),
    ("recaptured", 0, "start"), ("churn", 1, None),
])
def test_capture_real_numeric_job_and_verified_type(tmp_path: Path, mode: str,
                                                  expected_rc: int, expected_type: str | None) -> None:
    candidate, _ = _flow()
    fake = tmp_path / "systemctl"
    fake.write_text("""#!/bin/bash
if [ "$1" = list-jobs ]; then
  case "$MODE" in
    start|stop) echo "42 antiek-arxiv-oai-sync.service $MODE waiting" ;;
    replaced|recaptured|churn) echo '43 antiek-arxiv-oai-sync.service start waiting' ;;
  esac
elif [ "$2" = antiek-arxiv-oai-sync.timer ]; then
  echo 123
else
  [[ " $* " == *" --all "* ]] || exit 99
  job=42
  state=inactive
  stamp=9
  case "$MODE" in
    none|active|activating|failed|missing-job|missing-state|missing-time|duplicate-job|invalid-state|invalid-time) job= ;;
    invalid-job) job=garbage ;;
    zero-job) job=0 ;;
  esac
  case "$MODE" in active|activating|failed) state=$MODE ;; invalid-state) state=garbage ;; esac
  [ "$MODE" = invalid-time ] && stamp=garbage
  if [ "$MODE" = recaptured ] || [ "$MODE" = churn ]; then
    count=0
    [ -f "$COUNT_FILE" ] && count=$(cat "$COUNT_FILE")
    count=$((count + 1))
    echo "$count" > "$COUNT_FILE"
    [ "$count" -gt 1 ] && job=43
    if [ "$MODE" = churn ] && [ $((count % 2)) = 1 ]; then job=42; fi
  fi
  [ "$MODE" != missing-time ] && printf 'ExecMainStartTimestampMonotonic=%s\\n' "$stamp"
  [ "$MODE" != missing-state ] && printf 'ActiveState=%s\\n' "$state"
  [ "$MODE" != missing-job ] && printf 'Job=%s\\n' "$job"
  [ "$MODE" = duplicate-job ] && echo 'Job='
  exit 0
fi
""")
    fake.chmod(0o755)
    sleep = tmp_path / "sleep"
    sleep.write_text("#!/bin/bash\nexit 0\n")
    sleep.chmod(0o755)
    result = subprocess.run(["/bin/bash", "-c", _task(candidate,
        "capture arxiv service and timer before pause")["ansible.builtin.shell"]],
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "MODE": mode, "COUNT_FILE": str(tmp_path / "count")},
        capture_output=True, text=True, check=False)
    assert result.returncode == expected_rc
    assert not (tmp_path / "service-stopped").exists()
    if expected_type is not None:
        assert f"PendingJobType={expected_type}" in result.stdout
        jinja = Environment()
        jinja.tests["search"] = lambda value, pattern: re.search(pattern, value) is not None
        expression = _task(candidate, "remember whether an arxiv run was interrupted")[
            "ansible.builtin.set_fact"]["arxiv_was_running"]
        assert (jinja.from_string(expression).render(
            arxiv_before_pause={"stdout": result.stdout}) == "True") is (mode in {"start", "recaptured", "active", "activating"})


@pytest.mark.parametrize("failed_result", ["arxiv_rollback_resume", "arxiv_rollback_timer_resume"])
@pytest.mark.parametrize("disable_rc", [0, 1])
def test_failed_rollback_enqueue_disables_restored_timer_and_stops_service(
    tmp_path: Path, failed_result: str, disable_rc: int,
) -> None:
    _, rescue = _flow()
    fake = tmp_path / "systemctl"
    fake.write_text("""#!/bin/bash
if [ "$1" = start ]; then exit 1; fi
if [ "$1" = disable ]; then
  [ "$DISABLE_RC" = 0 ] && rm -f "$STATE/timer-enabled" "$STATE/timer-active"
  exit "$DISABLE_RC"
fi
if [ "$1" = stop ]; then rm -f "$STATE/service-active"; fi
""")
    fake.chmod(0o755)
    for name in ("timer-enabled", "timer-active", "service-active"):
        (tmp_path / name).touch()
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "STATE": str(tmp_path), "DISABLE_RC": str(disable_rc)}
    enqueue = _task(rescue, "resume the interrupted arxiv run on the compatible previous release")
    result = subprocess.run([str(fake), "start", "antiek-arxiv-oai-sync.service"], env=env, check=False)
    assert result.returncode == 1
    # Ansible must retain failed admission and continue to the cleanup tasks.
    assert enqueue.get("ignore_errors") is True
    facts = {"arxiv_rollback_resume": {"failed": failed_result == "arxiv_rollback_resume"},
             "arxiv_rollback_timer_resume": {"failed": failed_result == "arxiv_rollback_timer_resume"},
             "arxiv_rollback_status": {"skipped": True}}
    jinja = Environment()
    jinja.tests["failed"] = lambda value: bool(value.get("failed"))
    for name in ("disable arxiv timer after failed rollback continuation",
                 "stop arxiv service after failed rollback continuation"):
        task = _task(rescue, name)
        assert all(jinja.compile_expression(condition)(**facts) for condition in task["when"])
        unit = task["ansible.builtin.systemd"]
        if unit.get("enabled") is False:
            cleanup = subprocess.run([str(fake), "disable", "--now", unit["name"]], env=env, check=False)
            assert cleanup.returncode == disable_rc
            assert task.get("ignore_errors") is True
        else:
            subprocess.run([str(fake), "stop", unit["name"]], env=env, check=True)
    assert not (tmp_path / "service-active").exists()
    assert (tmp_path / "timer-enabled").exists() is bool(disable_rc)
    assert (tmp_path / "timer-active").exists() is bool(disable_rc)
    failure = _task(rescue, "fail the deploy after a verified rollback")["ansible.builtin.fail"]["msg"]
    assert "enqueue" in failure and "operator" in failure


def test_rescue_pause_classification_never_raises_on_unskipped_items() -> None:
    """The rescue block's pause-stage classification crashed a live deploy
    (run 36819650883, 2026-10-01): `rejectattr('skipped', 'equalto', true)`
    raises under Ansible's strict undefined when a loop item that RAN carries
    no `skipped` key. The classification must use an idiom that cannot raise
    on missing attributes — map(attribute=..., default=...) + select."""
    _, rescue = _flow()
    classify = _task(rescue, "classify arxiv service pause stage")
    facts = classify["ansible.builtin.set_fact"]
    for fact_name in ("arxiv_service_pause_attempted", "arxiv_loop_timer_pause_attempted"):
        expr = facts[fact_name]
        assert "rejectattr('skipped'" not in expr, (
            f"{fact_name} uses rejectattr on 'skipped', which raises under "
            "strict undefined for items that ran (no 'skipped' key)"
        )
        assert "map(attribute='skipped', default=false)" in expr, fact_name


def test_rescue_pause_classification_evaluates_correctly_for_all_item_shapes() -> None:
    """Evaluate the playbook's own expression shape against synthetic result
    lists: an item that ran (no 'skipped' key), a skipped item, an unrelated
    unit, an empty result set, and a skipped-service-plus-ran-timer mix."""
    env = Environment()
    env.tests["equalto"] = lambda a, b: a == b
    template = (
        "{{ (results | default([])) "
        "| selectattr('item', 'equalto', 'antiek-arxiv-oai-sync.service') "
        "| map(attribute='skipped', default=false) | select('equalto', false) "
        "| list | length > 0 }}"
    )
    svc = "antiek-arxiv-oai-sync.service"
    cases = [
        (True, [{"item": svc, "changed": True}]),
        (True, [{"item": svc, "changed": False}]),
        (False, [{"item": svc, "skipped": True}]),
        (False, [{"item": "antiek-arxiv-oai-sync.timer", "changed": True}]),
        (False, []),
        (False, [{"item": svc, "skipped": True},
                 {"item": "antiek-arxiv-oai-sync.timer", "changed": False}]),
        (False, None),  # arxiv_pause_result absent → .results | default([])
    ]
    for expected, results in cases:
        ctx = {} if results is None else {"results": results}
        assert env.from_string(template).render(**ctx) == str(expected), (
            f"expected {expected} for {results}"
        )
