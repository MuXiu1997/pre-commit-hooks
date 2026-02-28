import argparse
import json
import os
import subprocess
from collections.abc import Sequence
from pathlib import Path

# Mapping of lock files to their execution commands (inspired by package-manager-detector)
LOCK_FILES = {
    'pnpm-lock.yaml': ['pnpm', 'exec'],
    'yarn.lock': ['yarn', 'run'],
    'bun.lockb': ['bun', 'x'],
    'bun.lock': ['bun', 'x'],
    'package-lock.json': ['npx'],
    'npm-shrinkwrap.json': ['npx'],
}


def _check_package_manager_field(
    path: Path, local_eslint: Path, has_local: bool
) -> tuple[list[str], str | None] | None:
    """Check for packageManager field in package.json (Corepack spec)."""
    pkg_json_path = path / 'package.json'
    if pkg_json_path.exists():
        try:
            with open(pkg_json_path, encoding='utf-8') as f:
                pkg_data = json.load(f)
                pm_field = pkg_data.get('packageManager', '')

                if pm_field:
                    if pm_field.startswith('pnpm'):
                        return ([], str(local_eslint)) if has_local else (['pnpm', 'exec'], None)
                    if pm_field.startswith('yarn'):
                        return ([], str(local_eslint)) if has_local else (['yarn', 'run'], None)
                    if pm_field.startswith('bun'):
                        return (['bun'], str(local_eslint)) if has_local else (['bun', 'x'], None)
                    if pm_field.startswith('npm'):
                        return ([], str(local_eslint)) if has_local else (['npx'], None)
        except Exception:
            pass
    return None


def detect_runtime_and_eslint(start_path: Path) -> tuple[list[str], str | None]:
    """
    Detect the runtime environment and local eslint path.
    Returns: (execution command prefix, local eslint path)
    """
    current_path = start_path.absolute()
    paths_to_check = [current_path, *list(current_path.parents)]

    for path in paths_to_check:
        # Detect local eslint in node_modules
        # On Windows, it might be eslint.cmd
        local_eslint = path / 'node_modules' / '.bin' / ('eslint.cmd' if os.name == 'nt' else 'eslint')
        has_local = local_eslint.exists()

        # 1. Check for Deno (Highest priority due to unique execution style)
        if (path / 'deno.json').exists() or (path / 'deno.jsonc').exists():
            if has_local:
                # Use deno to run local eslint (bypassing node shebang)
                return ['deno', 'run', '-A'], str(local_eslint)
            # Use deno's remote npm mechanism
            return ['deno', 'run', '-A', 'npm:eslint'], None

        # 2. Check for Bun
        if (path / 'bun.lockb').exists() or (path / 'bun.lock').exists():
            # Bun can run node_modules/.bin/eslint directly with great performance
            return (['bun'], str(local_eslint)) if has_local else (['bun', 'x'], None)

        # 3. Check for packageManager field in package.json (Corepack spec)
        pm_result = _check_package_manager_field(path, local_eslint, has_local)
        if pm_result:
            return pm_result

        # 4. Check for Lockfiles
        for lock_file, pm_cmd in LOCK_FILES.items():
            if (path / lock_file).exists():
                # Direct execution is fastest if local eslint exists (depends on system node)
                return ([], str(local_eslint)) if has_local else (pm_cmd, None)

    return ([], str(local_eslint)) if has_local else (['npx'], None)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('filenames', nargs='*', help='Filenames to fix')
    args = parser.parse_args(argv)

    if not args.filenames:
        return 0

    # Detect directory of the first file
    first_file = Path(args.filenames[0])
    start_dir = first_file.parent if first_file.is_file() else first_file

    cmd_prefix, local_eslint_path = detect_runtime_and_eslint(start_dir)

    # Build final command
    # Priority 1: [runtime] [local_eslint] --fix [files]
    # Priority 2: [pkg_manager_exec] eslint --fix [files]
    if local_eslint_path:
        # Use local path directly, add prefix (e.g., bun, deno run) if exists
        cmd = [*cmd_prefix, local_eslint_path, '--fix', *args.filenames]
    elif cmd_prefix and cmd_prefix[0] == 'deno':
        # Special case for Deno (deno run -A npm:eslint --fix ...)
        cmd = [*cmd_prefix, '--fix', *args.filenames]
    else:
        # Use package manager (e.g., pnpm exec eslint --fix ...)
        cmd = [*cmd_prefix, 'eslint', '--fix', *args.filenames]

    print(f'Running: {" ".join(cmd)}')

    try:
        # Run the command and stream output to terminal
        result = subprocess.run(cmd, capture_output=False, check=False)
        return result.returncode
    except FileNotFoundError:
        cmd_name = cmd[0] if cmd else 'unknown'
        print(f"Error: Command '{cmd_name}' not found. Please ensure it is installed.")
        return 1
    except Exception as e:
        print(f'An unexpected error occurred: {e}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
