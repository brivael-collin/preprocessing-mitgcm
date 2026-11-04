#!/bin/bash

PACKET_SIZE=$((2 * 24 * 31))
PREFIX="month"
INPUT_DIR="../outputs"
OUTPUT_DIR="./outputs"
START_PACKET=12

COUNT=0
PACKET=1
FILES=()

mkdir -p "$OUTPUT_DIR"

while IFS= read -r file; do
    FILES+=("$file")
    ((COUNT++))

    if [ "$COUNT" -eq "$PACKET_SIZE" ]; then
        if [ "$PACKET" -ge "$START_PACKET" ]; then
            printf -v NUM "%03d" "$PACKET"
            zip "${OUTPUT_DIR}/${PREFIX}_${NUM}.zip" \
                "${FILES[@]/#/${INPUT_DIR}/}"
        fi
        FILES=()
        COUNT=0
        ((PACKET++))
    fi
done < <(ls -1 "$INPUT_DIR" | sort)

# Handle remaining files
if [ "$COUNT" -gt 0 ] && [ "$PACKET" -ge "$START_PACKET" ]; then
    printf -v NUM "%03d" "$PACKET"
    zip "${OUTPUT_DIR}/${PREFIX}_${NUM}.zip" \
        "${FILES[@]/#/${INPUT_DIR}/}"
fi
