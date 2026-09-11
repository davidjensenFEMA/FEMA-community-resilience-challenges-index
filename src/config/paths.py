"""
Centralized path management using pathlib.

All file paths in the application should go through this module
to ensure consistency and proper path handling across platforms.
"""

from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from src.config.settings import settings


@dataclass
class PathConfig:
    """
    Centralized path management using pathlib.

    All paths are resolved relative to the project root directory.
    Directories are created automatically when accessed.
    """

    # Project root (auto-detect from this file's location)
    # This file is at: <root>/src/config/paths.py
    # So root is 3 levels up: ../../..
    root: Path = Path(__file__).parent.parent.parent.resolve()

    # =============================================================================
    # Main Directories
    # =============================================================================

    @property
    def data(self) -> Path:
        """Data directory - contains input files, reference data"""
        path = self.root / settings.data_dir
        path.mkdir(exist_ok=True, parents=True)
        return path

    @property
    def output(self) -> Path:
        """Output directory - contains generated results"""
        path = self.root / settings.output_dir
        path.mkdir(exist_ok=True, parents=True)
        return path

    @property
    def logs(self) -> Path:
        """Logs directory - contains application logs"""
        path = self.root / settings.logs_dir
        path.mkdir(exist_ok=True, parents=True)
        return path

    @property
    def src(self) -> Path:
        """Source code directory"""
        return self.root / "src"

    @property
    def tests(self) -> Path:
        """Tests directory"""
        return self.root / "tests"

    @property
    def scripts(self) -> Path:
        """Scripts directory"""
        return self.root / "scripts"

    @property
    def deprecated(self) -> Path:
        """Deprecated code directory"""
        path = self.root / "deprecated"
        path.mkdir(exist_ok=True)
        return path

    # =============================================================================
    # Data Files
    # =============================================================================

    @property
    def reference_file(self) -> Path:
        """
        CRIA reference Excel file with indicator definitions.

        Contains:
        - Status sheet: Indicator definitions
        - Years sheet: Year configuration
        """
        return self.data / "cria_data_reference.xlsx"

    @property
    def arda_file(self) -> Path:
        """
        ARDA (Association of Religion Data Archives) data file.

        2010 religion census data by county.
        """
        return self.data / (
            "U.S. Religion Census Religious Congregations "
            "and Membership Study, 2010 (County File).xlsx"
        )

    @property
    def states_regions_file(self) -> Path:
        """
        States and regions reference file.

        Maps US States to DHS (Department of Homeland Security) regions.
        Important for regional aggregation and analysis.
        """
        return self.data / "states_and_regions.xlsx"

    @property
    def counties_info_file(self) -> Path:
        """Counties information file (legacy, may not exist)"""
        # NOTE: This file may not exist - check before using
        return self.data / "info_counties.xlsx"

    @property
    def tracts_info_file(self) -> Path:
        """Tracts information file (legacy, may not exist)"""
        # NOTE: This file may not exist - check before using
        return self.data / "info_tracts.xlsx"

    # =============================================================================
    # Output Subdirectories
    # =============================================================================

    @property
    def reports(self) -> Path:
        """Reports subdirectory in output/"""
        path = self.output / "reports"
        path.mkdir(exist_ok=True, parents=True)
        return path

    # =============================================================================
    # Helper Methods
    # =============================================================================

    def get_output_file(
        self,
        filename: str,
        geography: Optional[str] = None,
        year: Optional[int] = None,
        subfolder: Optional[str] = None,
    ) -> Path:
        """
        Generate standardized output file path.

        Args:
            filename: Base filename (e.g., "indicators.xlsx")
            geography: Optional geography level to prepend
            year: Optional year to append
            subfolder: Optional subfolder in output/ directory

        Returns:
            Full path to output file

        Examples:
            >>> paths.get_output_file("results.xlsx", geography="county", year=2021)
            Path("output/county_results_2021.xlsx")

            >>> paths.get_output_file("report.xlsx", subfolder="reports")
            Path("output/reports/report.xlsx")
        """
        # Build filename parts
        parts = []

        if geography:
            parts.append(geography)

        # Get base filename without extension
        stem = Path(filename).stem
        ext = Path(filename).suffix

        parts.append(stem)

        if year:
            parts.append(str(year))

        # Reconstruct filename
        new_filename = "_".join(parts) + ext

        # Determine directory
        if subfolder:
            directory = self.output / subfolder
            directory.mkdir(exist_ok=True, parents=True)
        else:
            directory = self.output

        return directory / new_filename

    def get_data_file(self, filename: str) -> Path:
        """
        Get path to a data file.

        Args:
            filename: Filename in data directory

        Returns:
            Full path to data file
        """
        return self.data / filename

    def get_log_file(self, name: str, extension: str = ".log") -> Path:
        """
        Get path to a log file.

        Args:
            name: Log file name (without extension)
            extension: File extension (default: .log)

        Returns:
            Full path to log file
        """
        if not extension.startswith("."):
            extension = f".{extension}"

        return self.logs / f"{name}{extension}"

    def verify_paths(self) -> dict[str, bool]:
        """
        Verify that all critical paths exist.

        Returns:
            Dictionary mapping path names to existence status
        """
        return {
            "data_dir": self.data.exists(),
            "output_dir": self.output.exists(),
            "logs_dir": self.logs.exists(),
            "reference_file": self.reference_file.exists(),
            "states_regions_file": self.states_regions_file.exists(),
            "arda_file": self.arda_file.exists(),
        }

    def __repr__(self) -> str:
        """String representation showing root directory"""
        return f"PathConfig(root={self.root})"


# Create global paths instance
# This will be imported throughout the application
paths = PathConfig()


# Convenience function for debugging
def print_paths() -> None:
    """Print all configured paths (useful for debugging)"""
    print(f"Project Root: {paths.root}")
    print(f"Data: {paths.data}")
    print(f"Output: {paths.output}")
    print(f"Logs: {paths.logs}")
    print(f"Reference File: {paths.reference_file}")
    print(f"ARDA File: {paths.arda_file}")
    print("\nPath Verification:")
    for name, exists in paths.verify_paths().items():
        status = "✓" if exists else "✗"
        print(f"  {status} {name}")


if __name__ == "__main__":
    print_paths()
