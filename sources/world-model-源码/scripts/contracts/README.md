# Contract Scripts

This directory contains scripts that generate language-specific contract code
from `contracts/proto`.

- `generate-contracts-go.sh`: regenerates checked-in Go protobuf code under
  `contracts/gen/go`.
- `generate-contracts-python.sh`: regenerates checked-in Python protobuf code
  under `contracts/gen/python`.

Validation stays in `scripts/quality/check-contracts.sh`; that check calls these
generators and fails if generated files drift.
