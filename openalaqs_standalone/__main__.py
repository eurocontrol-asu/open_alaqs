"""
Package entry point: `python -m openalaqs_standalone`.

Dispatches to one of the package's subcommands:

  aircraft   Compute per-movement aircraft emission totals from an
             .alaqs file (the Phase A0 core). See cli.run_aircraft.

  austal     Build the six-folder austal_prep input structure from an
             .alaqs file (stationary sources, meteo, receptors,
             config). This is the pre-existing orchestrate.orchestrate
             driver, exposed as a subcommand.

Usage:
    python -m openalaqs_standalone <command> [options]
    python -m openalaqs_standalone aircraft --help
    python -m openalaqs_standalone austal --help

The dispatch is deliberately thin: each subcommand owns its own
argparse parser (in cli.py for `aircraft`, in orchestrate.py for
`austal`), so the subcommands stay independently testable and the
entry point carries no option logic of its own.
"""

from __future__ import annotations

import sys

_USAGE = (
    "usage: python -m openalaqs_standalone <command> [options]\n"
    "\n"
    "commands:\n"
    "  aircraft   per-movement aircraft emission totals from an .alaqs\n"
    "  austal     build the six-folder austal_prep input structure\n"
    "\n"
    "run `python -m openalaqs_standalone <command> --help` for the\n"
    "options of a given command.\n"
)


def main(argv: list | None = None) -> int:
    """Dispatch to a subcommand. Returns a process exit code."""
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(_USAGE)
        return 0

    command = argv[0]
    rest = argv[1:]

    if command == "aircraft":
        from openalaqs_standalone.cli import run_aircraft

        return run_aircraft(rest)

    if command == "austal":
        # The pre-existing orchestrate driver. Its main() builds its
        # own argparse parser and returns None on success; translate
        # that to a 0 exit code.
        from openalaqs_standalone.orchestrate import main as orchestrate_main

        orchestrate_main(rest)
        return 0

    sys.stderr.write(f"error: unknown command {command!r}\n\n")
    sys.stderr.write(_USAGE)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
