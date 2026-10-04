"""The `services` package.

This file exists for two reasons, both measured rather than stylistic.

**1. mypy could not check this tree at all without it.**

    $ mypy services
    services/antiek_format/__init__.py: error: Source file found twice under different module
        names: "antiek_format" and "services.antiek_format"
    Found 1 error in 1 file (errors prevented further checking)

With `services/` a namespace package, mypy maps each child BOTH as a top-level module and as
`services.<child>`, and refuses to continue. This file makes the mapping unambiguous, and it is
what lets `services` be added to `DECLARED_MYPY_TARGETS` -- which is required, because
`tests/test_declared_bar.py::test_mypy_targets_match_wheel_packages` asserts the mypy scope
equals the wheel-package list.

**2. `services/` was missing from the wheel entirely.**

`pyproject.toml` did not list it among the package roots, so `pip wheel .` built cleanly and the
result could not import:

    PYTHONPATH=<wheel> python -c 'import interfaces.research.api.artifact_routes'
    -> ModuleNotFoundError: No module named 'services.html_projection.context'

**The other twelve roots are all regular packages.** This makes the thirteenth match them, so
the tree no longer has one root that behaves differently from the rest.
"""