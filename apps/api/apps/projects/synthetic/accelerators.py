from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal

AcceleratorMode = Literal["auto", "cpu", "gpu"]


@dataclass(frozen=True)
class RandomStreams:
    backend: str
    used_gpu: bool
    seed: int
    time_roll: list[float]
    scenario_roll: list[float]
    app_roll: list[float]
    endpoint_roll: list[float]
    consumer_roll: list[float]
    environment_roll: list[float]
    status_roll: list[float]
    latency_roll: list[float]
    tail_roll: list[float]
    payload_roll: list[float]
    log_roll: list[float]
    span_roll: list[float]


class RandomPlanner:
    """Generate numeric random streams, preferring GPU batch generation when available.

    The telemetry engine is mostly text and JSON synthesis, but high-volume runs
    still need millions of random numbers for timestamps, weighted choices,
    statuses, latency, log sampling, and span fan-out. This planner centralizes
    that work and can move it to CUDA through optional CuPy or Torch installs.
    """

    STREAM_COUNT = 12

    def __init__(self, mode: AcceleratorMode = "auto") -> None:
        if mode not in {"auto", "cpu", "gpu"}:
            raise ValueError("accelerator mode must be one of: auto, cpu, gpu")
        self.mode = mode

    def plan(self, *, count: int, seed: int) -> RandomStreams:
        safe_count = max(0, int(count))
        if safe_count == 0:
            return self._empty(seed, "cpu-random", used_gpu=False)

        if self.mode in {"auto", "gpu"}:
            for maker in (self._cupy_plan, self._torch_plan):
                try:
                    streams = maker(safe_count, seed)
                except Exception:
                    streams = None
                if streams is not None:
                    return streams
            if self.mode == "gpu":
                raise RuntimeError("GPU accelerator requested, but neither CuPy nor Torch CUDA is available")

        return self._cpu_plan(safe_count, seed)

    def _empty(self, seed: int, backend: str, *, used_gpu: bool) -> RandomStreams:
        return RandomStreams(
            backend=backend,
            used_gpu=used_gpu,
            seed=seed,
            time_roll=[],
            scenario_roll=[],
            app_roll=[],
            endpoint_roll=[],
            consumer_roll=[],
            environment_roll=[],
            status_roll=[],
            latency_roll=[],
            tail_roll=[],
            payload_roll=[],
            log_roll=[],
            span_roll=[],
        )

    def _from_matrix(self, *, matrix: list[list[float]], seed: int, backend: str, used_gpu: bool) -> RandomStreams:
        return RandomStreams(
            backend=backend,
            used_gpu=used_gpu,
            seed=seed,
            time_roll=matrix[0],
            scenario_roll=matrix[1],
            app_roll=matrix[2],
            endpoint_roll=matrix[3],
            consumer_roll=matrix[4],
            environment_roll=matrix[5],
            status_roll=matrix[6],
            latency_roll=matrix[7],
            tail_roll=matrix[8],
            payload_roll=matrix[9],
            log_roll=matrix[10],
            span_roll=matrix[11],
        )

    def _cpu_plan(self, count: int, seed: int) -> RandomStreams:
        rng = random.Random(seed)
        matrix = [[rng.random() for _ in range(count)] for _ in range(self.STREAM_COUNT)]
        return self._from_matrix(matrix=matrix, seed=seed, backend="cpu-random", used_gpu=False)

    def _cupy_plan(self, count: int, seed: int) -> RandomStreams | None:
        import cupy  # type: ignore[import-not-found]

        device_count = int(cupy.cuda.runtime.getDeviceCount())
        if device_count <= 0:
            return None
        rng = cupy.random.default_rng(seed)
        values = rng.random((self.STREAM_COUNT, count), dtype=cupy.float32)
        matrix = values.get().tolist()
        return self._from_matrix(matrix=matrix, seed=seed, backend="cupy-cuda", used_gpu=True)

    def _torch_plan(self, count: int, seed: int) -> RandomStreams | None:
        import torch  # type: ignore[import-not-found]

        if not torch.cuda.is_available():
            return None
        generator = torch.Generator(device="cuda")
        generator.manual_seed(seed)
        values = torch.rand((self.STREAM_COUNT, count), generator=generator, device="cuda")
        matrix = values.cpu().tolist()
        return self._from_matrix(matrix=matrix, seed=seed, backend="torch-cuda", used_gpu=True)
