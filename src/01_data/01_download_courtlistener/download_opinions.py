"""
Download opinion HTML/PDFs for an existing CourtListener metadata run directory, from its saved CSV of opinion IDs.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to Python path
project_root = Path(__file__).parents[3]
sys.path.insert(0, str(project_root))

from src.utils.logger import Logger, set_logger
from courtlistener_utils import download_opinions_from_csv


def main(run_dir: str,
         csv_name: str = 'opinion_metadata.csv',
         opinion_id_column: str = 'opinion_id'):
    """
    Download opinions from a CSV file in an existing metadata run directory

    Locates the opinion-id CSV inside the run directory and downloads its opinions into <run_dir>/opinions/, skipping any already present there.

    Args:
        run_dir: Path to a metadata run directory (e.g., '.../CourtListener/run_20250109_120000')
        csv_name: Name of the CSV within the run directory containing the opinion IDs
        opinion_id_column: Name of column with opinion IDs (default: 'opinion_id')
    """
    script_start_time = datetime.now()

    # log into the run directory being backfilled, not a fresh timestamped one
    run_dir = Path(run_dir)
    set_logger(Logger(log_dir=run_dir))

    csv_path = run_dir / csv_name
    if not csv_path.exists():
        raise FileNotFoundError(
            f"No '{csv_name}' found in run directory: {run_dir}")

    output_dir = run_dir / "opinions"

    print(f"Run directory: {run_dir}")
    print(f"CSV file: {csv_path}")
    print(f"Opinion ID column: {opinion_id_column}")
    print(f"Output directory: {output_dir}")
    print(f"{'='*60}\n")

    download_opinions_from_csv(csv_path=csv_path,
                               output_dir=output_dir,
                               opinion_id_column=opinion_id_column,
                               existing_downloads_dir=output_dir)

    print(f"\nTotal script runtime: {datetime.now() - script_start_time}")


if __name__ == "__main__":
    # Example usage
    main(
        run_dir=str(config.RUN_DIR),  # TODO: update this
        csv_name='opinion_metadata.csv',
        opinion_id_column='opinion_id')
