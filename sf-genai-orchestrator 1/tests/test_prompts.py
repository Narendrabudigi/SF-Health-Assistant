"""Guards the prompt files. Each rule that keeps a report limited to the information provided is checked as a phrase of the prompt,
so deleting one by accident fails a test. The prompts are the instructions the model works from; the tests of what the program does
with the model's answer are in test_checks.py and test_reports.py."""
import json
from importlib import resources
from pathlib import Path

import pytest
from sf_orchestrator.reports import load_healthy_prompt, load_setup_prompt, load_system_prompt
from sf_orchestrator.schemas import NUMBERS_ASKED_FOR, BrdDraft, MetricInsight


# ───────────────────────── custom standards leave the industry prompts untouched ─────────────────────────


def test_the_industry_prompts_are_untouched():
    assert "the industry standard" in load_system_prompt().text and "Which standard is used" not in load_system_prompt().text


# ───────────────────────── data workstreams ─────────────────────────


@pytest.mark.parametrize(
    "phrase",
    [
        'has `kind` "data" and an empty `fixesFactors`',
        "Never list a factor that a workstream does not address.",
        '"kind": "factor" | "data"',
    ],
)
def test_the_prompt_keeps_the_data_workstream_rules(phrase):
    assert phrase in load_system_prompt().text


# ───────────────────────── the glossary instruction ─────────────────────────


PROMPTS = ["system", "healthy", "setup"]


def text_of(name: str) -> str:
    return resources.files("sf_orchestrator").joinpath("prompts", f"{name}.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", PROMPTS)
def test_every_prompt_says_to_use_the_glossary_and_never_to_guess_an_abbreviation(name):
    t = text_of(name)
    assert "`<glossary>` block gives a plain-words label for a name, use that label exactly" in t
    assert "never guess what an abbreviation stands for" in t
    assert "Keep an abbreviation you are not sure of as written" in t


# ───────────────────────── the healthy summary prompt ─────────────────────────


# ───────────────────────── the prompts ─────────────────────────


@pytest.mark.parametrize(
    "phrase",
    [
        "a metric whose health state is healthy",
        "Do not give advice, recommendations, plans, risks or next steps.",
        "Write each as a full paragraph of about 100 to 150 words",
        "every sentence must add a fact",
        "Do not repeat a number or restate a sentence to make a paragraph longer.",
        "say that no field is completely empty",
        "The input has no root-cause factors",
        "If it holds `notUsable` instead, the forecast could not be used.",
        "If the text states a range (for example \"30 to 60\")",
        "For a check with 0 failed records, say that it found no problems.",
        '"summary": [string, string]   // one or two paragraphs, each about 100 to 150 words',
    ],
)
def test_the_healthy_prompt_keeps_its_rules(phrase):
    assert phrase in load_healthy_prompt().text


@pytest.mark.parametrize(
    "phrase",
    [
        "If it holds `notUsable` instead, the forecast could not be used.",
        "If `forecast` holds `notUsable`, write one sentence saying that the forecast could not be used and why",
        "as a list or grouped under `mandatoryFieldsMissing` and `otherFieldsMissing`",
        "(including those under `mandatoryFieldsMissing` or `otherFieldsMissing`)",
    ],
)
def test_the_diagnosis_prompt_knows_about_unusable_forecasts_and_grouped_missing_fields(phrase):
    assert phrase in load_system_prompt().text


# ───────────────────────── the narrative and the phases ─────────────────────────


@pytest.mark.parametrize(
    "phrase",
    [
        "10. **Few numbers in the diagnosis.**",
        "Use at most 2 numbers in the whole narrative, and none when a point is clear without them",
        'do not grade the size of a gap with words such as "far", "sharply" or "significantly"',
        '"narrative": [string]',
        "each one plain sentence of at most 25 words",
        "The other fields keep to the rule about copying numbers exactly.",
    ],
)
def test_the_prompt_asks_for_points_with_few_numbers(phrase):
    assert phrase in load_system_prompt().text


@pytest.mark.parametrize("name", ["system.md", "setup.md"])
def test_the_prompts_name_the_three_phase_values(name):
    from pathlib import Path

    import sf_orchestrator

    text = (Path(sf_orchestrator.__file__).parent / "prompts" / name).read_text(encoding="utf-8")
    assert "`phase` is exactly one of `architecture`, `configuration` or `rollout`; never invent another value" in text


# ───────────────────────── numbers: a warning, never a rejection ─────────────────────────


def test_the_prompt_asks_for_two_numbers_at_most():
    assert NUMBERS_ASKED_FOR == 2


# ───────────────────────── grounding rules of the diagnosis prompt ─────────────────────────


@pytest.mark.parametrize(
    "phrase",
    [
        # forecast: described in words, in one point, without numbers
        "Describe the forecast in words.",
        "whether the metric is expected to stay above (or below) the industry standard",
        # data findings: fixed wording, no speculation about what a field influences
        "The program itself adds one Risk row for every empty field",
        "Do not write those rows.",
        "Do not say what an empty field influences.",
        # business impact: built from the input only
        "Build them only from facts in the input",
        "cannot be quantified from the available data",
        "no competitors, candidates leaving, temporary staffing, overtime",
        # trend: only the comparisons chosen by code, described in words
        "Describe the trend only with `equalPeriodComparisons`, and in words, without numbers",
        # the diagnosis is a short list of points with few numbers
        "Few numbers in the diagnosis",
        "Use at most 2 numbers in the whole narrative",
        "3 to 5 short points",
        # no rankings or re-labelled counts
        "No superlatives or rankings the input does not give",
        "Say what was counted",
        "never turn a share of records into a share of something else",
    ],
)
def test_the_prompt_keeps_its_grounding_rules(phrase):
    assert phrase in load_system_prompt().text


def test_the_prompt_no_longer_asks_for_consequences_from_outside_the_input():
    text = load_system_prompt().text
    assert "can mean for the business" not in text
    assert 'using "can" or "may"' not in text


# ───────────────────────── the diagnosis prompt and the notebook format ─────────────────────────


SAMPLE = Path(__file__).resolve().parent / "samples" / "TimeToHire.json"


def _property_names(node, acc: set[str]) -> set[str]:
    if isinstance(node, dict):
        acc.update(node.get("properties", {}))
        for v in node.values():
            _property_names(v, acc)
    elif isinstance(node, list):
        for v in node:
            _property_names(v, acc)
    return acc


def test_system_prompt_documents_every_output_field_and_choice():
    """Guards prompts/system.md against drifting from the BrdDraft model."""
    prompt = load_system_prompt().text
    names = _property_names(BrdDraft.model_json_schema(by_alias=True), set())
    assert [n for n in names if f'"{n}"' not in prompt] == []
    for choice in ("architecture", "configuration", "rollout", "consultant", "processOwner", "qaUat", "Assumption", "Risk"):
        assert f'"{choice}"' in prompt


def test_system_prompt_describes_every_input_field_the_notebook_sends():
    """Guards prompts/system.md against drifting from the notebook format."""
    prompt = load_system_prompt().text
    payload = json.loads(SAMPLE.read_text())

    def keys(node, acc):
        if isinstance(node, dict):
            for k, v in node.items():
                if k not in {"periods", "children", "year", "quarter", "month", "granularity", "isPartial"}:  # raw trend tree
                    acc.add(k)
                keys(v, acc)
        elif isinstance(node, list):
            for v in node:
                keys(v, acc)
        return acc

    sent = keys(MetricInsight.model_validate(payload).for_prompt(), set()) - {"from", "to", "period", "average", "partial", "yearly", "quarterly", "monthly"}
    assert [k for k in sorted(sent) if f"`{k}`" not in prompt and k not in prompt] == []


def test_system_prompt_keeps_its_grounding_rules():
    """Guards the rules that stop the model adding information that is not in the input."""
    prompt = load_system_prompt().text
    for phrase in (
        "Only the information provided",
        "Never add new information",
        "Copy numbers exactly as given",
        "Facts versus proposals",
        "Do not describe the client's situation beyond the data",
        "Compare equal periods",
        "staging environment test",
    ):
        assert phrase in prompt


# ───────────────────────── the setup plan prompt ─────────────────────────


# ───────────────────────── the prompts ─────────────────────────


@pytest.mark.parametrize(
    "phrase",
    [
        "ONE HR metric that could NOT be calculated",
        "THE PLAN IS ABOUT THESE",
        "`mandatoryFieldsMissing`",
        "`otherFieldsMissing`",
        "Every workstream sets up one or more of the fields in `mandatoryFieldsMissing`",
        'all of `kind` "data" with an empty `fixesFactors`',
        "The LAST workstream runs the analysis again",
        "The input does not say why the fields are missing.",
        "Do not cite transaction codes, tables, screens, menu paths, settings, tools or integration names.",
        "The program itself adds one Risk row for every empty field in `otherFieldsMissing`",
        "the FIRST must say that the financial impact cannot be quantified from the available data",
        "Use at most 2 numbers in the whole narrative",
        "MUST also contain at least one activity for `qaUat`",
    ],
)
def test_the_setup_prompt_keeps_its_rules(phrase):
    assert phrase in load_setup_prompt().text


def test_the_contract_of_the_setup_prompt_names_every_field_the_program_reads():
    contract = load_setup_prompt().text.split("# Output contract", 1)[1]
    for name in ("diagnosis", "headline", "narrative", "businessImpact", "overview",
                 "financialImpact", "slaAndTurnaround", "governanceAndAudit", "workstreams", "id", "kind", "step", "fixesFactors", "activities",
                 "phase", "activity", "role", "workstream", "week", "hours", "assumptionsAndRisks", "type", "description", "mitigation"):
        assert f'"{name}"' in contract, name


# ───────────────────────── rankings and internal names ─────────────────────────


@pytest.mark.parametrize(
    "phrase",
    [
        "do not list the factors or their shares in any of the four fields",
        'Do not write the words "like with like" or "equal period comparisons".',
        "mention every failed check and every empty field",
    ],
)
def test_the_prompt_keeps_the_ranking_rules(phrase):
    assert phrase in load_system_prompt().text


def test_the_prompt_no_longer_invites_the_model_to_rank_segments():
    assert "take longest" not in load_system_prompt().text


# ───────────────────────── standards written as text ─────────────────────────


# ───────────────────────── the prompt keeps the rules for such data ─────────────────────────


@pytest.mark.parametrize(
    "phrase",
    [
        "When it is text (for example a statutory or company SLA described in words)",
        "If the industry standard is text, leave the comparison out.",
        "(Completeness, Staleness or Validity)",
    ],
)
def test_the_prompt_keeps_its_rules_for_text_standards(phrase):
    assert phrase in load_system_prompt().text
