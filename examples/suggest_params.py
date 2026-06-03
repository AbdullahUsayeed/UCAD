import json
import os
from statistics import median

def suggest_parameters(board_data, examples_path=None):
    if examples_path is None:
        examples_path = os.path.join(os.path.dirname(__file__), "enclosure_examples.json")
    with open(examples_path) as f:
        examples = json.load(f)

    area = board_data["dimensions"]["width"] * board_data["dimensions"]["height"]
    closest = sorted(examples, key=lambda e: abs(e["board_width"] * e["board_depth"] - area))
    top3 = closest[:3]

    wall_thicknesses = [e["wall_thickness"] for e in top3]
    boss_ods = [e.get("boss_od", 3.0) for e in top3 if e.get("boss_od", 0) > 0]
    hole_diameters = [e["hole_diameter"] for e in top3]
    hole_margins = [e["hole_margin"] for e in top3]
    lid_clearances = [e.get("lid_clearance", 0.1) for e in top3 if e.get("has_lid")]

    return {
        "wall_thickness": median(wall_thicknesses),
        "hole_diameter": median(hole_diameters),
        "hole_margin": median(hole_margins),
        "boss_od": median(boss_ods) if boss_ods else 3.0,
        "lid_clearance": median(lid_clearances) if lid_clearances else 0.1,
        "has_lid": any(e.get("has_lid") for e in top3),
    }


if __name__ == "__main__":
    test_boards = [
        {"dimensions": {"width": 100, "height": 60}},
        {"dimensions": {"width": 50, "height": 30}},
        {"dimensions": {"width": 30, "height": 5}},
        {"dimensions": {"width": 55, "height": 28}},
    ]
    for board in test_boards:
        params = suggest_parameters(board)
        area = board["dimensions"]["width"] * board["dimensions"]["height"]
        print(f"Board {board['dimensions']['width']}x{board['dimensions']['height']} ({area}mm²):")
        for k, v in params.items():
            print(f"  {k}: {v}")
        print()
