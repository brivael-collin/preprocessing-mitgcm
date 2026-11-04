#!/bin/bash

INPUT_DIR="../pickup"
OUTPUT_PATH="./pickup.zip"
rm -f "$OUTPUT_PATH"

zip -r "$OUTPUT_PATH" "$INPUT_DIR"
