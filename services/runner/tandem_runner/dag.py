"""Load pipeline.yaml, validate it into an ordered plan, and run it.

The runner knows nothing about individual stages. Each stage's `fn` is a dotted path
to a pure function in tandem_core. Fallback strategies other than `last_recorded`
resolve to `fallback_<name>` in the same module as the stage fn.
"""

import hashlib
import importlib
import time
import uuid
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from pydantic import BaseModel, JsonValue

from tandem_core.models import (
    BriefWritten,
    BriefWrittenPayload,
    Check,
    CheckRaised,
    EndpointLocated,
    EndpointLocatedPayload,
    EventBase,
    Overlap,
    OverlapFound,
    Project,
    Provenance,
    RecordExtracted,
    ReferenceResult,
    ReferenceTested,
    RunCompleted,
    RunCompletedPayload,
    RunStarted,
    RunStartedPayload,
    Severity,
    StageCompleted,
    StageCompletedPayload,
    StageStarted,
    StageStartedPayload,
)
from tandem_core.stage import (
    EffectRequest,
    RunParams,
    Source,
    StageContext,
    StageFn,
    StageOutput,
    canonical_json,
)
from tandem_runner.cache import EffectCache
from tandem_runner.config import PipelineConfig, StageSpec
from tandem_runner.effects import EXECUTORS, Executor
from tandem_runner.events import EventLog

LAST_RECORDED = "last_recorded"
MAX_EFFECT_ROUNDS = 20

EVENT_FOR_EMIT: Mapping[type[BaseModel], type[EventBase]] = {
    Project: RecordExtracted,
    Check: CheckRaised,
    Overlap: OverlapFound,
    ReferenceResult: ReferenceTested,
    EndpointLocatedPayload: EndpointLocated,
    BriefWrittenPayload: BriefWritten,
}

Resolver = Callable[[str], object]


class PipelineError(Exception):
    """pipeline.yaml is invalid; the message lists every problem found."""


class StageFailure(Exception):
    """A stage could not produce output (error or timeout)."""


class StageTimeout(StageFailure):
    pass


def import_dotted(path: str) -> object:
    module_name, _, attr = path.rpartition(".")
    if not module_name:
        raise LookupError(f"{path!r} is not a dotted path")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise LookupError(f"cannot import {module_name!r}: {exc}") from exc
    if not hasattr(module, attr):
        raise LookupError(f"{module_name!r} has no attribute {attr!r}")
    return getattr(module, attr)


# --- Plan -------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedStage:
    spec: StageSpec
    fn: StageFn
    fallbacks: tuple[tuple[str, StageFn | None], ...]  # None means last_recorded


def plan(
    config: PipelineConfig,
    *,
    resolve: Resolver = import_dotted,
    executors: Mapping[str, Executor] = EXECUTORS,
) -> tuple[PlannedStage, ...]:
    """Validate the config and return its stages in a stable topological order."""
    errors: list[str] = []
    stages = config.stages

    utilities = set(config.utilities)
    for sid, source in config.sources.items():
        if source.utility is not None and source.utility not in utilities:
            errors.append(f"source {sid!r}: unknown utility {source.utility!r}")
    for a, b in config.pairs:
        for u in (a, b):
            if u not in utilities:
                errors.append(f"pair [{a}, {b}]: unknown utility {u!r}")

    producer: dict[str, str] = {}  # data name -> stage id ("" for sources)
    for sid in config.sources:
        producer[sid] = ""
    seen_ids: set[str] = set()
    for s in stages:
        if s.id in seen_ids:
            errors.append(f"duplicate stage id {s.id!r}")
        seen_ids.add(s.id)
        if s.out is not None:
            if s.out in producer:
                other = producer[s.out] or "a source"
                errors.append(f"stage {s.id!r}: output {s.out!r} is also produced by {other}")
            else:
                producer[s.out] = s.id

    fns: dict[str, StageFn] = {}
    fallbacks: dict[str, tuple[tuple[str, StageFn | None], ...]] = {}
    for s in stages:
        for name in s.inputs:
            if name not in producer:
                errors.append(f"stage {s.id!r}: unknown input {name!r}")
        for kind in s.effects:
            if kind not in executors:
                errors.append(f"stage {s.id!r}: no executor for effect {kind!r}")
        fn = _resolve_fn(s.fn, resolve, f"stage {s.id!r}: fn", errors)
        if fn is not None:
            fns[s.id] = fn
        chain: list[tuple[str, StageFn | None]] = []
        for name in s.fallback:
            if name == LAST_RECORDED:
                chain.append((name, None))
                continue
            path = f"{s.fn.rpartition('.')[0]}.fallback_{name}"
            fb = _resolve_fn(path, resolve, f"stage {s.id!r}: fallback {name!r}", errors)
            if fb is not None:
                chain.append((name, fb))
        fallbacks[s.id] = tuple(chain)
        if s.gate is not None and s.out is None:
            errors.append(f"stage {s.id!r}: a gate needs an `out`")

    order = _toposort(stages, producer, errors)
    if errors:
        raise PipelineError("invalid pipeline:\n  " + "\n  ".join(errors))
    return tuple(PlannedStage(s, fns[s.id], fallbacks[s.id]) for s in order)


def _resolve_fn(path: str, resolve: Resolver, what: str, errors: list[str]) -> StageFn | None:
    try:
        obj = resolve(path)
    except LookupError as exc:
        errors.append(f"{what} {path!r} not found ({exc})")
        return None
    if not callable(obj):
        errors.append(f"{what} {path!r} is not callable")
        return None
    return cast(StageFn, obj)


def _toposort(
    stages: tuple[StageSpec, ...], producer: Mapping[str, str], errors: list[str]
) -> list[StageSpec]:
    """Kahn's algorithm, always taking the earliest-declared ready stage (stable order)."""
    index = {s.id: i for i, s in enumerate(stages)}
    deps = {s.id: {producer[n] for n in s.inputs if producer.get(n)} - {s.id} for s in stages}
    for s in stages:
        if s.out is not None and s.out in s.inputs:
            errors.append(f"stage {s.id!r} consumes its own output {s.out!r}")
    done: list[StageSpec] = []
    remaining = dict(deps)
    while remaining:
        ready = sorted((sid for sid, d in remaining.items() if not d), key=index.__getitem__)
        if not ready:
            cycle = ", ".join(sorted(remaining, key=index.__getitem__))
            errors.append(f"cycle among stages: {cycle}")
            break
        sid = ready[0]
        done.append(stages[index[sid]])
        del remaining[sid]
        for d in remaining.values():
            d.discard(sid)
    return done


# --- Run --------------------------------------------------------------------------


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str


class Runner:
    def __init__(
        self,
        config: PipelineConfig,
        log: EventLog,
        cache: EffectCache,
        *,
        root: Path,
        llm_model: str,
        resolve: Resolver = import_dotted,
        executors: Mapping[str, Executor] = EXECUTORS,
    ) -> None:
        self.config = config
        self.log = log
        self.cache = cache
        self.root = root
        self.llm_model = llm_model
        self.executors = executors
        self.stages = plan(config, resolve=resolve, executors=executors)

    def run(self, run_id: str | None = None) -> RunResult:
        run_id = run_id or uuid.uuid4().hex
        cfg = self.config
        input_hashes = self._hash_sources()
        self.log.start_run(run_id, cfg.config_hash, cfg.run.today.isoformat())
        self.log.append(
            run_id,
            RunStarted,
            RunStartedPayload(
                config_hash=cfg.config_hash, input_hashes=input_hashes, today=cfg.run.today
            ),
        )
        params = RunParams(
            today=cfg.run.today,
            distance_threshold_mi=cfg.run.distance_threshold_mi,
            georgia_sponsors=cfg.run.georgia_sponsors,
            utilities=cfg.utilities,
            pairs=cfg.pairs,
            llm_model=self.llm_model,
        )
        data: dict[str, Any] = {
            sid: Source(id=sid, **spec.model_dump()) for sid, spec in cfg.sources.items()
        }
        outputs: dict[str, BaseModel] = {}
        status = "completed"
        for stage in self.stages:
            output = self._run_stage(run_id, stage, params, data)
            if output is None:
                status = "failed"
                break
            if stage.spec.out is not None:
                data[stage.spec.out] = output.value
                outputs[stage.spec.out] = output.value

        totals: dict[str, int] = {}
        for event in self.log.events(run_id):
            totals[event.type] = totals.get(event.type, 0) + 1
        dumped = {name: value.model_dump(mode="json") for name, value in outputs.items()}
        output_hash = hashlib.sha256(canonical_json(dumped).encode()).hexdigest()
        self.log.append(
            run_id,
            RunCompleted,
            RunCompletedPayload(
                status=status, totals=totals, output_hashes={"stage_outputs": output_hash}
            ),
        )
        self.log.finish_run(run_id, status)
        return RunResult(run_id, status)

    def _hash_sources(self) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for sid, spec in self.config.sources.items():
            path = self.root / spec.path
            if not path.is_file():
                raise PipelineError(f"source {sid!r}: file not found: {path}")
            hashes[sid] = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes

    def _run_stage(
        self, run_id: str, stage: PlannedStage, params: RunParams, data: Mapping[str, Any]
    ) -> StageOutput | None:
        """Run one stage and emit its events. Returns None if the run must stop."""
        spec = stage.spec
        self.log.append(run_id, StageStarted, StageStartedPayload(stage_id=spec.id))
        started = time.monotonic()
        ctx = StageContext(stage_id=spec.id, run=params, params=spec.params)
        inputs = MappingProxyType({name: data[name] for name in spec.inputs})
        deadline = None if spec.timeout_s is None else started + spec.timeout_s

        used_fallback: str | None = None
        output: StageOutput | None
        try:
            output = self._execute(spec, stage.fn, ctx, inputs, deadline)
            self._check_output(spec, output)
        except StageFailure as exc:
            timed_out = isinstance(exc, StageTimeout)
            self._raise_check(
                run_id,
                spec,
                "RUN-TIMEOUT" if timed_out else "RUN-STAGE-ERROR",
                "warn" if stage.fallbacks else "error",
                str(exc),
            )
            output, used_fallback = self._fallback(run_id, stage, ctx, inputs)
            if output is None:
                self._raise_check(
                    run_id, spec, "RUN-STAGE-FAILED", "error", "no fallback produced output"
                )
                return None

        for emit in output.emits:
            self.log.append(run_id, EVENT_FOR_EMIT[type(emit)], emit, fixture=output.fixture)

        gate_error = self._gate_error(spec, output)
        self.log.append(
            run_id,
            StageCompleted,
            StageCompletedPayload(
                stage_id=spec.id,
                counts=output.counts,
                duration_ms=round((time.monotonic() - started) * 1000),
                used_fallback=used_fallback,
            ),
        )
        self.log.record_stage_output(run_id, spec.id, output, used_fallback)
        if gate_error is not None:
            self._raise_check(run_id, spec, "RUN-GATE", "error", gate_error)
            return None
        return output

    def _execute(
        self,
        spec: StageSpec,
        fn: StageFn,
        ctx: StageContext,
        inputs: Mapping[str, Any],
        deadline: float | None,
    ) -> StageOutput:
        """Call fn, executing and caching requested effects, until it returns output.

        Stage fns and effect executors run on worker threads so a deadline can be
        enforced; the cache is only touched from this thread.
        """
        results: dict[str, JsonValue] = {}
        pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix=f"stage-{spec.id}")
        try:
            for _ in range(MAX_EFFECT_ROUNDS):
                answer = _wait(
                    pool.submit(fn, ctx, inputs, MappingProxyType(dict(results))), deadline
                )
                if isinstance(answer, StageOutput):
                    return answer
                if not answer.requests:
                    raise StageFailure(f"{spec.fn} returned NeedEffects with no requests")
                pending: list[tuple[EffectRequest, Future[JsonValue]]] = []
                for request in answer.requests:
                    if request.kind not in spec.effects:
                        raise StageFailure(
                            f"{spec.fn} requested effect {request.kind!r}, "
                            f"not declared in pipeline.yaml"
                        )
                    found, value = self.cache.get(request)
                    if found:
                        results[request.key] = value
                    else:
                        executor = self.executors[request.kind]
                        pending.append((request, pool.submit(executor, request)))
                for request, future in pending:
                    value = _wait(future, deadline)
                    self.cache.put(request, value)
                    results[request.key] = value
            raise StageFailure(f"{spec.fn} still needed effects after {MAX_EFFECT_ROUNDS} rounds")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

    def _check_output(self, spec: StageSpec, output: object) -> None:
        if not isinstance(output, StageOutput):
            raise StageFailure(f"{spec.fn} returned {type(output).__name__}, not StageOutput")
        if spec.out is not None and not isinstance(output.value, BaseModel):
            raise StageFailure(f"{spec.fn} returned no value for output {spec.out!r}")
        for emit in output.emits:
            if type(emit) not in EVENT_FOR_EMIT:
                raise StageFailure(f"{spec.fn} emitted unsupported {type(emit).__name__}")

    def _fallback(
        self,
        run_id: str,
        stage: PlannedStage,
        ctx: StageContext,
        inputs: Mapping[str, Any],
    ) -> tuple[StageOutput | None, str | None]:
        spec = stage.spec
        for name, fn in stage.fallbacks:
            if fn is None:
                recorded = self.log.last_stage_output(spec.id, exclude_run=run_id)
                if recorded is not None:
                    return recorded, name
                reason = "no recorded output from an earlier run"
            else:
                try:
                    output = self._execute(spec, fn, ctx, inputs, deadline=None)
                    self._check_output(spec, output)
                    return output, name
                except StageFailure as exc:
                    reason = str(exc)
            self._raise_check(
                run_id,
                spec,
                "RUN-FALLBACK-UNAVAILABLE",
                "warn",
                f"fallback {name!r} unavailable ({reason}); trying the next strategy",
            )
        return None, None

    def _gate_error(self, spec: StageSpec, output: StageOutput) -> str | None:
        gate = spec.gate
        if gate is None:
            return None
        if gate.metric not in output.counts:
            return f"gate metric {gate.metric!r} missing from stage counts"
        actual = output.counts[gate.metric]
        if isinstance(gate.equals, int):
            expected = gate.equals
        elif gate.equals in output.counts:
            expected = output.counts[gate.equals]
        else:
            return f"gate metric {gate.equals!r} missing from stage counts"
        if actual != expected:
            return f"gate failed: {gate.metric}={actual}, expected {gate.equals}={expected}"
        return None

    def _raise_check(
        self, run_id: str, spec: StageSpec, rule_id: str, severity: Severity, message: str
    ) -> None:
        check = Check(
            rule_id=rule_id,
            severity=severity,
            subject=spec.id,
            message=message,
            provenance=Provenance(
                file="pipeline.yaml", page=None, locator=f"stage {spec.id}", stage=spec.id
            ),
        )
        self.log.append(run_id, CheckRaised, check)


def _wait[T](future: Future[T], deadline: float | None) -> T:
    try:
        if deadline is None:
            return future.result()
        return future.result(timeout=max(0.0, deadline - time.monotonic()))
    except TimeoutError as exc:
        raise StageTimeout("stage exceeded its timeout_s") from exc
    except StageFailure:
        raise
    except Exception as exc:
        raise StageFailure(f"{type(exc).__name__}: {exc}") from exc
