# Scripts Layout

`scripts` is split by responsibility:

- `quality/`: repository checks and formatters for contracts, Python, Go, and
  Rust.
- `contracts/`: contract generation helpers, such as protobuf codegen for Go
  and Python.
- `ops/`: local machine and hardware operation helpers.
- `command/`: standalone Python command CLI project.

Keep new scripts in the narrowest matching layer. Avoid adding new files
directly under `scripts/`.
