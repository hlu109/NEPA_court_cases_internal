"""
Main workflow to download CourtListener cases. 
"""

# TODO: handle HTTP Error: 429 Client Error: Too Many Requests for url somewhere with a reattempt
# parse error message: eg {"detail":"Request was throttled. Expected available in 275 seconds."}
# also retry request for 502 errors

import sys
import time
from pathlib import Path
from datetime import datetime
from typing import List, Optional
import pandas as pd

# Add project root to Python path to allow imports from src.utils
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.logger import get_logger
from courtlistener_utils import save_complete_dataset, get_all_results
from src.utils import config


def search_and_download(query: str,
                        max_results: Optional[int] = None,
                        result_type: str = "o",
                        courts: Optional[List[str]] = None,
                        highlight: Optional[str] = None,
                        download_opinions: bool = False):
    """ Search cases, save metadata/crosswalks, and optionally download opinion documents.

        Args:
            query: Search query
            max_results: Maximum number of results to fetch (applied per court)
            result_type: Type of search (see get_search_cases() function for options)
            courts: Optional list of court codes to filter
            highlight: Optional highlight parameter for search results
            download_opinions: Whether to download opinion files (both HTML and PDFs)

        Outputs:
            Creates directory: data/run_{timestamp}/

            Files saved in run directory:
            - cluster_metadata.csv: Cluster-level metadata
            - cluster_opinion_crosswalk.csv: Cluster→Opinion mapping with opinion types
            - cluster_docket_crosswalk.csv: Cluster→Docket mapping with docket numbers
            - opinion_metadata.csv: Individual opinion metadata
            - docket_metadata.csv: Individual docket metadata
            - complete_metadata.json: Complete JSON backup with nested structures
            - log.txt: Log file of activity and errors
            - opinions/: Directory with opinion HTML/PDFs (if download_opinions=True)
              - opinion_{id}/: Subdirectories for each opinion
                - opinion_{id}.html
                - opinion_{id}.pdf

            Returns dictionary of saved file paths.
    """
    logger = get_logger()

    logger.info("Starting API data pull")
    logger.info(f"Run directory: {config.RUN_DIR}")
    logger.info(f"Query: {query}")
    logger.info(f"Max results: {max_results}")
    if courts:
        logger.info(f"Courts: {courts}")
    logger.info(f"Download opinions: {download_opinions}")

    if courts is None:
        courts = [None]

    try:
        # Search and collect results
        logger.info("=" * 60)
        logger.info("Pulling opinion clusters from Search API...")

        results = []
        # CourtListener's court filter has some bug in the logic (e.g. OR combinations) so we loop over each court individually
        for c in courts:
            court_results = get_all_results(query=query,
                                            max_results=max_results,
                                            result_type=result_type,
                                            highlight=highlight,
                                            court=c)
            logger.info(
                f"Found {len(court_results)} opinion clusters for court: {c}.")
            results.extend(court_results)
            if len(courts) > 1:
                time.sleep(config.REQUEST_DELAY)

        logger.info(f"Found {len(results)} opinion clusters total.")

        saved_files = save_complete_dataset(
            results, download_opinions=download_opinions)

        logger.info("All saved files:")
        for file_type, path in saved_files.items():
            logger.info(f"  - {file_type}: {path}")

        return saved_files

    except Exception as e:
        logger.critical("Error in search_and_download()",
                        exception=e,
                        query=query,
                        max_results=max_results,
                        result_type=result_type,
                        download_opinions=download_opinions)
        raise


if __name__ == "__main__":
    script_start_time = datetime.now()

    try:
        config.setup_directories()
        logger = get_logger()
        logger.info("=" * 60)
        logger.info("NEPA CourtListener Data Pull")
        logger.info("=" * 60)

        saved_files = search_and_download(
            query="\"National Environmental Policy Act\"",
            result_type="o",
            highlight="on",
            courts=[
                "ca1", "ca2", "ca3", "ca4", "ca5", "ca6", "ca7", "ca8", "ca9",
                "ca10", "ca11", "cadc", "cafc", "scotus"
            ],
            max_results=None,
            download_opinions=True)

        runtime = datetime.now() - script_start_time
        logger.info(f"Total script runtime: {runtime}")
        logger.print_summary()

    except KeyboardInterrupt:
        logger = get_logger()
        logger.critical("Script interrupted by user")
        logger.print_summary()
        raise
    except Exception as e:
        logger = get_logger()
        logger.critical("Fatal error in main script", exception=e)
        logger.print_summary()
        raise
