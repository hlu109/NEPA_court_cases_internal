"""
CourtListener Data Utilities 
"""

import sys
import warnings
import json
import csv
import time
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import requests

from src.utils.api_utils import _make_request
from src.utils.config import RUN_DIR, BASE_PDF_URL, CURR_OPINIONS_DIR, TIMEOUT, API_KEY, REQUEST_DELAY
from src.utils.logger import get_logger

# TODO: double check pdf paths


def get_search_cases(query: str,
                     result_type: str = 'o',
                     api_key: str = API_KEY,
                     highlight: Optional[str] = None,
                     court: Optional[str] = None) -> Dict:
    """ Make request to Search API for court cases. 

        Args:
            query: Search query text
            result_type: Type of search. Options:
                * "o": Case law opinion clusters with nested Opinion documents.
                * "r": List of Federal cases (dockets) with up to three nested 
                        documents.
                * "rd": Federal filing documents from PACER.
                * "d": Federal cases (dockets) from PACER.
                * "p": Judges.
                * "oa": Oral argument audio files.
            api_key: CourtListener API key
            highlight: Optional highlight parameter for search results. 
                Use "on" or "all" to enable highlighting of search terms in results.
            court: Optional court code filter (e.g., 'ca9', 'ca2')

        Returns:
            Dictionary with search results
    """
    params = {'q': query, 'type': result_type, 'format': 'json'}
    if highlight is not None:
        params['highlight'] = highlight

    if court is not None:
        params['court'] = court

    return _make_request('/search/', params=params, api_key=api_key)


def get_opinion_by_id(opinion_id: int, api_key: str = API_KEY) -> Dict:
    """
    Retrieve a specific opinion by ID

    Args:
        opinion_id: Opinion ID number
        api_key: CourtListener API key

    Returns:
        Dictionary with opinion data
    """
    endpoint = f'/opinions/{opinion_id}/'
    params = {'format': 'json'}
    return _make_request(endpoint=endpoint, params=params, api_key=api_key)


def get_cluster_by_id(cluster_id: int, api_key: str = API_KEY) -> Dict:
    """
    Retrieve a specific cluster by ID

    Args:
        cluster_id: Cluster ID number
        api_key: CourtListener API key

    Returns:
        Dictionary with cluster data
    """
    endpoint = f'/clusters/{cluster_id}/'
    params = {'format': 'json'}
    return _make_request(endpoint=endpoint, params=params, api_key=api_key)


def get_docket_by_id(docket_id: int, api_key: str = API_KEY) -> Dict:
    """
    Retrieve a specific docket by ID

    Args:
        docket_id: Docket ID number
        api_key: CourtListener API key

    Returns:
        Dictionary with docket data
    """
    endpoint = f'/dockets/{docket_id}/'
    params = {'format': 'json'}
    return _make_request(endpoint=endpoint, params=params, api_key=api_key)


def get_all_results(query: str,
                    max_results: Optional[int] = None,
                    result_type: str = 'o',
                    api_key: str = API_KEY,
                    highlight: Optional[str] = None,
                    court: Optional[str] = None,
                    **kwargs) -> List[Dict]:
    """ Fetch all pages of results for a query. 

        Args:
            query: Search query
            max_results: Maximum number of results to fetch (None = all)
            result_type: Type of search (see get_search_cases() function for options)
            api_key: CourtListener API key
            highlight: Optional highlight parameter for search results.
                Use "on" to enable highlighting of search terms in result snippet.
            court: Optional court code filter (e.g., 'ca9', 'ca2')
            **kwargs: Additional search parameters (will be added to params)

        Returns:
            List of all results across pages
    """
    all_results = []
    page = 1
    next_url = None

    while True:
        print(f"Fetching page {page}...")

        # Use next_url if available, otherwise make initial request
        if next_url is not None:
            response = _make_request(endpoint='',
                                     params=None,
                                     api_key=api_key,
                                     full_url=next_url)
        else:
            response = get_search_cases(query,
                                        result_type=result_type,
                                        api_key=api_key,
                                        highlight=highlight,
                                        court=court)
        results = response.get('results', [])
        all_results.extend(results)

        # Check stopping conditions
        next_url = response.get('next')
        if not next_url:
            print(f"Reached end at page {page}")
            break

        if max_results and len(all_results) >= max_results:
            all_results = all_results[:max_results]
            print(f"Reached max_results limit: {max_results}")
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    logger = get_logger()
    logger.info(f"Total results fetched: {len(all_results)}")

    return all_results


def save_metadata_json(results: List[Dict],
                       filename: Optional[str] = None) -> str:
    """
    Save metadata to JSON file (preserves nested structures)

    Args:
        results: List of opinion dictionaries
        filename: Optional custom filename

    Returns:
        Path to saved file
    """
    logger = get_logger()

    if not filename:
        filename = "complete_metadata.json"

    filepath = RUN_DIR / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(results)} records to: {filepath}")
        return str(filepath)
    except Exception as e:
        logger.error(f"Error saving metadata JSON",
                     exception=e,
                     filename=filename)
        raise


def load_metadata_json(filename: str) -> List[Dict]:
    """
    Load metadata from JSON file

    Args:
        filename: Name of JSON file in run directory

    Returns:
        List of opinion dictionaries
    """
    logger = get_logger()
    filepath = RUN_DIR / filename

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info(f"Loaded metadata from: {filepath}")
        return data
    except FileNotFoundError as e:
        logger.error(f"Metadata file not found",
                     exception=e,
                     filename=filename)
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON file",
                     exception=e,
                     filename=filename)
        raise
    except Exception as e:
        logger.error(f"Error loading metadata JSON",
                     exception=e,
                     filename=filename)
        raise


def download_opinion_pdf(download_url: str, save_path: str) -> bool:
    """ Download opinion PDF from URL.

        Args:
            download_url: URL to PDF
            save_path: Local path to save PDF

        Returns:
            True if successful, False otherwise
    """
    # TODO: replace download url with local url from CourListener API response
    logger = get_logger()
    try:
        logger.debug(f"Downloading PDF from: {download_url}",
                     save_path=str(save_path))
        response = requests.get(download_url, timeout=TIMEOUT)
        response.raise_for_status()

        with open(save_path, 'wb') as f:
            f.write(response.content)
        logger.debug(f"PDF saved to {save_path}")
        return True

    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error downloading PDF",
                     exception=e,
                     download_url=download_url,
                     save_path=str(save_path))
        return False
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout downloading PDF",
                     exception=e,
                     download_url=download_url,
                     save_path=str(save_path))
        return False
    except Exception as e:
        logger.error(f"Failed to download PDF",
                     exception=e,
                     download_url=download_url,
                     save_path=str(save_path))
        return False


def download_opinion_html(opinion_id: int, text: str, save_path) -> str:
    """
    Save opinion text to file

    Args:
        opinion_id: Opinion ID
        text: HTML text content
        save_path: Path to save HTML file

    Returns:
        Path to saved file
    """
    logger = get_logger()

    try:
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(text)
        logger.debug(f"Saved opinion text to: {save_path}",
                     opinion_id=opinion_id)
        return str(save_path)
    except Exception as e:
        logger.error(f"Error saving opinion text",
                     exception=e,
                     opinion_id=opinion_id,
                     save_path=str(save_path))
        raise


def _download_pdf_with_fallback(opinion_id: int, opinion_data: Dict,
                                opinion_dir: Path) -> tuple:
    """
    Attempts PDF download with multiple sources and fallbacks.

    Args:
        opinion_id: Opinion ID number
        opinion_data: Full opinion dictionary from CourtListener API call
        opinion_dir: Directory to save the PDF into.

    Returns:
        A tuple (pdf_saved, pdf_url, pdf_source): whether a PDF was saved, and the URL/source ("local_path", "download_url", or "harvard").
    """
    logger = get_logger()
    pdf_path = opinion_dir / f"opinion_{opinion_id}.pdf"

    candidates = []
    if opinion_data.get('local_path'):
        candidates.append(
            ('local_path', f"{BASE_PDF_URL}/{opinion_data['local_path']}"))
    if opinion_data.get('download_url'):
        candidates.append(('download_url', opinion_data['download_url']))

    for i, (source, url) in enumerate(candidates, start=1):
        logger.debug(f"\t\tPDF attempt {i}: trying '{source}' url: {url}",
                     opinion_id=opinion_id)
        if download_opinion_pdf(url, pdf_path):
            return True, url, source
        time.sleep(REQUEST_DELAY)

    # last resort fallback - harvard server pdf which is sometimes populated in the cluster record
    cluster_id = opinion_data.get('cluster_id')
    cluster_data = get_cluster_by_id(cluster_id) if cluster_id else {}
    harvard_path = cluster_data.get('filepath_pdf_harvard')
    if harvard_path:
        url = f"{BASE_PDF_URL}/{harvard_path}"
        logger.debug(
            f"\t\tPDF attempt {len(candidates) + 1}: trying 'harvard' url: {url}",
            opinion_id=opinion_id)
        if download_opinion_pdf(url, pdf_path):
            return True, url, 'harvard'

    return False, None, None


def download_opinions_from_csv(csv_path: str,
                               output_dir: Path,
                               opinion_id_column: str = 'opinion_id',
                               existing_downloads_dir: Optional[Path] = None):
    """
    Download opinions from a CSV file, skipping already-downloaded ones.

    Exports a summary CSV of download status.

    Args:
        csv_path: Path to CSV file containing opinion IDs
        output_dir: Directory to save new downloads
        opinion_id_column: Name of column containing opinion IDs
        existing_downloads_dir: Directory to check for existing downloads (optional)
    """
    logger = get_logger()

    try:
        df = pd.read_csv(csv_path)
        logger.info(f"Reading CSV file: {csv_path}")

        if opinion_id_column not in df.columns:
            error_msg = f"Column '{opinion_id_column}' not found in CSV. Available columns: {df.columns.tolist()}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        opinion_ids = df[opinion_id_column].dropna().unique().tolist()
        logger.info(f"Found {len(opinion_ids)} unique opinion IDs in CSV")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {output_dir}")

        if existing_downloads_dir:
            logger.info(
                f"Checking for existing downloads in: {existing_downloads_dir}"
            )

        summary_rows = []
        skipped_count = 0

        for i, opinion_id in enumerate(opinion_ids, start=1):
            logger.info(f"[{i}/{len(opinion_ids)}] On opinion {opinion_id} ")
            opinion_dir = output_dir / f"opinion_{opinion_id}"
            html_path = opinion_dir / f"opinion_{opinion_id}.html"

            # check for existing files
            if existing_downloads_dir:
                existing_opinion_dir = existing_downloads_dir / f"opinion_{opinion_id}"
                have_html = (existing_opinion_dir /
                             f"opinion_{opinion_id}.html").exists()
                have_pdf = (existing_opinion_dir /
                            f"opinion_{opinion_id}.pdf").exists()
            else:
                have_html = False
                have_pdf = False

            if have_html and have_pdf:
                # skip downloads
                skipped_count += 1

            need_html = not have_html
            need_pdf = not have_pdf

            logger.info(
                f"html={'needed' if need_html else 'skip'}, pdf={'needed' if need_pdf else 'skip'}..."
            )
            opinion_dir.mkdir(parents=True, exist_ok=True)

            html_downloaded = not need_html
            pdf_downloaded = not need_pdf
            pdf_url = None
            pdf_source = None

            if need_html or need_pdf:
                try:
                    # Get full opinion data
                    opinion_data = get_opinion_by_id(opinion_id)

                    # Save HTML text
                    if need_html and opinion_data.get('html_with_citations'):
                        text = opinion_data['html_with_citations']
                        if text == "":
                            logger.warning(
                                f"Empty 'html_with_citations' for opinion {opinion_id}",
                                opinion_id=opinion_id)
                        else:
                            download_opinion_html(opinion_id, text, html_path)
                            html_downloaded = True

                        if html_downloaded:
                            logger.log_download_success(
                                opinion_id, "HTML saved")
                        else:
                            logger.log_download_failure(
                                opinion_id, "No HTML content downloaded")

                    # Save PDF
                    if need_pdf:
                        pdf_downloaded, pdf_url, pdf_source = _download_pdf_with_fallback(
                            opinion_id, opinion_data, opinion_dir)

                        if pdf_downloaded:
                            logger.log_download_success(
                                opinion_id,
                                f"PDF saved (source: {pdf_source})")
                        else:
                            logger.log_download_failure(
                                opinion_id, "No PDF content downloaded")

                    time.sleep(REQUEST_DELAY)

                except Exception as e:
                    logger.log_download_failure(opinion_id,
                                                str(e),
                                                exception=e)

            summary_rows.append({
                'opinion_id': opinion_id,
                'html_downloaded': html_downloaded,
                'pdf_downloaded': pdf_downloaded,
                'pdf_url': pdf_url or '',
                'pdf_source': pdf_source or '',
            })

        logger.info(
            f"Skipped {skipped_count} opinions with both HTML and PDF already downloaded"
        )
        logger.info(f"Downloads saved to: {output_dir}")

        # write fresh download summary next to the input CSV
        summary_path = Path(csv_path).parent / "opinion_download_summary.csv"
        pd.DataFrame(summary_rows).to_csv(summary_path, index=False)
        logger.info(f"Saved download summary to: {summary_path}")

    except Exception as e:
        logger.error(f"Error in download_opinions_from_csv",
                     exception=e,
                     csv_path=csv_path)
        raise


def save_complete_dataset(results: List[Dict],
                          download_opinions: bool = False) -> Dict[str, str]:
    """
    Save complete dataset: cluster metadata, crosswalks, opinion metadata, docket metadata, and optionally download 
    opinion text/PDFs

    Args:
        results: List of opinion cluster dictionaries from API
        download_opinions: Whether to download full opinion text/PDFs (default: False)

    Returns:
        Dictionary with paths to saved files
    """
    logger = get_logger()
    saved_files = {}

    logger.info("=" * 60)
    logger.info("SAVING METADATA")
    logger.info("=" * 60)

    try:
        # 1. Save opinion cluster metadata (without nested opinion data)
        logger.info("")
        logger.info("1. Extracting and saving opinion cluster metadata...")
        cluster_df = extract_cluster_metadata(results)
        cluster_csv_path = RUN_DIR / "cluster_metadata.csv"
        cluster_df.to_csv(cluster_csv_path,
                          index=False,
                          quoting=csv.QUOTE_NONNUMERIC)
        saved_files['cluster_metadata_csv'] = str(cluster_csv_path)
        logger.info(
            f"   Saved {len(cluster_df)} clusters to: {cluster_csv_path}")

        # 2. Extract and save opinion metadata
        logger.info("")
        logger.info("2. Extracting and saving opinion metadata...")
        opinion_df = extract_opinion_metadata(results)
        opinion_csv_path = RUN_DIR / "opinion_metadata.csv"
        opinion_df.to_csv(opinion_csv_path,
                          index=False,
                          quoting=csv.QUOTE_NONNUMERIC)
        saved_files['opinion_metadata_csv'] = str(opinion_csv_path)
        logger.info(
            f"   Saved {len(opinion_df)} opinions to: {opinion_csv_path}")

        # 3. Extract and save docket metadata
        logger.info("")
        logger.info("3. Extracting and saving docket metadata...")
        docket_df = extract_docket_metadata(results)
        docket_csv_path = RUN_DIR / "docket_metadata.csv"
        docket_df.to_csv(docket_csv_path,
                         index=False,
                         quoting=csv.QUOTE_NONNUMERIC)
        saved_files['docket_metadata_csv'] = str(docket_csv_path)
        logger.info(f"   Saved {len(docket_df)} dockets to: {docket_csv_path}")

        # 4. Save full JSON for reference (preserves all nested structures)
        logger.info("")
        logger.info("4. Saving complete JSON for reference...")
        saved_files['json'] = save_metadata_json(results)
        # logger.info(f"   Saved complete JSON to: {saved_files['json']}")

    except Exception as e:
        logger.error("Error saving dataset", exception=e)
        raise

    # # 5. Create and save cluster→opinion crosswalk
    # print("5. Creating cluster→opinion crosswalk...")
    # cluster_opinion_xwalk = create_cluster_opinion_crosswalk(results)
    # xwalk_opinion_path = RUN_DIR / "cluster_opinion_crosswalk.csv"
    # cluster_opinion_xwalk.to_csv(xwalk_opinion_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    # saved_files['cluster_opinion_crosswalk_csv'] = str(xwalk_opinion_path)
    # print(f"   Saved {len(cluster_opinion_xwalk)} cluster-opinion mappings to: {xwalk_opinion_path}\n")

    # # 6. Create and save cluster→docket crosswalk
    # print("6. Creating cluster→docket crosswalk...")
    # cluster_docket_xwalk = create_cluster_docket_crosswalk(results)
    # xwalk_docket_path = RUN_DIR / "cluster_docket_crosswalk.csv"
    # cluster_docket_xwalk.to_csv(xwalk_docket_path, index=False, quoting=csv.QUOTE_NONNUMERIC)
    # saved_files['cluster_docket_crosswalk_csv'] = str(xwalk_docket_path)
    # print(f"   Saved {len(cluster_docket_xwalk)} cluster-docket mappings to: {xwalk_docket_path}\n")

    # 7. Download opinions if requested
    if download_opinions:
        logger.info("")
        logger.info("7. Downloading opinion text/PDFs...")
        download_opinions_from_csv(csv_path=opinion_csv_path,
                                   output_dir=CURR_OPINIONS_DIR,
                                   opinion_id_column='opinion_id',
                                   existing_downloads_dir=CURR_OPINIONS_DIR)
        saved_files['log'] = str(logger.log_path)
        saved_files['run_dir'] = str(CURR_OPINIONS_DIR)
    else:
        logger.info("")
        logger.info("7. Skipping opinion downloads (download_opinions=False)")

    logger.info("=" * 60)
    logger.info("DATASET SAVE COMPLETE")
    logger.info("=" * 60)

    return saved_files


def extract_cluster_metadata(results: List[Dict]) -> pd.DataFrame:
    """
    Extract cluster-level metadata only (excluding nested opinion data)

    Args:
        results: List of opinion cluster dictionaries from API

    Returns:
        Pandas DataFrame with cluster-level metadata only
    """
    flattened = []

    for item in results:
        flat_item = {}

        # Copy simple fields (excluding nested structures)
        for key, value in item.items():
            if key == 'opinions':  # Skip nested opinions - will be handled separately
                continue
            if not isinstance(value, (dict, list)):
                flat_item[key] = value
                # TODO: debug why this doesn't seem to catch filepath_pdf_harvard fields?

        # Flatten list fields
        if 'citation' in item and isinstance(item['citation'], list):
            flat_item['citation'] = '; '.join(item['citation'])
        if 'non_participating_judge_ids' in item and isinstance(
                item['non_participating_judge_ids'], list):
            flat_item['non_participating_judge_ids'] = '; '.join(
                map(str, item['non_participating_judge_ids']))
        if 'panel_ids' in item and isinstance(item['panel_ids'], list):
            flat_item['panel_ids'] = '; '.join(map(str, item['panel_ids']))
        if 'panel_names' in item and isinstance(item['panel_names'], list):
            flat_item['panel_names'] = '; '.join(item['panel_names'])
        if 'sibling_ids' in item and isinstance(item['sibling_ids'], list):
            flat_item['sibling_ids'] = '; '.join(map(str, item['sibling_ids']))

        # Flatten the "meta" field
        if 'meta' in item and isinstance(item['meta'], dict):
            for meta_key, meta_value in item['meta'].items():
                if meta_key == 'score' and isinstance(meta_value, dict):
                    # meta score is itself a nested dict
                    for score_key, score_value in meta_value.items():
                        flat_item[f"meta_score_{score_key}"] = score_value
                else:
                    flat_item[f"meta_{meta_key}"] = meta_value

        flattened.append(flat_item)

    df = pd.DataFrame(flattened)
    # rearrange columns in alphabetical order
    df = df.reindex(sorted(df.columns), axis=1)

    # Convert date columns to datetime
    date_columns = ['date_filed', 'dateFiled']
    for col in date_columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')

    return df


def extract_opinion_metadata(results: List[Dict]) -> pd.DataFrame:
    """
    Extract full metadata for all individual opinions

    Args:
        results: List of opinion cluster dictionaries from API

    Returns:
        DataFrame with full opinion metadata
    """
    opinion_data = []

    logger = get_logger()
    # logger.info(f"Extracting opinion metadata for {len(results)} clusters...")

    for i, cluster in enumerate(results, 1):
        opinions = cluster.get('opinions', [])

        for opinion in opinions:
            opinion_id = opinion.get('id')

            if not opinion_id:
                logger.warning("Opinion missing ID in cluster",
                               cluster_index=i)
                continue

            try:
                # Fetch full opinion metadata
                full_opinion = get_opinion_by_id(opinion_id)

                # Flatten opinion metadata
                flat_opinion = {}

                # ignore html/text fields since we download them separately
                ignore_fields = [
                    "plain_text", "html", "html_lawbox", "html_columbia",
                    "html_anon_2020", "xml_harvard", "html_with_citations"
                ]
                for field in ignore_fields:
                    full_opinion.pop(field, None)

                for key, value in full_opinion.items():
                    # note we don't expect any nested dicts

                    if not isinstance(value, (dict, list)):
                        flat_opinion[key] = value
                    elif isinstance(value, list):
                        # Flatten lists to semicolon-separated strings
                        flat_opinion[key] = '; '.join(map(
                            str, value)) if value else None

                # TODO: update this
                # add a column to check if html_with_citations is populated; if local_path pdf link is available; if harvard pdf link is available
                # for result in all_results:
                #     opinion_metadata = result.get('opinions', [{}])[0]
                #     opinion_id = opinion_metadata.get('id')
                #     cluster_id = result.get('cluster_id')
                #     opinion = get_opinion_by_id(opinion_id, api_key)
                #     cluster = get_cluster_by_id(cluster_id, api_key)

                #     result['has_html_with_citations'] = bool(opinion.get('html_with_citations')) & (opinion.get('html_with_citations') != "")
                #     result['pdf_local_path'] = opinion.get('local_path')
                #     result['pdf_harvard_path'] = cluster.get('filepath_pdf_harvard')

                # rename "id" to "opinion_id" and "type" to "opinion_type" for clarity
                flat_opinion['opinion_id'] = flat_opinion.pop('id', None)
                flat_opinion['opinion_type'] = flat_opinion.pop('type', None)

                opinion_data.append(flat_opinion)
                time.sleep(REQUEST_DELAY)

            except Exception as e:
                logger.error(f"Error fetching opinion {opinion_id}",
                             exception=e,
                             opinion_id=opinion_id)

        if (i % 100) == 0:
            logger.info(f"Processed {i}/{len(results)} clusters...")

    df = pd.DataFrame(opinion_data)
    if not df.empty:
        # rearrange columns in alphabetical order
        df = df.reindex(sorted(df.columns), axis=1)

    return df


def extract_docket_metadata(results: List[Dict]) -> pd.DataFrame:
    """
    Extract full metadata for all dockets

    Args:
        results: List of opinion cluster dictionaries from API

    Returns:
        DataFrame with full docket metadata
    """
    # Get unique docket IDs
    docket_ids = set()
    for cluster in results:
        docket_id = cluster.get('docket_id')
        if docket_id:
            docket_ids.add(docket_id)

    logger = get_logger()
    # logger.info(f"Extracting metadata for {len(docket_ids)} unique dockets...")

    docket_data = []

    for i, docket_id in enumerate(sorted(docket_ids), 1):
        try:
            # Fetch full docket metadata via API
            docket = get_docket_by_id(docket_id)

            # Flatten docket metadata
            flat_docket = {}
            for key, value in docket.items():
                if not isinstance(value, (dict, list)):
                    flat_docket[key] = value
                elif isinstance(value, list):
                    # Flatten lists to semicolon-separated strings
                    flat_docket[key] = '; '.join(map(str,
                                                     value)) if value else None

            # rename "id" to "docket_id" for clarity
            flat_docket['docket_id'] = flat_docket.pop('id', None)

            docket_data.append(flat_docket)
            time.sleep(REQUEST_DELAY)

        except Exception as e:
            logger.error(f"Error fetching docket {docket_id}",
                         exception=e,
                         docket_id=docket_id)

        if (i % 100) == 0:
            logger.info(f"Processed {i}/{len(docket_ids)} dockets...")

    df = pd.DataFrame(docket_data)
    if not df.empty:
        df = df.reindex(sorted(df.columns), axis=1)

    return df


# def create_cluster_opinion_crosswalk(results: List[Dict]) -> pd.DataFrame:
#     """
#     Create crosswalk mapping opinion clusters to individual opinions with opinion types

#     Args:
#         results: List of opinion cluster dictionaries from API

#     Returns:
#         DataFrame with columns: cluster_id, opinion_id, opinion_type
#     """
#     crosswalk_data = []

#     print(f"Creating cluster-opinion crosswalk for {len(results)} clusters...")

#     for i, cluster in enumerate(results, 1):
#         cluster_id = cluster.get('cluster_id')

#         if not cluster_id:
#             print(f"Warning: Cluster {i} has no ID, skipping")
#             continue

#         # Get opinion IDs from nested opinions field
#         opinions = cluster.get('opinions', [])

#         if not opinions:
#             print(f"Warning: Cluster {cluster_id} has no opinions")
#             continue

#         # For each opinion, fetch full metadata to get opinion type
#         for opinion in opinions:
#             opinion_id = opinion.get('id')

#             if not opinion_id:
#                 print(f"Warning: Cluster {cluster_id} has opinion with no ID")
#                 continue

#             # Fetch full opinion metadata to get type
#             try:
#                 opinion_data = get_opinion_by_id(opinion_id)
#                 opinion_type = opinion_data.get('type', None)

#                 crosswalk_data.append({
#                     'cluster_id': cluster_id,
#                     'opinion_id': opinion_id,
#                     'opinion_type': opinion_type
#                 })

#                 time.sleep(REQUEST_DELAY)

#             except Exception as e:
#                 print(f"Error fetching opinion {opinion_id}: {e}")
#                 crosswalk_data.append({
#                     'cluster_id': cluster_id,
#                     'opinion_id': opinion_id,
#                     'opinion_type': None
#                 })

#         if (i % 100) == 0:
#             print(f"Processed {i}/{len(results)} clusters...")

#     df = pd.DataFrame(crosswalk_data)
#     return df

# def create_cluster_docket_crosswalk(results: List[Dict]) -> pd.DataFrame:
#     """
#     Create crosswalk mapping opinion clusters to dockets

#     NOTE: this is completely redundant with the cluster metadata, which already lists docket number and docket ID.

#     Args:
#         results: List of opinion cluster dictionaries from API

#     Returns:
#         DataFrame with columns: cluster_id, raw_docket_number, docket_id
#     """
#     crosswalk_data = []

#     print(f"Creating cluster-docket crosswalk for {len(results)} clusters...")

#     for i, cluster in enumerate(results, 1):
#         cluster_id = cluster.get('cluster_id')
#         docket_id = cluster.get('docket_id')
#         raw_docket_number = cluster.get('docketNumber')

#         crosswalk_data.append({
#             'cluster_id': cluster_id,
#             'docket_id': docket_id,
#             'raw_docket_number': raw_docket_number,
#         })

#         if (i % 100) == 0:
#             print(f"Processed {i}/{len(results)} clusters...")

#     df = pd.DataFrame(crosswalk_data)
#     return df
