import os
import json
from datetime import datetime


def write_log(message, log_dir, identifier):
    """
    Appends a timestamped message to a run-specific log file.

    Parameters:
        message (str): Message text to append.
        log_dir (str): Directory where log files are stored.
        identifier (str): Run identifier used in the log filename.
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    file_path = os.path.join(log_dir, f"log_{identifier}.txt")
    with open(file_path, "a", encoding="utf-8") as file:
        timestamp = datetime.now().strftime("%H:%M:%S")
        file.write(f"[{timestamp}] {message}\n\n")


def write_run_boundary(log_dir, identifier, label):
    """
    Writes a labeled separator to the run's log file marking where a script invocation begins or ends.

    Parameters:
        log_dir (str): Directory where log files are stored.
        identifier (str): Run identifier used in the log filename.
        label (str): Short label for the boundary (e.g. "START" or "END").
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    file_path = os.path.join(log_dir, f"log_{identifier}.txt")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(file_path, "a", encoding="utf-8") as file:
        file.write(f"{'*' * 30} RUN {label} [{timestamp}] {'*' * 30}\n\n")


def _log_and_print(message, log_dir=None, identifier=None):
    """
    Convenient wrapper to print a message and optionally writes it to a log file.

    Parameters:
        message (str): Message to print and optionally log.
        log_dir (str): Log directory; if omitted, message is only printed.
        identifier (str): Run identifier for the log filename.
    """
    print(message)
    if log_dir and identifier:
        write_log(message, log_dir, identifier)


def log_config(prompt_text_path,
               gemini_model_id,
               identifier,
               log_dir,
               input_dir=None,
               case_ids=None,
               data_struct=None,
               output_path=None,
               intermediate_dir=None,
               reuse_old_results=False,
               resume_run_identifier=None,
               note=None):
    """
    Logs prompt text and configuration values for a Gemini run.

    Parameters:
        prompt_text_path (str): Path to the prompt text file.
        gemini_model_id (str): Gemini model to use.
        identifier (str): Run identifier used for config and log filenames.
        log_dir (str): Directory where log outputs are saved.
        input_dir (str): Input directory being processed.
        case_ids (list): Subset of case IDs being processed. (None value indicates all cases.)
        data_struct (BaseModel): output data structure.
        output_path (str): Path to the final output CSV.
        intermediate_dir (str): Folder for saving intermediate JSONs.
        reuse_old_results (bool): Whether this run resumes from cached intermediate JSONs.
        resume_run_identifier (str): Identifier of the run being resumed.
        note (str): Free-text note describing the run's purpose.
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    separator = f"{'*' * 30} [{timestamp}] {'*' * 30}\n"

    # archive the prompt text; append with a separator so we can see if pause/resume runs have different prompts
    with open(prompt_text_path, "r", encoding="utf-8") as file:
        prompt_text = file.read()
    with open(os.path.join(log_dir, f"prompt_text_{identifier}.txt"),
              "a",
              encoding="utf-8") as file:
        file.write(separator)
        file.write(prompt_text)
        file.write("\n\n")

    # archive the data structure/output schema separately since it is too long to inline in the main log
    data_struct_path = os.path.join(log_dir, f"data_struct_{identifier}.txt")
    if data_struct is not None:
        with open(data_struct_path, "a", encoding="utf-8") as file:
            file.write(separator)
            json.dump(data_struct.model_json_schema(), file, indent=2)
            file.write("\n\n")

    # log other config parameters
    file_path = os.path.join(log_dir, f"log_{identifier}.txt")
    with open(file_path, "a", encoding="utf-8") as file:
        file.write(f"[{timestamp}] \n\n")
        file.write(f"CONFIG PARAMETERS\n\n")
        if note:
            file.write(f"Note: {note}\n")
        file.write(f"Run identifier: {identifier}\n")
        file.write(f"Input directory: {input_dir}\n")
        file.write(f"Output CSV: {output_path}\n")
        file.write(f"Intermediate JSON dir: {intermediate_dir}\n")
        file.write(
            f"Case IDs filter: {case_ids if case_ids else 'All cases'}\n")
        file.write(f"Prompt text file: {prompt_text_path}\n")
        if data_struct is not None:
            file.write(f"Data structure file: {data_struct_path}\n")
        file.write(f"Gemini model: {gemini_model_id}\n")
        if reuse_old_results:
            file.write(
                f"Reuse old results: True, resumed from run '{resume_run_identifier}'\n\n"
            )
        else:
            file.write(f"Reuse old results: False\n\n")
