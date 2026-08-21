"""The demo is a fixture, not a decoration: its numbers are pinned."""

from fleet_ops.demo import NO_PROBE, TRUNCATED, UNHEALTHY, UNREACHABLE, run_demo


def test_the_scenario_produces_the_documented_counts():
    report, nodes = run_demo()
    assert report.rolled_back == 2
    assert report.untouched == 6
    assert report.halted_at == "pilot"


def test_each_planted_failure_produces_its_own_code():
    report, _ = run_demo()
    codes = {o.node_id: o.code for o in report.outcomes}
    assert codes[UNREACHABLE] == "transport-failure"
    assert codes[TRUNCATED] == "digest-mismatch"
    assert codes[UNHEALTHY] == "health-probe-failed"
    assert codes[NO_PROBE] == "health-probe-failed"


def test_every_node_that_failed_is_still_running_the_old_version():
    report, nodes = run_demo()
    for outcome in report.outcomes:
        if not outcome.ok:
            assert nodes[outcome.node_id].running_version == "2.3.0"


def test_the_halt_leaves_the_last_wave_entirely_alone():
    report, nodes = run_demo()
    attempted = {o.node_id for o in report.outcomes}
    last_wave = report.plan.waves[-1]
    assert not (set(last_wave.node_ids) & attempted)
    assert all(nodes[n].running_version == "2.3.0" for n in last_wave.node_ids)
