# Manual Tests

This directory contains manual test scripts that verify functionality not covered by automated tests.

## Running Tests

### TUI Binary Release Test

**Purpose**: Tests the TUI binary distribution system by fetching the latest release, downloading assets, and verifying binary integrity.

**When to use**:
- After a new release is created
- Before promoting a release to production
- When troubleshooting binary distribution issues
- To verify CI workflow worked correctly

**Usage**:
```bash
cd manual_tests
python test_tui_binary_release.py
```

**What it tests**:
1. ✅ Fetch latest release from GitHub API
2. ✅ Detect and select platform-appropriate asset
3. ✅ Download binary from release URL
4. ✅ Extract binary from archive (tar.gz or zip)
5. ✅ Verify binary exists and is executable
6. ✅ Check version matches release tag
7. ✅ Calculate SHA256 checksum
8. ✅ Display binary information

**Expected output**:
```
============================================================
  TUI Binary Distribution Test Suite
============================================================

Repository: lirrensi/silc
API Endpoint: https://api.github.com/repos/lirrensi/silc/releases/latest
Python: 3.12.0
OS: linux

============================================================
  Test 1: Fetching Latest Release
============================================================
Fetching release from: https://api.github.com/repos/lirrensi/silc/releases/latest
✓ Release fetched successfully
  Tag: v0.1.0
  Name: SILC TUI v0.1.0
  Published: 2024-01-27T00:00:00Z
  Draft: false
  Pre-release: false

... [continues for all tests]

============================================================
  Test Summary
============================================================
✓ All tests passed successfully!

Binary is ready for:
  - Local testing
  - Distribution to users
  - Integration testing
```

**Exit codes**:
- `0`: All tests passed
- `1`: Test failed (error occurred)

### Daemon Tests

#### Simple Daemon Test
```bash
python test_daemon_simple.py
```
Tests basic daemon start/stop functionality.

#### Daemon Workflow Test
```bash
python test_daemon_workflow.py
```
Tests complete daemon lifecycle including session management.

### Integration Tests

#### Full Workflow Test
```bash
python test_full_workflow.py
```
Tests end-to-end workflow from daemon start to session cleanup.

#### New Process Test
```bash
python test_new_process_test.py
```
Tests process spawning and management.

### Process Tests

#### CLI Process Test
```bash
python cli_process_test.py
```
Tests command execution through CLI interface.

#### Process Script Test
```bash
python process_script_test.py
```
Tests complex command sequences.

#### Command List Test
```bash
python run_commands.py
```
Tests multiple command execution.

### Other Tests

#### Full Process Manual
```bash
python full_process_manual.py
```
Manual walkthrough of SILC functionality.

#### Manual Flow
```bash
python manual_flow.py
```
Interactive manual flow demonstration.

#### Integration Test
```bash
python integration_test.py
```
Integration test for API and CLI interaction.

## Test Dependencies

Most manual tests require the SILC daemon to be running. Before running, ensure:
1. SILC daemon is started: `silc start`
2. Dependencies are installed: `pip install -e .[test]`
3. Sufficient permissions on Unix systems

## Troubleshooting

### Network Issues
If the test fails to fetch the release:
- Check internet connectivity
- Verify GitHub API rate limits (unauthenticated requests have limits)
- Test with `curl` or `wget` directly:
  ```bash
  curl -I https://api.github.com/repos/lirrensi/silc/releases/latest
  ```

### Platform Mismatch
If no asset is found for your platform:
- Check the release contains assets for your OS/architecture
- Verify `installer._platform_keywords()` and `_architecture_keywords()` match expected patterns
- Check that asset names contain platform keywords (linux, darwin, windows, x86_64, aarch64, amd64, arm64)

### Download Issues
If download fails:
- Verify release URL is accessible
- Check file size matches expected
- Verify disk space is available
- Check network timeout settings

### Extraction Issues
If extraction fails:
- Verify archive format (tar.gz, .tar.xz, .zip)
- Check archive is not corrupted
- Verify target directory is writable

## CI Integration

While these are manual tests, you can integrate them into your CI pipeline:

```yaml
# Example GitHub Actions workflow
- name: Run TUI Binary Release Test
  run: |
    python manual_tests/test_tui_binary_release.py
```

## Test Results

- **Passing**: All tests complete without errors
- **Warning**: Tests pass but with minor issues (e.g., unusual version format)
- **Failed**: Test encountered an error

Test results are printed to stdout with clear pass/fail indicators and detailed error messages.

## Contributing

When adding new manual tests:
1. Add tests to `manual_tests/` directory
2. Include comprehensive docstrings
3. Handle exceptions gracefully
4. Provide clear exit codes
5. Add usage examples
6. Update this README

## Notes

- Manual tests are designed to be run locally or in CI
- They may require interactive input or specific environment setup
- Some tests may be slow due to network operations
- Always review test output carefully
