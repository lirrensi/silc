# Quick Start: TUI Binary Release Test

## Quick Reference

### Run the test after a release:
```bash
python manual_tests/test_tui_binary_release.py
```

### What it checks:
1. ✅ Fetches latest release from GitHub
2. ✅ Selects correct platform asset
3. ✅ Downloads the binary
4. ✅ Extracts and verifies it's executable
5. ✅ Checks version matches release tag
6. ✅ Calculates SHA256 checksum
7. ✅ Displays binary information

### Expected output:
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
✓ Release fetched successfully
  Tag: v0.1.0
  Name: SILC TUI v0.1.0
  Published: 2024-01-27T00:00:00Z
  Draft: false
  Pre-release: false

... [7 tests total]

============================================================
  Test Summary
============================================================
✓ All tests passed successfully!
```

### Exit codes:
- `0` = All tests passed
- `1` = Test failed

### Troubleshooting:

**No asset found for platform**:
- Check that release includes assets for your OS/architecture
- Verify asset names contain platform keywords (linux, darwin, windows, x86_64, etc.)

**Download fails**:
- Check internet connectivity
- Verify release URL is accessible
- Check disk space

**Extraction fails**:
- Verify archive format (tar.gz or zip)
- Check archive is not corrupted

See `manual_tests/README.md` for detailed documentation.
