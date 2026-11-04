def contains_nan(filename="STDOUT.0000"):
    try:
        with open(filename, "r") as f:
            content = f.read()
        if "nan" in content.lower():
            raise ValueError(f"Error: 'Nan' found in file {filename}.")
        else:
            print(f"The {filename} file does NOT contain the word 'Nan'.")
    except FileNotFoundError:
        print(f"File '{filename}' not found.")

if __name__ == "__main__":
    contains_nan()