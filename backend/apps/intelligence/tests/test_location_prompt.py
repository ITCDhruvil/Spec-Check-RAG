from apps.intelligence.prompts.templates import (
    EXTRACTION_FEW_SHOT,
    EXTRACTION_TYPE_INSTRUCTIONS,
)


def test_location_instruction_states_all_location_types():
    instr = EXTRACTION_TYPE_INSTRUCTIONS["technical_requirements"].lower()
    assert "every distinct" in instr
    assert "counties" in instr
    assert "bridge" in instr
    assert "point-to-point" in instr or "milepost" in instr
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
    # District + counties example present.
    assert "district 8" in lower
    assert "counties" in lower
    # Allowed labels unchanged.
    assert "project_location" in shot
    assert "project_square_footage" in shot
