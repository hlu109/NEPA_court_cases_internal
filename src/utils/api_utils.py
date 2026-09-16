"""
API interaction utilities for CourtListener
"""

import requests
import time
import json
import re
from typing import Dict, List, Optional, Any
from src.utils.config import API_KEY, BASE_API_URL, TIMEOUT, RETRY_WAIT_TIME, MAX_RETRIES
from src.utils.logger import get_logger


def _get_headers(api_key: str = API_KEY) -> Dict[str, str]:
    """ Get request headers with API authentication

        Args:
            api_key: CourtListener API key

        Returns:
            Dictionary of headers
    """
    return {
        'Authorization': f'Token {api_key}',
        'Content-Type': 'application/json'
    }


def _make_request(endpoint: str,
                  params: Optional[Dict] = None,
                  full_url: Optional[str] = None,
                  api_key: str = API_KEY,
                  retry_count: int = 0) -> Dict:
    """ Make API request with error handling and retry logic for 502 and 429 errors.

        Args:
            endpoint: API endpoint (e.g., '/search/')
            params: Query parameters
            api_key: CourtListener API key
            full_url: Optional full URL to use instead of constructing from endpoint
            retry_count: Internal counter for retry attempts (used recursively)

        Returns:
            JSON response as dictionary
    """
    # Use full URL if provided, otherwise build from endpoint
    if full_url:
        url = full_url
    else:
        # Build URL and avoid double slashes
        url = f"{BASE_API_URL}{endpoint}"
        if not endpoint.startswith('/'):
            url = f"{BASE_API_URL}/{endpoint}"

    logger = get_logger()

    try:
        logger.log_api_request(endpoint if not full_url else full_url)
        response = requests.get(
            url,
            headers=_get_headers(api_key),
            params=params
            if not full_url else None,  # Don't use params with full_url
            timeout=TIMEOUT)
        response.raise_for_status()
        logger.log_api_request(endpoint if not full_url else full_url,
                               status="success")
        return response.json()

    except requests.exceptions.HTTPError as e:
        status_code = response.status_code

        # Handle 502 Bad Gateway with retry
        if status_code == 502 and retry_count < MAX_RETRIES:
            wait_time = RETRY_WAIT_TIME * (2**retry_count
                                           )  # Exponential backoff
            logger.warning(
                f"502 Bad Gateway error (attempt {retry_count + 1}/{MAX_RETRIES}). "
                f"Retrying in {wait_time:.1f} seconds...",
                endpoint=endpoint if not full_url else full_url,
                retry_count=retry_count + 1)
            time.sleep(wait_time)
            return _make_request(endpoint=endpoint,
                                 params=params,
                                 full_url=full_url,
                                 api_key=api_key,
                                 retry_count=retry_count + 1)

        # Handle 429 Too Many Requests with retry
        elif status_code == 429 and retry_count < MAX_RETRIES:
            # Try to parse wait time from error response
            wait_time = RETRY_WAIT_TIME
            try:
                error_detail = response.json()
                if isinstance(error_detail, dict) and 'detail' in error_detail:
                    detail_str = error_detail['detail']
                    # Parse "Expected available in X seconds" from the detail message
                    match = re.search(r'(\d+)\s+seconds?', detail_str,
                                      re.IGNORECASE)
                    if match:
                        wait_time = int(
                            match.group(1)) + RETRY_WAIT_TIME  # add buffer
                        logger.info(
                            f"Parsed wait time from 429 error: {wait_time} seconds",
                            endpoint=endpoint if not full_url else full_url)
            except (json.JSONDecodeError, ValueError, AttributeError):
                # If parsing fails, use default retry wait time
                pass

            logger.warning(
                f"429 Too Many Requests (attempt {retry_count + 1}/{MAX_RETRIES}). "
                f"Waiting {wait_time} seconds before retry...",
                endpoint=endpoint if not full_url else full_url,
                retry_count=retry_count + 1,
                wait_time=wait_time)
            time.sleep(wait_time)
            return _make_request(endpoint=endpoint,
                                 params=params,
                                 full_url=full_url,
                                 api_key=api_key,
                                 retry_count=retry_count + 1)

        # For other HTTP errors or max retries reached, log and raise
        error_msg = f"HTTP Error {status_code}: {e}"
        logger.log_api_error(endpoint if not full_url else full_url,
                             error_msg,
                             exception=e)
        try:
            logger.error(f"Response body: {response.text[:500]}",
                         endpoint=endpoint if not full_url else full_url,
                         status_code=status_code)
        except:
            pass
        raise

    except requests.exceptions.Timeout as e:
        error_msg = f"Request timed out after {TIMEOUT} seconds"
        logger.log_api_error(endpoint if not full_url else full_url,
                             error_msg,
                             exception=e)
        raise
    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {e}"
        logger.log_api_error(endpoint if not full_url else full_url,
                             error_msg,
                             exception=e)
        raise
    except Exception as e:
        error_msg = f"Unexpected error in API request: {e}"
        logger.log_api_error(endpoint if not full_url else full_url,
                             error_msg,
                             exception=e)
        raise
