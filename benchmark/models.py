"""Data models for the AI IDE Token Benchmark."""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Turn:
    """A single prompt-response pair within a session."""

    turn_number: int
    role: str  # "task_description" | "clarifying_question" | "implementation" | "verification"
    prompt: str

    def to_dict(self) -> dict:
        return {
            "turn_number": self.turn_number,
            "role": self.role,
            "prompt": self.prompt,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Turn":
        return cls(
            turn_number=data["turn_number"],
            role=data["role"],
            prompt=data["prompt"],
        )


@dataclass
class Session:
    """An independent coding task conversation consisting of multiple turns."""

    session_id: int
    issue_number: int
    title: str
    task_type: str  # "single-file" | "cross-file"
    files: List[str]
    turns: List[Turn]

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "issue_number": self.issue_number,
            "title": self.title,
            "task_type": self.task_type,
            "files": list(self.files),
            "turns": [t.to_dict() for t in self.turns],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            session_id=data["session_id"],
            issue_number=data["issue_number"],
            title=data["title"],
            task_type=data["task_type"],
            files=list(data["files"]),
            turns=[Turn.from_dict(t) for t in data["turns"]],
        )


@dataclass
class SessionScript:
    """A structured document containing all sessions and their ordered prompts."""

    generated_at: str
    repo_path: str
    sessions: List[Session]

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "repo_path": self.repo_path,
            "sessions": [s.to_dict() for s in self.sessions],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionScript":
        return cls(
            generated_at=data["generated_at"],
            repo_path=data["repo_path"],
            sessions=[Session.from_dict(s) for s in data["sessions"]],
        )


@dataclass
class TokenCount:
    """Token usage counts for a turn, session, or run."""

    input_tokens: int
    output_tokens: int
    total_tokens: int

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TokenCount":
        return cls(
            input_tokens=data["input_tokens"],
            output_tokens=data["output_tokens"],
            total_tokens=data["total_tokens"],
        )


@dataclass
class TurnRecord:
    """Recorded token data for a single turn."""

    session_id: int
    turn_number: int
    tokens: TokenCount
    mcp_tools_called: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "turn_number": self.turn_number,
            "tokens": self.tokens.to_dict(),
            "mcp_tools_called": list(self.mcp_tools_called),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TurnRecord":
        return cls(
            session_id=data["session_id"],
            turn_number=data["turn_number"],
            tokens=TokenCount.from_dict(data["tokens"]),
            mcp_tools_called=list(data.get("mcp_tools_called", [])),
        )


@dataclass
class SessionRecord:
    """Recorded token data for a complete session."""

    session_id: int
    task_type: str
    turns: List[TurnRecord]
    aggregate: TokenCount

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "task_type": self.task_type,
            "turns": [t.to_dict() for t in self.turns],
            "aggregate": self.aggregate.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionRecord":
        return cls(
            session_id=data["session_id"],
            task_type=data["task_type"],
            turns=[TurnRecord.from_dict(t) for t in data["turns"]],
            aggregate=TokenCount.from_dict(data["aggregate"]),
        )


@dataclass
class RunRecord:
    """Recorded token data for a complete benchmark run."""

    run_type: str  # "baseline" | "treatment"
    timestamp: str
    prompt_file: str
    sessions: List[SessionRecord]
    aggregate: TokenCount

    def to_dict(self) -> dict:
        return {
            "run_type": self.run_type,
            "timestamp": self.timestamp,
            "prompt_file": self.prompt_file,
            "sessions": [s.to_dict() for s in self.sessions],
            "aggregate": self.aggregate.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RunRecord":
        return cls(
            run_type=data["run_type"],
            timestamp=data["timestamp"],
            prompt_file=data["prompt_file"],
            sessions=[SessionRecord.from_dict(s) for s in data["sessions"]],
            aggregate=TokenCount.from_dict(data["aggregate"]),
        )


@dataclass
class SessionComparison:
    """Comparison of token usage between baseline and treatment for a session."""

    session_id: int
    task_type: str
    baseline: TokenCount
    treatment: TokenCount
    delta: TokenCount
    reduction_ratio: float  # baseline.total / treatment.total

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "task_type": self.task_type,
            "baseline": self.baseline.to_dict(),
            "treatment": self.treatment.to_dict(),
            "delta": self.delta.to_dict(),
            "reduction_ratio": self.reduction_ratio,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionComparison":
        return cls(
            session_id=data["session_id"],
            task_type=data["task_type"],
            baseline=TokenCount.from_dict(data["baseline"]),
            treatment=TokenCount.from_dict(data["treatment"]),
            delta=TokenCount.from_dict(data["delta"]),
            reduction_ratio=data["reduction_ratio"],
        )


@dataclass
class ComparisonReport:
    """Full comparison report between baseline and treatment runs."""

    timestamp: str
    sessions: List[SessionComparison]
    aggregate_baseline: TokenCount
    aggregate_treatment: TokenCount
    aggregate_delta: TokenCount
    aggregate_reduction_ratio: float
    assessment: str  # "supported" | "partially_supported" | "not_supported"
    assessment_detail: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "sessions": [s.to_dict() for s in self.sessions],
            "aggregate_baseline": self.aggregate_baseline.to_dict(),
            "aggregate_treatment": self.aggregate_treatment.to_dict(),
            "aggregate_delta": self.aggregate_delta.to_dict(),
            "aggregate_reduction_ratio": self.aggregate_reduction_ratio,
            "assessment": self.assessment,
            "assessment_detail": self.assessment_detail,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ComparisonReport":
        return cls(
            timestamp=data["timestamp"],
            sessions=[SessionComparison.from_dict(s) for s in data["sessions"]],
            aggregate_baseline=TokenCount.from_dict(data["aggregate_baseline"]),
            aggregate_treatment=TokenCount.from_dict(data["aggregate_treatment"]),
            aggregate_delta=TokenCount.from_dict(data["aggregate_delta"]),
            aggregate_reduction_ratio=data["aggregate_reduction_ratio"],
            assessment=data["assessment"],
            assessment_detail=data.get("assessment_detail", ""),
        )


# Default mapping from turn role to MCP tool prefix for treatment runs
DEFAULT_PREFIX_MAP: Dict[str, str] = {
    "task_description": "miser-plan",
    "clarifying_question": "miser-ask",
    "implementation": "miser-fix",
    "verification": "miser-ask",
}


@dataclass
class AutomationConfig:
    """Configuration for automated benchmark execution."""

    kiro_path: str = "kiro"
    idle_timeout: int = 30
    turn_timeout: int = 300
    startup_timeout: int = 60
    treatment_prefix_map: Dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_PREFIX_MAP)
    )

    def to_dict(self) -> dict:
        return {
            "kiro_path": self.kiro_path,
            "idle_timeout": self.idle_timeout,
            "turn_timeout": self.turn_timeout,
            "startup_timeout": self.startup_timeout,
            "treatment_prefix_map": dict(self.treatment_prefix_map),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AutomationConfig":
        return cls(
            kiro_path=data.get("kiro_path", "kiro"),
            idle_timeout=data.get("idle_timeout", 30),
            turn_timeout=data.get("turn_timeout", 300),
            startup_timeout=data.get("startup_timeout", 60),
            treatment_prefix_map=data.get(
                "treatment_prefix_map", dict(DEFAULT_PREFIX_MAP)
            ),
        )


@dataclass
class BenchmarkConfig:
    """Configuration for a benchmark run."""

    repo_path: str
    prompt_file: str = "benchmark_output/session_script.json"
    output_dir: str = "benchmark_output"
    output_format: str = "json"  # "json" | "csv"
    proxy_port: int = 8080
    timeout_seconds: int = 120
    automation: AutomationConfig = field(default_factory=AutomationConfig)

    def to_dict(self) -> dict:
        return {
            "repo_path": self.repo_path,
            "prompt_file": self.prompt_file,
            "output_dir": self.output_dir,
            "output_format": self.output_format,
            "proxy_port": self.proxy_port,
            "timeout_seconds": self.timeout_seconds,
            "automation": self.automation.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BenchmarkConfig":
        return cls(
            repo_path=data["repo_path"],
            prompt_file=data.get("prompt_file", "benchmark_output/session_script.json"),
            output_dir=data.get("output_dir", "benchmark_output"),
            output_format=data.get("output_format", "json"),
            proxy_port=data.get("proxy_port", 8080),
            timeout_seconds=data.get("timeout_seconds", 120),
            automation=AutomationConfig.from_dict(data.get("automation", {})),
        )


@dataclass
class WatchResult:
    """Result from watching for response completion."""

    entries: List[dict]
    new_position: int
    timed_out: bool


class BenchmarkError(Exception):
    """Raised when the benchmark must halt due to unrecoverable errors."""

    pass
