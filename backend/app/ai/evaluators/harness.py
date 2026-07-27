"""Isolated AI evaluation scaffolding (not used in production inference)."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class EvaluationSample:
    """Golden dataset sample for offline evaluation.

    Attributes:
        id: Sample identifier.
        prompt_version: Prompt version under test.
        question: User question.
        contexts: Retrieved contexts.
        answer: Model answer.
        ground_truth: Expected answer.
    """

    id: str
    prompt_version: str
    question: str
    contexts: List[str]
    answer: str
    ground_truth: str


@dataclass
class EvaluationMetrics:
    """Tracked evaluation metrics.

    Attributes:
        faithfulness: Faithfulness score.
        context_precision: Context precision score.
        context_recall: Context recall score.
        answer_relevancy: Answer relevancy score.
        latency_ms: Latency in milliseconds.
        token_usage: Total tokens used.
        cost_usd: Estimated cost.
        hallucination_rate: Hallucination rate.
    """

    faithfulness: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0
    answer_relevancy: float = 0.0
    latency_ms: float = 0.0
    token_usage: int = 0
    cost_usd: float = 0.0
    hallucination_rate: float = 0.0


@dataclass
class EvaluationRun:
    """Offline evaluation run metadata.

    Attributes:
        evaluation_version: Evaluation framework version.
        dataset_version: Dataset version.
        prompt_version: Prompt version.
        metrics: Aggregated metrics.
        samples: Evaluated samples.
        created_at: Run timestamp.
        notes: Optional notes.
    """

    evaluation_version: str
    dataset_version: str
    prompt_version: str
    metrics: EvaluationMetrics
    samples: List[EvaluationSample] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None


class EvaluationHarness:
    """Placeholder harness compatible with RAGAS/DeepEval integrations.

    This module intentionally stays isolated from production inference.
    """

    EVALUATION_VERSION = "eval-v1"
    DATASET_VERSION = "golden-v1"

    def score_placeholder(self, sample: EvaluationSample) -> EvaluationMetrics:
        """Compute placeholder overlap-based metrics.

        Args:
            sample: Evaluation sample.

        Returns:
            Heuristic EvaluationMetrics for local smoke tests.
        """
        answer_terms = set(sample.answer.lower().split())
        truth_terms = set(sample.ground_truth.lower().split())
        overlap = len(answer_terms & truth_terms)
        denom = max(len(truth_terms), 1)
        relevancy = overlap / denom
        return EvaluationMetrics(
            faithfulness=relevancy,
            context_precision=relevancy,
            context_recall=relevancy,
            answer_relevancy=relevancy,
            hallucination_rate=max(0.0, 1.0 - relevancy),
        )

    def run(self, samples: List[EvaluationSample], prompt_version: str) -> EvaluationRun:
        """Run offline evaluation over a golden dataset.

        Args:
            samples: Golden samples.
            prompt_version: Prompt version identifier.

        Returns:
            Aggregated EvaluationRun.
        """
        metrics_list = [self.score_placeholder(sample) for sample in samples]
        if not metrics_list:
            return EvaluationRun(
                evaluation_version=self.EVALUATION_VERSION,
                dataset_version=self.DATASET_VERSION,
                prompt_version=prompt_version,
                metrics=EvaluationMetrics(),
                samples=[],
            )
        count = len(metrics_list)
        aggregated = EvaluationMetrics(
            faithfulness=sum(m.faithfulness for m in metrics_list) / count,
            context_precision=sum(m.context_precision for m in metrics_list) / count,
            context_recall=sum(m.context_recall for m in metrics_list) / count,
            answer_relevancy=sum(m.answer_relevancy for m in metrics_list) / count,
            hallucination_rate=sum(m.hallucination_rate for m in metrics_list) / count,
        )
        return EvaluationRun(
            evaluation_version=self.EVALUATION_VERSION,
            dataset_version=self.DATASET_VERSION,
            prompt_version=prompt_version,
            metrics=aggregated,
            samples=samples,
        )

    def to_dict(self, run: EvaluationRun) -> Dict[str, Any]:
        """Serialize an evaluation run.

        Args:
            run: Evaluation run.

        Returns:
            JSON-serializable dictionary.
        """
        return {
            "evaluation_version": run.evaluation_version,
            "dataset_version": run.dataset_version,
            "prompt_version": run.prompt_version,
            "created_at": run.created_at.isoformat(),
            "metrics": run.metrics.__dict__,
            "sample_count": len(run.samples),
            "notes": run.notes,
        }
