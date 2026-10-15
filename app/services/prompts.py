"""Prompt construction for council agents and the moderator."""

import hashlib
import re

from app.llm import ChatMessage
from app.models import Agent, Message

# The moderator must produce exactly these sections, in this order.
REPORT_SECTIONS = (
    "Verdict",
    "Agreed requirements",
    "Open questions",
    "Key risks",
    "Recommended next steps",
)

TURN_RULES = """
RULES FOR THIS DEBATE:
- Stay in character as the {name}. Speak only for yourself, never for other members.
- Keep it under 170 words. Use short paragraphs or a few bullets (markdown is fine).
- No greetings, no restating the topic, no meta commentary about being an AI.
- Be concrete: name specific requirements, numbers, risks or trade-offs.
- When you reference another member's point, name them (e.g. "I agree with the Product Owner that...").
"""

MODERATOR_PROMPT = """You are the neutral Moderator of a software requirements council.
Several specialists have debated a topic. Your job is to synthesise the debate into a
clear, decision-ready report. Do not invent positions nobody took; attribute points to
roles where useful. Write in markdown using exactly these sections:

## Verdict
One or two sentences: the council's overall position.

## Agreed requirements
Bullets of requirements the council converged on, each concrete and testable.

## Open questions
Bullets of unresolved questions, with who needs to answer them.

## Key risks
Bullets of the main risks raised and suggested mitigations.

## Recommended next steps
A short numbered list of the first actions the team should take.
"""


OPENING_INSTRUCTION = (
    "This is the opening round. State your position: the two or three issues that "
    "matter most from your perspective, with concrete questions or proposals."
)
FINAL_INSTRUCTION = (
    "This is the final round. Converge: say what you now agree with, what you still "
    "dispute and why, and your single most important recommendation."
)
REBUTTAL_INSTRUCTION = (
    "Respond directly to specific points other members made. Challenge weak assumptions, "
    "concede good points and refine your proposals. Do not repeat your earlier remarks."
)


def _round_instruction(round_number: int, max_rounds: int) -> str:
    if round_number == 1:
        return OPENING_INSTRUCTION
    if round_number == max_rounds:
        return FINAL_INSTRUCTION
    return REBUTTAL_INSTRUCTION


def prompt_version(agents: list[Agent]) -> str:
    """Short hash of every prompt text a debate with these agents uses.

    Stored on each debate so outputs and eval results can be tied to the exact prompts.
    """
    parts = [
        TURN_RULES,
        MODERATOR_PROMPT,
        OPENING_INSTRUCTION,
        REBUTTAL_INSTRUCTION,
        FINAL_INSTRUCTION,
    ]
    parts += [f"{a.name}\n{a.system_prompt}" for a in sorted(agents, key=lambda a: a.name)]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:12]


_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


def missing_report_sections(report: str) -> list[str]:
    """Required sections that are absent or empty in a moderator report."""
    bodies: dict[str, str] = {}
    current = None
    for line in report.splitlines():
        heading = _HEADING.match(line.strip())
        if heading:
            current = heading.group(1).strip().lower()
            bodies.setdefault(current, "")
        elif current is not None:
            bodies[current] += line.strip()
    return [s for s in REPORT_SECTIONS if not bodies.get(s.lower())]


def format_transcript(messages: list[Message]) -> str:
    if not messages:
        return "(No one has spoken yet.)"
    lines: list[str] = []
    current_round = None
    for m in messages:
        if m.round_number != current_round:
            current_round = m.round_number
            lines.append(f"\n### Round {current_round}")
        lines.append(f"**{m.agent.name} ({m.agent.role}):** {m.content.strip()}")
    return "\n".join(lines).strip()


def _roster(agents: list[Agent]) -> str:
    return ", ".join(f"{a.name} ({a.role})" for a in agents)


def build_agent_turn(
    *,
    agent: Agent,
    topic: str,
    council: list[Agent],
    transcript: list[Message],
    round_number: int,
    max_rounds: int,
) -> list[ChatMessage]:
    system = agent.system_prompt.strip() + "\n" + TURN_RULES.format(name=agent.name)
    user = (
        f"TOPIC UNDER DEBATE:\n{topic}\n\n"
        f"COUNCIL MEMBERS: {_roster(council)}\n\n"
        f"TRANSCRIPT SO FAR:\n{format_transcript(transcript)}\n\n"
        f"It is now round {round_number} of {max_rounds}. Your turn, {agent.name}. "
        f"{_round_instruction(round_number, max_rounds)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_moderator_turn(
    *, topic: str, council: list[Agent], transcript: list[Message]
) -> list[ChatMessage]:
    user = (
        f"TOPIC:\n{topic}\n\n"
        f"COUNCIL MEMBERS: {_roster(council)}\n\n"
        f"FULL TRANSCRIPT:\n{format_transcript(transcript)}\n\n"
        "Write the council report now."
    )
    return [{"role": "system", "content": MODERATOR_PROMPT}, {"role": "user", "content": user}]
