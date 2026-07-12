"""Midnight Oil pure substrates (ask #13 — autonomous unattended research swarm).

Each module is independently bar-clean off main. The execution planner
(:mod:`execution_plan`) is the phased time+token scheduler that turns the
operator's goals+duration into a concrete executable plan, composing the cost
estimate (ceiling) and feeding the execution gate (per-phase authorization).
"""
