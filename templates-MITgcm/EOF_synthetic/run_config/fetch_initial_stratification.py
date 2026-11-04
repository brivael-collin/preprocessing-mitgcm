import csv
import datetime
import re
import sys

CSV_PATH = "stratification.csv"  # Define the global CSV file path

def fetch_tRef_in_data_file(lines):
    # Identify the tRef array section from "data"
    start_index, format_match = None, None
    for idx, line in enumerate(lines):
        if line.startswith(" tRef = "):
            start_index = idx + 1
            break

    if start_index is None:
        raise ValueError("'tRef' section not found in data.txt.")

    # Get array until the next blank line
    tRef_lines = []
    for line in lines[start_index:]:
        if line.strip():  # Non-blank lines
            tRef_lines.append(line.strip())
        else:
            break

    # Detect comma-separated formatting
    tRef_content = " ".join(tRef_lines).replace("_d 0", "").strip()
    format_match = re.match(r"^[\d.,\s]+$", tRef_content)  # Verify array format

    if not format_match:
        raise ValueError("Invalid or unexpected 'tRef' format detected in data.txt.")

    # Extract array shape based on number of elements per tRef line
    shape = [len(re.findall(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?", line)) for line in tRef_lines]

    return start_index, tRef_lines, shape


def parse_date():
    if len(sys.argv) < 2:
        raise ValueError("Please provide the date and time (yyyy-mm-dd) as a command-line argument.")

    date_input = sys.argv[1].strip()
    try:
        # Verify input date-time format
        input_datetime = datetime.datetime.strptime(date_input, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Invalid date format. Please use 'yyyy-mm-dd'.")

    return date_input

if __name__ == "__main__":
    date_input = parse_date()

    # Extract column in CSV file corresponding to input date
    column_data = []
    with open(CSV_PATH, "r") as csvfile:
        reader = csv.DictReader(csvfile)
        if date_input not in reader.fieldnames:
            raise KeyError(f"No matching column for date {date_input} in CSV file.")

        for row in reader:
            column_data.append(row[date_input])

    #Read "data" file
    with open("data", "r") as file:
        lines = file.readlines()
    start_index, tRef_lines, shape = fetch_tRef_in_data_file(lines)

    # Format and write updated tRef section back to "data.txt"
    # Reshape column_data to match array shape
    reshaped_data = []
    idx = 0
    for row_length in shape:
        reshaped_data.append(column_data[idx:idx + row_length])
        idx += row_length

    # Format reshaped data into tRef format
    formatted_data = "\n".join([",".join(row) for row in reshaped_data])
    updated_lines = (
            lines[:start_index] + [formatted_data + "\n"] + lines[start_index + len(tRef_lines):]
    )

    with open("data", "w") as file:
        file.writelines(updated_lines)
