"""Entry point of the packaged ass2ae.exe: no arguments opens the GUI, arguments run the CLI."""
import os
import sys


def run() -> int:
    if len(sys.argv) > 1:
        if sys.stderr is None:  # windowed build: keep CLI output in a log next to the exe
            log = open(os.path.join(os.path.dirname(sys.executable), "ass2ae-cli.log"), "w", encoding="utf-8")
            sys.stdout = sys.stderr = log
        else:
            # A windowed exe only has output handles when they are redirected (a pipe from
            # Git Bash, a file): write UTF-8 there rather than the ANSI code page (cp950).
            for stream in (sys.stdout, sys.stderr):
                if stream is not None and hasattr(stream, "reconfigure"):
                    stream.reconfigure(encoding="utf-8", errors="replace")
        from ass2ae.cli import main
        return main()
    from ass2ae.gui import main
    main()
    return 0


if __name__ == "__main__":
    sys.exit(run())
