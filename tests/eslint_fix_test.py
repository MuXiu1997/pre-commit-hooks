import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pre_commit_hooks.eslint_fix import detect_runtime_and_eslint, main


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Fixture to provide a temporary project directory."""
    return tmp_path


def test_detect_pnpm_with_local_eslint(temp_project: Path) -> None:
    """Test detection when pnpm-lock.yaml and local eslint exist."""
    (temp_project / 'pnpm-lock.yaml').touch()
    bin_dir = temp_project / 'node_modules' / '.bin'
    bin_dir.mkdir(parents=True)
    eslint_path = bin_dir / ('eslint.cmd' if os.name == 'nt' else 'eslint')
    eslint_path.touch()

    cmd_prefix, local_path = detect_runtime_and_eslint(temp_project)

    # Should return empty prefix and direct path to local eslint
    assert cmd_prefix == []
    assert local_path == str(eslint_path)


def test_detect_bun_with_local_eslint(temp_project: Path) -> None:
    """Test detection when bun.lockb and local eslint exist (Bun runtime should be used)."""
    (temp_project / 'bun.lockb').touch()
    bin_dir = temp_project / 'node_modules' / '.bin'
    bin_dir.mkdir(parents=True)
    eslint_path = bin_dir / ('eslint.cmd' if os.name == 'nt' else 'eslint')
    eslint_path.touch()

    cmd_prefix, local_path = detect_runtime_and_eslint(temp_project)

    # Should use 'bun' as runtime to execute local eslint
    assert cmd_prefix == ['bun']
    assert local_path == str(eslint_path)


def test_detect_deno_with_local_eslint(temp_project: Path) -> None:
    """Test detection when deno.json and local eslint exist (Deno runtime should be used)."""
    (temp_project / 'deno.json').touch()
    bin_dir = temp_project / 'node_modules' / '.bin'
    bin_dir.mkdir(parents=True)
    eslint_path = bin_dir / ('eslint.cmd' if os.name == 'nt' else 'eslint')
    eslint_path.touch()

    cmd_prefix, local_path = detect_runtime_and_eslint(temp_project)

    # Should use 'deno run -A' as runtime to execute local eslint
    assert cmd_prefix == ['deno', 'run', '-A']
    assert local_path == str(eslint_path)


def test_detect_deno_remote(temp_project: Path) -> None:
    """Test detection when deno.json exists but no local node_modules."""
    (temp_project / 'deno.json').touch()

    cmd_prefix, local_path = detect_runtime_and_eslint(temp_project)

    # Should use deno's remote npm mechanism
    assert cmd_prefix == ['deno', 'run', '-A', 'npm:eslint']
    assert local_path is None


def test_detect_package_manager_field(temp_project: Path) -> None:
    """Test detection using the packageManager field in package.json."""
    pkg_json = temp_project / 'package.json'
    with open(pkg_json, 'w') as f:
        json.dump({'packageManager': 'pnpm@9.0.0'}, f)

    cmd_prefix, local_path = detect_runtime_and_eslint(temp_project)

    assert cmd_prefix == ['pnpm', 'exec']
    assert local_path is None


def test_recursive_lookup(temp_project: Path) -> None:
    """Test that it can find the root package manager from a sub-directory."""
    (temp_project / 'yarn.lock').touch()
    sub_dir = temp_project / 'packages' / 'app'
    sub_dir.mkdir(parents=True)

    cmd_prefix, local_path = detect_runtime_and_eslint(sub_dir)

    # Should find yarn.lock in the parent directory
    assert cmd_prefix == ['yarn', 'run']
    assert local_path is None


@patch('subprocess.run')
def test_main_execution_pnpm(mock_run: MagicMock, temp_project: Path) -> None:
    """Test the full main function execution flow for a pnpm project."""
    mock_run.return_value = MagicMock(returncode=0)

    # Setup a mock pnpm project
    (temp_project / 'pnpm-lock.yaml').touch()
    test_file = temp_project / 'src' / 'index.js'
    test_file.parent.mkdir(parents=True)
    test_file.touch()

    # Run main with the test file
    exit_code = main([str(test_file)])

    assert exit_code == 0
    # Verify the generated command
    expected_cmd = ['pnpm', 'exec', 'eslint', '--fix', str(test_file)]
    mock_run.assert_called_once_with(expected_cmd, capture_output=False, check=False)


@patch('subprocess.run')
def test_main_execution_local_bun(mock_run: MagicMock, temp_project: Path) -> None:
    """Test the full main function execution flow for a Bun project with local eslint."""
    mock_run.return_value = MagicMock(returncode=0)

    # Setup a mock Bun project with local eslint
    (temp_project / 'bun.lockb').touch()
    bin_dir = temp_project / 'node_modules' / '.bin'
    bin_dir.mkdir(parents=True)
    eslint_path = bin_dir / ('eslint.cmd' if os.name == 'nt' else 'eslint')
    eslint_path.touch()

    test_file = temp_project / 'index.ts'
    test_file.touch()

    exit_code = main([str(test_file)])

    assert exit_code == 0
    # Verify the generated command uses bun to run the local eslint path
    expected_cmd = ['bun', str(eslint_path), '--fix', str(test_file)]
    mock_run.assert_called_once_with(expected_cmd, capture_output=False, check=False)


def test_main_no_files() -> None:
    """Test that main returns 0 immediately if no files are provided."""
    assert main([]) == 0


@patch('subprocess.run')
def test_main_error_handling(mock_run: MagicMock, temp_project: Path) -> None:
    """Test that main returns the exit code of the subprocess if it fails."""
    mock_run.return_value = MagicMock(returncode=1)

    test_file = temp_project / 'error.js'
    test_file.touch()

    exit_code = main([str(test_file)])
    assert exit_code == 1
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs['capture_output'] is False
    assert mock_run.call_args.kwargs['check'] is False
