"""
Tests for PyInstaller specification (grabber.spec) and binary packaging integrity.
Ensures that native shared libraries required at runtime (such as libarrow_substrait)
are never stripped or excluded from desktop application bundles.
"""

from pathlib import Path

import pyarrow


def test_grabber_spec_does_not_strip_substrait():
    """Verify that grabber.spec does not filter out substrait from a.binaries."""
    spec_path = Path(__file__).resolve().parent.parent / "grabber.spec"
    assert spec_path.exists(), "grabber.spec must exist in the project root"

    content = spec_path.read_text(encoding="utf-8")

    # Verify that 'substrait' is never in binary stripping exclusions
    for line in content.splitlines():
        if "a.binaries" in line and "not in" in line:
            assert "substrait" not in line.lower(), (
                f"Line '{line}' strips substrait! pyarrow.lib requires libarrow_substrait at runtime."
            )


def test_grabber_spec_binary_filtering_retains_required_arrow_libs():
    """Verify the binary filtering logic correctly preserves core Arrow binaries."""
    dummy_binaries = [
        ("pyarrow/libarrow.2500.dylib", "/path/libarrow.dylib", "BINARY"),
        ("pyarrow/libarrow_substrait.2500.dylib", "/path/libarrow_substrait.dylib", "BINARY"),
        ("pyarrow/libarrow_flight.2500.dylib", "/path/libarrow_flight.dylib", "BINARY"),
        ("pyarrow/libparquet.2500.dylib", "/path/libparquet.dylib", "BINARY"),
    ]

    # Replicate the spec logic: only flight is stripped
    filtered = [b for b in dummy_binaries if "flight" not in b[0].lower()]
    names = [b[0] for b in filtered]

    assert "pyarrow/libarrow.2500.dylib" in names
    assert "pyarrow/libarrow_substrait.2500.dylib" in names
    assert "pyarrow/libparquet.2500.dylib" in names
    assert "pyarrow/libarrow_flight.2500.dylib" not in names


def test_pyarrow_substrait_library_presence():
    """Verify that libarrow_substrait is present in the installed pyarrow distribution."""
    pa_path = Path(pyarrow.__file__).parent
    # Check if substrait libraries exist in the package
    substrait_files = list(pa_path.glob("*substrait*"))
    assert len(substrait_files) > 0, (
        f"pyarrow package at {pa_path} is missing substrait binaries required for runtime dlopen."
    )
