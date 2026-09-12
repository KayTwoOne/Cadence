"""Run every suite. Exit code is non-zero if any of them fail."""
import subprocess, sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ["test_controllers.py", "test_macros.py", "test_ui.py"]

failed = []
for name in SUITES:
    print(f"\n{'=' * 70}\n{name}\n{'=' * 70}")
    r = subprocess.run([sys.executable, os.path.join(HERE, name)],
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if r.returncode:
        failed.append(name)

print()
if failed:
    print(f"FAILED: {', '.join(failed)}")
    sys.exit(1)
print("ALL SUITES PASSED")
