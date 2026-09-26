# tandem_core

The pure functional core of Tandem: frozen Pydantic records, the Dominion and Georgia parsers, endpoint splitting, location choice, geometry, validation rules, overlap detection, ranking, cost estimates, briefs prompts, run diffs, and the Python event reducer. Nothing in this package reads files, calls the network, uses randomness, or looks at the clock; "today" and every external result are passed in by the runner. Tests live in `tests/` and run with `make test`.
