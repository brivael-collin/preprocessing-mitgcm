#!/bin/bash

BINARY_DATA_DIR="../binary_data"
CODE_DIR="../code"
GRID_DIR="../grid"
RUN_CONFIG_DIR="../run_config"
POSTPROCESSING_DIR="../postprocessing"

OUTPUT_PATH="./input_files.zip"
rm -f "$OUTPUT_PATH"

zip -r "$OUTPUT_PATH" \
    "$BINARY_DATA_DIR" \
    "$CODE_DIR" \
    "$GRID_DIR" \
    "$RUN_CONFIG_DIR" \
    "$POSTPROCESSING_DIR"
