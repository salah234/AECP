"""Semantic conflict detection: catches cases where two changes are
individually valid but jointly incoherent.

This is the one piece of AECP's own coordination logic that may itself
call out to a model (to reason about whether two diffs' intents conflict)
rather than being a pure structural check — but the decision of what to
do with that judgment (auto-resolve vs. escalate) still goes through
merge_policy.py's explicit, non-model-driven rules.

IMPLEMENTATION NOTE — this is a heuristic placeholder, not the
model-backed check the module docstring above describes. Adding a live
LLM dependency (an `anthropic`/`openai` SDK call from this service) is a
real product and cost decision — what model, what prompt, what latency
budget, what happens on provider outage — that is out of scope for this
fix and has not been made, so no such dependency has been added to
pyproject.toml. Instead, compare() runs a deterministic, explainable
heuristic over each task's TaskNode.description and
definition_of_done.acceptance_criteria: it looks for (a) known antonym
pairs appearing across the two tasks' text, and (b) the same content word
asserted in one task's text and negated in the other's. This will miss
real semantic contradictions that don't share vocabulary (a false
negative) and is not a substitute for the real model-backed version this
module's docstring envisions — but per this fix's instructions, silently
introducing a model dependency without that product decision would be
worse than a documented, narrower heuristic. compare() defaults to
jointly_coherent=True whenever it finds no concrete, explainable
contradiction signal, matching this codebase's existing "don't fabricate
a finding you can't support" convention (see conflict.py's
_detect_textual and state/app/repository.py's get_decisions_for_module).

__init__ takes taskgraph_client in addition to state_client. The
originally scaffolded signature was `__init__(self, state_client)`, but
the heuristic above needs each task's TaskNode (description, acceptance
criteria) to compare, which only TaskGraph — not State — exposes; this
mirrors ConflictDetector's own reliance on a taskgraph_client for its
ownership check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app import ownership
from app.taskgraph.v1 import taskgraph_pb2


@dataclass
class SemanticDiffResult:
    jointly_coherent: bool
    explanation: str


_WORD_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
        "is", "are", "be", "this", "that", "it", "as", "by", "at", "from",
        "must", "should", "will", "can", "task", "when", "if", "its", "than",
        "into", "all", "any", "via", "per",
    }
)

# Tokens that negate whatever content word immediately follows them.
_NEGATION_TOKENS = frozenset(
    {"not", "never", "no", "cannot", "without", "disallow", "disallows", "forbid", "forbids"}
)

# Known opposing-term pairs. Order within a pair doesn't matter; either
# word may appear in either task's text.
_ANTONYM_PAIRS: tuple[tuple[str, str], ...] = (
    ("synchronous", "asynchronous"),
    ("sync", "async"),
    ("enable", "disable"),
    ("enabled", "disabled"),
    ("allow", "forbid"),
    ("allow", "deny"),
    ("allowed", "forbidden"),
    ("public", "private"),
    ("required", "optional"),
    ("mandatory", "optional"),
    ("immutable", "mutable"),
    ("stateless", "stateful"),
    ("blocking", "nonblocking"),
    ("idempotent", "nonidempotent"),
    ("increase", "decrease"),
)


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


_NEGATION_LOOKAHEAD = 3


def _asserted_and_negated_words(text: str) -> tuple[set[str], set[str]]:
    """Split a text's content words into those asserted plainly and
    those negated by a nearby negation token (e.g. "must not be
    idempotent" negates "idempotent", not the stopword "be" sitting
    between "not" and it).

    A negation token opens a lookahead window of up to
    _NEGATION_LOOKAHEAD tokens; the first content word found inside that
    window is treated as negated, and the window then closes. Stopwords
    inside the window (e.g. "be", "the") consume a slot but don't reset
    or extend it, so negation doesn't leak arbitrarily far down the
    sentence.
    """
    tokens = _tokenize(text)
    asserted: set[str] = set()
    negated: set[str] = set()

    negation_window = 0
    for token in tokens:
        if token in _NEGATION_TOKENS:
            negation_window = _NEGATION_LOOKAHEAD
            continue

        if token in _STOPWORDS or len(token) <= 2:
            if negation_window > 0:
                negation_window -= 1
            continue

        if negation_window > 0:
            negated.add(token)
            negation_window = 0
        else:
            asserted.add(token)

    return asserted, negated


def _negation_contradiction(text_a: str, text_b: str) -> str | None:
    """Return a content word that one text asserts and the other negates,
    or None if no such word exists.
    """
    asserted_a, negated_a = _asserted_and_negated_words(text_a)
    asserted_b, negated_b = _asserted_and_negated_words(text_b)

    hits = (asserted_a & negated_b) | (negated_a & asserted_b)
    if not hits:
        return None

    return sorted(hits)[0]


def _antonym_contradiction(text_a: str, text_b: str) -> tuple[str, str] | None:
    """Return the first known antonym pair with one word in each text, or
    None if no such pair exists.
    """
    words_a = set(_tokenize(text_a))
    words_b = set(_tokenize(text_b))

    for word_1, word_2 in _ANTONYM_PAIRS:
        if (word_1 in words_a and word_2 in words_b) or (
            word_2 in words_a and word_1 in words_b
        ):
            return word_1, word_2

    return None


def _combined_text(node: taskgraph_pb2.TaskNode) -> str:
    return " ".join([node.description, *node.definition_of_done.acceptance_criteria])


class SemanticDiffer:
    def __init__(self, state_client, taskgraph_client) -> None:
        self.state_client = state_client
        self.taskgraph_client = taskgraph_client

    async def compare(self, tenant_id: str, task_id_a: str, task_id_b: str) -> SemanticDiffResult:
        """Determine whether task_id_a's and task_id_b's changes are
        jointly coherent, using each task's description/acceptance
        criteria plus (best-effort, informational) State Layer ownership
        context. See this module's docstring for why this is a heuristic,
        not the model-backed check the class originally envisioned.
        """
        node_a = await self.taskgraph_client.get_task_node(task_id_a, tenant_id)
        node_b = await self.taskgraph_client.get_task_node(task_id_b, tenant_id)

        if node_a is None or node_b is None:
            missing_id = task_id_a if node_a is None else task_id_b
            return SemanticDiffResult(
                jointly_coherent=True,
                explanation=(
                    f"Cannot compare: task '{missing_id}' was not found in "
                    "TaskGraph. Defaulting to jointly_coherent=True rather "
                    "than fabricating a contradiction with no data to "
                    "support it."
                ),
            )

        text_a = _combined_text(node_a)
        text_b = _combined_text(node_b)

        antonym_hit = _antonym_contradiction(text_a, text_b)
        if antonym_hit is not None:
            word_a, word_b = antonym_hit
            return SemanticDiffResult(
                jointly_coherent=False,
                explanation=(
                    f"Task '{task_id_a}' and task '{task_id_b}' use opposing "
                    f"terms ('{word_a}' vs '{word_b}') in their description "
                    "or acceptance criteria, suggesting they may implement "
                    "contradictory requirements against the same invariant."
                ),
            )

        negation_hit = _negation_contradiction(text_a, text_b)
        if negation_hit is not None:
            return SemanticDiffResult(
                jointly_coherent=False,
                explanation=(
                    f"Task '{task_id_a}' and task '{task_id_b}' disagree on "
                    f"'{negation_hit}': one asserts it, the other negates "
                    "it, in their description or acceptance criteria."
                ),
            )

        context_note = await self._ownership_context_note(tenant_id, node_a, node_b)
        return SemanticDiffResult(
            jointly_coherent=True,
            explanation=(
                "No contradiction signal found between the two tasks' "
                "description and acceptance criteria." + context_note
            ),
        )

    async def _ownership_context_note(
        self,
        tenant_id: str,
        node_a: taskgraph_pb2.TaskNode,
        node_b: taskgraph_pb2.TaskNode,
    ) -> str:
        """Best-effort, informational-only context from the State
        Layer's ownership map for a path shared between the two tasks'
        declared ownership globs.

        This never flips jointly_coherent — proto/state/v1/state.proto
        only exposes GetInterfaceContract by contract_id, and Integration
        has no path-to-contract_id lookup, so there is no way to pull the
        actual interface contract or full decision history for a shared
        path today. A real fix needs a state.proto query keyed on a
        path/module, which is a schema change out of scope here (same
        documented-gap pattern as state/app/repository.py's
        get_decisions_for_module and agents/app/hydration.py's
        documented-empty contract lists). GetOwnership is the one
        path-keyed query State does expose today, so it's used here only
        to surface "who last touched this" as supplementary explanation
        text.
        """
        shared_paths = ownership.shared_literal_paths(
            list(node_a.ownership.path_globs), list(node_b.ownership.path_globs)
        )

        for path in shared_paths:
            record = await self.state_client.get_ownership(tenant_id, path)
            if record is not None and record.last_task_id:
                return (
                    f" (State Layer ownership map: '{path}' was last "
                    f"touched by task '{record.last_task_id}'.)"
                )

        return ""
