# tandem_runner

The imperative shell and the only place in Tandem with I/O. It reads `pipeline.yaml`, builds and executes the stage DAG, runs the effects that stages request (PDF and xlsx reads, Overpass, Nominatim, Gemini), caches every effect result by request hash in SQLite, applies per-stage timeouts and fallbacks, and appends each step to the event log. Adding a stage means editing `pipeline.yaml` and adding a pure function in `tandem_core`, never editing the runner.
