from pydantic import BaseModel
import time
import requests
import os
import json
import pandas as pd
from google.genai import errors
from utils.gemini_logging import _log_and_print


class RateLimitException(Exception):
    """Raised when 429 retries are exhausted to abort full run."""


def upload_to_API(genai_client, file_path: str, log_dir=None, identifier=None):
    """
    Uploads court case opinion file to the Gemini API.

    Parameters:
        genai_client: Gemini API client.
        file_path (str): Path to the input opinion file.
        log_dir (str): Directory for writing Gemini error logs.
        identifier (str): Run identifier used for the Gemini log filename.

    Returns:
        object: Uploaded file object from the Gemini API.
    """
    file_name = os.path.basename(file_path)

    # Check if file already exists in the File API
    uploaded_file = None
    max_retries = 7
    base_wait = 10
    should_check_existing = True

    # Error handling: retry server errors (5xx) and rate limits (429) with exponential backoff.
    # For all other errors, in order to keep things running, we bypass the check for existing files and upload directly.
    for attempt in range(max_retries):
        if not should_check_existing:
            break
        try:
            existing_files = genai_client.files.list()
            for f in existing_files:
                if f.display_name == file_name:
                    uploaded_file = f
                    print(
                        f"    File '{file_name}' already exists in the File API. Skipping upload."
                    )
                    break
            break
        except errors.ServerError as e:
            wait_time = base_wait * (2**attempt)
            m = f"Server error {e.code} while checking existing upload for '{file_name}' on attempt {attempt + 1}. Retrying in {wait_time:.1f}s..."
            _log_and_print(m, log_dir, identifier)
            time.sleep(wait_time)
        except errors.ClientError as e:
            if e.code == 429:
                wait_time = 60 * (2**attempt)
                m = f"Rate limit (429 error) while checking existing upload for '{file_name}' on attempt {attempt + 1}. Retrying in {wait_time:.1f}s..."
                _log_and_print(m, log_dir, identifier)
                time.sleep(wait_time)
            else:
                m = f"Warning: existing file check failed for '{file_name}' (client error {e.code}). Skipping check and proceeding with direct upload: {e}"
                _log_and_print(m, log_dir, identifier)
                should_check_existing = False
        except Exception as e:
            m = f"Warning: existing file check failed for '{file_name}'. Skipping check and proceeding with direct upload: {e}"
            _log_and_print(m, log_dir, identifier)
            should_check_existing = False

    if should_check_existing and not uploaded_file and attempt == max_retries - 1:
        m = f"Max retries reached while checking existing upload for '{file_name}'. Proceeding with direct upload."
        _log_and_print(m, log_dir, identifier)

    # Upload file (only if it has not already been uploaded)
    if not uploaded_file:
        print(f"    Uploading file: {file_name}")
        uploaded_file = genai_client.files.upload(
            file=file_path, config={'display_name': file_name})

    return uploaded_file


def _save_partial_results(all_dataframes, outfile_path, log_dir, identifier,
                          reason):
    """
    Saves accumulated rows to CSV and returns the concatenated DataFrame.

    Parameters:
        all_dataframes (list): List of one-row DataFrames to concatenate and save.
        outfile_path (str): Output CSV path.
        log_dir (str): Logging directory.
        identifier (str): Run identifier.
        reason (str): Reason why the partial save was triggered.

    Returns:
        Concatenated DataFrame, or None.
    """
    if not all_dataframes:
        _log_and_print(f"{reason}: no partial results to save.", log_dir,
                       identifier)
        return None
    partial_df = pd.concat(all_dataframes, ignore_index=True)
    partial_df.to_csv(outfile_path, index=False)
    _log_and_print(
        f"{reason}: partial results saved to {outfile_path} ({partial_df.shape[0]} rows).",
        log_dir, identifier)
    return partial_df


def extract_case_data(genai_client,
                      input_files: list,
                      data_struct: type[BaseModel],
                      prompt_text: str,
                      model_id: str,
                      case_id=None,
                      log_dir=None,
                      identifier=None,
                      debug=False):
    """
    Extracts structured data from one or more court case opinion files using the Gemini API.

    Parameters:
        genai_client: Gemini API client.
        input_files (list): File objects uploaded to the Gemini API.
        data_struct (BaseModel): Data structure for extracted content.
        prompt_text (str): Prompt text for the API.
        model_id (str): Gemini model ID.
        case_id (str): Opinion/case identifier used in error logging context.
        log_dir (str): Directory for writing Gemini error logs.
        identifier (str): Run identifier used for the Gemini log filename.
        debug (bool): Enables debug logging.

    Returns:
        dict or None: Parsed structured data if successful, otherwise None.
    """
    # limit output size
    max_token_output = 80000
    max_retries = 7
    base_wait = 10  # this is in seconds!

    for attempt in range(max_retries):
        print(f"      Attempt {attempt + 1} to extract data...")
        try:
            # Generate a structured response using the Gemini API ---
            response = genai_client.models.generate_content(
                model=model_id,
                contents=[prompt_text, *input_files],
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': data_struct,
                    'max_output_tokens': max_token_output
                })

            # print("API Response:", response)  # Debugging step
            # print(" Response Usage Metadata:", response.usage_metadata)

            # Added: Check for token limit issues
            if hasattr(response, 'candidates') and response.candidates:
                if response.candidates[0].finish_reason.name == 'MAX_TOKENS':
                    print(
                        f"WARNING: Response truncated due to token limit. Consider increasing max_output_tokens or splitting the page."
                    )
                    print(
                        f"Token count: {response.usage_metadata.candidates_token_count}"
                    )

            if debug:
                file_path = "output.txt"

                # Open the file in append mode and write text multiple times
                with open(file_path, "a", encoding="utf-8") as file:
                    for i in range(5):  # Writing 5 times
                        file.write(
                            f"Line {i + 1}: This is some text being written.\n"
                        )

            if not response or not response.parsed:
                m = "ERROR: The API did not return a valid parsed response."
                _log_and_print(
                    f"case_id={case_id} \t\nmodel_id={model_id} \t\nextract_attempt={attempt + 1} \t\n{m}",
                    log_dir, identifier)
                return None

            return response.parsed

        # retry server errors with exponential backoff; retry 429s with a longer wait and kill the run if they persist
        except errors.ServerError as e:
            wait_time = base_wait * (2**attempt)
            m = f"Server error {e.code} on attempt {attempt + 1}. Retrying in {wait_time:.1f}s..."
            _log_and_print(
                f"case_id={case_id} \t\nmodel_id={model_id} \t\nextract_attempt={attempt + 1} \t\n{m}",
                log_dir, identifier)
            time.sleep(wait_time)
        except errors.ClientError as e:
            if e.code == 429:
                # rate limits are per minute and per day; if a long wait still hits the limit we have likely exhausted the daily quota and should downgrade the model, so kill the run
                if attempt == max_retries - 1:
                    m = "Max rate limit retries reached."
                    _log_and_print(
                        f"case_id={case_id} \t\nmodel_id={model_id} \t\n{m}",
                        log_dir, identifier)
                    raise RateLimitException(
                        "Max rate limit retries reached. Killing rest of the full run."
                    )
                wait_time = 60 * (2**attempt)
                m = f"Rate limit (429 error) on attempt {attempt + 1}. Retrying in {wait_time:.1f}s..."
                _log_and_print(
                    f"case_id={case_id} \t\nmodel_id={model_id} \t\nextract_attempt={attempt + 1} \t\n{m}",
                    log_dir, identifier)
                time.sleep(wait_time)
            else:
                m = f"Client error {e.code} occurred (non-retryable): {e}"
                _log_and_print(
                    f"case_id={case_id} \t\nmodel_id={model_id} \t\nextract_attempt={attempt + 1} \t\n{m}",
                    log_dir, identifier)
                return None
        except Exception as e:
            m = f"Other exception occurred (non-retryable): {e}"
            _log_and_print(
                f"case_id={case_id} \t\nmodel_id={model_id} \t\nextract_attempt={attempt + 1} \t\n{m}",
                log_dir, identifier)
            return None

    m = "Max error retries reached. Giving up on this case."
    _log_and_print(f"case_id={case_id} \t\nmodel_id={model_id} \t\n{m}",
                   log_dir, identifier)
    return None


# ==============================================================================
# Processing loop
# ==============================================================================


def process_cases(genai_client,
                  input_dir: str,
                  data_struct: type[BaseModel],
                  prompt_text: str,
                  model_id: str,
                  outfile_path: str,
                  intermediate_dir: str,
                  to_dataframe_fn,
                  case_ids: list = None,
                  log_dir=None,
                  identifier=None,
                  debug=False,
                  reuse_old_results: bool = False):
    """
    Extracts structured data from court case opinion files and saves results.

    Parameters:
        genai_client: Gemini API client.
        input_dir (str): Path to directory containing opinion_XXX folders.
        data_struct (BaseModel): Data structure for extracted content.
        prompt_text (str): Prompt text for the API.
        model_id (str): Gemini model ID.
        outfile_path (str): Path to save extracted data.
        intermediate_dir (str): Folder for intermediate outputs.
        to_dataframe_fn: Function converting parsed schema object to dataframe.
        case_ids (list): Optional list of specific case IDs to process. If None, processes all cases.
        log_dir (str): Directory for writing Gemini error logs.
        identifier (str): Run identifier used for the Gemini log filename.
        debug (bool): Enables debug logging.
        reuse_old_results (bool): If True, cases whose intermediate JSON already exists in intermediate_dir are loaded from disk instead of re-queried.

    Returns:
        pd.DataFrame: Aggregated structured data extracted from all cases.
    """
    # TODO: add handling if there are errors for one page but not other pages
    # include a print and a log of failed pages

    # Get list of case folders to process
    if case_ids is None:
        case_folders = [
            f for f in os.listdir(input_dir) if f.startswith('opinion_')
            and os.path.isdir(os.path.join(input_dir, f))
        ]
        case_ids = [f.replace('opinion_', '') for f in case_folders]
    total_cases = len(case_ids)

    all_dataframes = []
    max_retries = 5
    start_time = time.time()

    # track issues in real time
    error_count = 0
    missing_file_skip_count = 0

    try:
        for i, case_id in enumerate(case_ids):
            # add counter for cases processed
            print(f"\nProcessing case {case_id} ({i + 1}/{total_cases})...")
            case_folder = os.path.join(input_dir, f"opinion_{case_id}")
            json_path = os.path.join(intermediate_dir,
                                     f"coded_opinion_{case_id}.json")

            # Resume support: load intermediate JSON if it already exists rather than re-querying Gemini
            if reuse_old_results and os.path.exists(json_path):
                print(
                    f"  Case {case_id} ({i + 1}/{total_cases}): intermediate JSON exists, reusing cached result."
                )
                with open(json_path, "r", encoding="utf-8") as file:
                    result_json = json.load(file)
                result = data_struct.model_validate(result_json)
                df = to_dataframe_fn(result)
                for key in ("opinion_id", "file_source_indicator", "model_id"):
                    if key in result_json:
                        df[key] = result_json[key]
                all_dataframes.append(df)
                continue

            # try to attach both html and pdf files if available
            html_path = os.path.join(case_folder, f"opinion_{case_id}.html")
            pdf_path = os.path.join(case_folder, f"opinion_{case_id}.pdf")
            case_opinion_paths = [
                p for p in (html_path, pdf_path) if os.path.exists(p)
            ]

            if not case_opinion_paths:
                print(
                    f"WARNING: no html or pdf file found for case {case_id}, skipping..."
                )
                missing_file_skip_count += 1
                continue

            file_source_indicator = "+".join(
                os.path.splitext(p)[1].lstrip(".") for p in case_opinion_paths)

            retries = 0
            success = False
            prompt = prompt_text
            df = None

            while retries < max_retries and not success:
                try:
                    print(f"\t(Attempt {retries + 1})...")

                    # Upload each available opinion file
                    uploaded_files = [
                        upload_to_API(genai_client,
                                      p,
                                      log_dir=log_dir,
                                      identifier=identifier)
                        for p in case_opinion_paths
                    ]

                    # Extract case data
                    result = extract_case_data(genai_client,
                                               uploaded_files,
                                               data_struct,
                                               prompt,
                                               model_id,
                                               case_id=case_id,
                                               log_dir=log_dir,
                                               identifier=identifier,
                                               debug=debug)

                    if result:
                        success = True
                        runtime_metadata = {
                            "opinion_id": case_id,
                            "file_source_indicator": file_source_indicator,
                            "model_id": model_id
                        }

                        # add additional tracked information to the json
                        json_path = os.path.join(
                            intermediate_dir, f"coded_opinion_{case_id}.json")
                        result_json = result.model_dump()
                        result_json.update(runtime_metadata)

                        # save intermediate data structure to json to handle unplanned termination and be able to resume from existing progress
                        with open(json_path, "w", encoding="utf-8") as file:
                            json.dump(result_json,
                                      file,
                                      indent=4,
                                      ensure_ascii=False)
                        print(
                            f"  Saved intermediate JSON of coded opinion to {json_path}"
                        )

                        df = to_dataframe_fn(result)
                        # add metadata to final dataframe
                        for key, value in runtime_metadata.items():
                            df[key] = value

                        # Immediately delete the uploaded files to avoid storage limits
                        for uploaded_file in uploaded_files:
                            try:
                                genai_client.files.delete(
                                    name=uploaded_file.name)
                                print(
                                    f"Deleted uploaded file: {uploaded_file.name}"
                                )
                            except Exception as e:
                                print(
                                    f"Warning: failed to delete uploaded file {uploaded_file.name}: {e}"
                                )

                    else:
                        m = f"FAILURE - No data found for case {case_id}."
                        _log_and_print(
                            f"case_id={case_id} \t\nfile_source_indicator={file_source_indicator} \t\nmodel_id={model_id} \t\n{m}",
                            log_dir, identifier)

                except requests.exceptions.ConnectionError as e:
                    m = f"Connection error for opinion {case_id}: {e}"
                    _log_and_print(
                        f"case_id={case_id} \t\ncase_attempt={retries + 1} \t\nfile_source_indicator={file_source_indicator} \t\n{m}",
                        log_dir, identifier)
                    retries += 1
                    if retries < max_retries:
                        m = f"Retrying opinion {case_id} in 5 seconds..."
                        _log_and_print(
                            f"case_id={case_id} \t\ncase_attempt={retries + 1} \t\n{m}",
                            log_dir, identifier)
                        time.sleep(5)
                    else:
                        _log_and_print(
                            f"Max retries reached for case {case_id}. Raising ValueError.",
                            log_dir, identifier)
                        print(
                            f"Warning: Max retries reached for case {case_id}."
                        )

            if not success:
                error_count += 1
                # continue

            # Combine output
            if success and df is not None:
                all_dataframes.append(df)

            total_time_elapsed = time.time() - start_time
            avg_time_per_case = total_time_elapsed / (i + 1)
            # print(f"Total time elapsed: {total_time_elapsed / 3600:.2f} hrs")
            # print(f"Average time per case so far: {avg_time_per_case:.2f} s")
            # print(f"Cases with no Gemini output so far: {error_count}")
            # print(
            #     f"Cases skipped for missing files so far: {missing_file_skip_count}"
            # )

            if (i + 1) % 10 == 0:
                _log_and_print(f"Progress: {i + 1}/{total_cases}", log_dir,
                               identifier)
                _log_and_print(
                    f"Total time elapsed: {total_time_elapsed / 3600:.2f} hrs",
                    log_dir, identifier)
                _log_and_print(
                    f"Average time per Gemini query so far: {avg_time_per_case:.2f} s",
                    log_dir, identifier)
                _log_and_print(
                    f"Cases with no Gemini output so far: {error_count}",
                    log_dir, identifier)
                _log_and_print(
                    f"Cases skipped for missing files so far: {missing_file_skip_count}",
                    log_dir, identifier)

    except KeyboardInterrupt:
        _log_and_print("RUN INTERRUPTED by user.", log_dir, identifier)
        _save_partial_results(all_dataframes, outfile_path, log_dir,
                              identifier, "Keyboard interrupt")
        raise
    except RateLimitException as e:
        _log_and_print(f"FATAL rate limit error: {e}", log_dir, identifier)
        _save_partial_results(all_dataframes, outfile_path, log_dir,
                              identifier, "Fatal rate limit stop")
        raise

    # log error and missing file counts to log file
    m = f"Total cases with no Gemini output: {error_count}"
    _log_and_print(m, log_dir, identifier)
    m = f"Total cases skipped for missing files: {missing_file_skip_count}"
    _log_and_print(m, log_dir, identifier)

    if all_dataframes:
        final_dataframe = pd.concat(all_dataframes, ignore_index=True)
        print(f"\n Generated dataframe with {final_dataframe.shape[0]} rows")
        final_dataframe.to_csv(outfile_path, index=False)
        print(f"  Saved final output to {outfile_path}\n")
        return final_dataframe
    else:
        return None
