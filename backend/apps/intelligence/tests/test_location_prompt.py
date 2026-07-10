from apps.intelligence.prompts.templates import (
    EXTRACTION_FEW_SHOT,
    EXTRACTION_TYPE_INSTRUCTIONS,
)


def test_location_instruction_states_specificity_rules():
    instr = EXTRACTION_TYPE_INSTRUCTIONS["technical_requirements"].lower()
    # Must tell the model to prefer the most specific location.
    assert "most specific" in instr
    # Bare city is a fallback only.
    assert "fallback" in instr
    # Distinct sites emitted separately.
    assert "distinct" in instr


def test_location_few_shot_covers_taxonomy():
    shot = EXTRACTION_FEW_SHOT["technical_requirements"]
    lower = shot.lower()
    # Full address example present.
    assert "8000 park lane" in lower
    # Road segment example present.
    assert "from" in lower and "to" in lower
    # Point-to-point example present.
    assert "between" in lower
    # Negative case: bare city alongside full address -> address only.
    assert "city of" in lower
    # Allowed labels unchanged.
    assert "project_location" in shot
    assert "project_square_footage" in shot
