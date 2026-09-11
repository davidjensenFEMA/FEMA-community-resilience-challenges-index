"""
Unit tests for PathConfig class.
"""

import pytest
from pathlib import Path
from unittest.mock import patch


class TestPathConfig:
    """Tests for PathConfig."""

    def _make_path_config(self, root):
        """Build a PathConfig rooted at the given directory."""
        from src.config.paths import PathConfig

        pc = PathConfig(root=root)
        return pc

    def test_root_resolves_to_project(self):
        """The default root should resolve to the project directory."""
        from src.config.paths import PathConfig

        pc = PathConfig()
        # The default root is computed from the file's location:
        # <root>/src/config/paths.py -> 3 levels up
        assert pc.root.is_absolute()
        assert (pc.root / "src" / "config" / "paths.py").exists()

    def test_data_creates_directory(self, tmp_path):
        """Accessing the data property should create the directory."""
        pc = self._make_path_config(tmp_path)
        data_dir = pc.data

        assert data_dir.exists()
        assert data_dir.is_dir()
        assert data_dir == tmp_path / "data"

    def test_output_creates_directory(self, tmp_path):
        """Accessing the output property should create the directory."""
        pc = self._make_path_config(tmp_path)
        output_dir = pc.output

        assert output_dir.exists()
        assert output_dir.is_dir()
        assert output_dir == tmp_path / "data" / "output"

    def test_reference_file_path(self, tmp_path):
        """reference_file should point to data/cria_data_reference.xlsx."""
        pc = self._make_path_config(tmp_path)
        ref = pc.reference_file

        assert ref.name == "cria_data_reference.xlsx"
        assert ref.parent == pc.data

    def test_get_output_file_basic(self, tmp_path):
        """get_output_file with just a filename returns output/<filename>."""
        pc = self._make_path_config(tmp_path)
        result = pc.get_output_file("results.xlsx")

        assert result.name == "results.xlsx"
        assert result.parent == pc.output

    def test_get_output_file_with_geo_year(self, tmp_path):
        """get_output_file with geography and year builds a compound name."""
        pc = self._make_path_config(tmp_path)
        result = pc.get_output_file("results.xlsx", geography="county", year=2021)

        assert result.name == "county_results_2021.xlsx"
        assert result.parent == pc.output

    def test_get_output_file_subfolder(self, tmp_path):
        """get_output_file with subfolder creates and uses that directory."""
        pc = self._make_path_config(tmp_path)
        result = pc.get_output_file("report.xlsx", subfolder="reports")

        assert result.name == "report.xlsx"
        expected_parent = pc.output / "reports"
        assert result.parent == expected_parent
        assert expected_parent.exists()

    def test_verify_paths_returns_dict(self, tmp_path):
        """verify_paths should return a dict mapping path names to booleans."""
        pc = self._make_path_config(tmp_path)
        result = pc.verify_paths()

        assert isinstance(result, dict)
        expected_keys = {
            "data_dir",
            "output_dir",
            "logs_dir",
            "reference_file",
            "states_regions_file",
            "arda_file",
        }
        assert set(result.keys()) == expected_keys

        # data_dir, output_dir, logs_dir are auto-created by the properties
        # so they should be True after verify_paths triggers the properties
        assert result["data_dir"] is True
        assert result["output_dir"] is True
        assert result["logs_dir"] is True

        # Reference files don't exist in tmp_path
        assert result["reference_file"] is False
