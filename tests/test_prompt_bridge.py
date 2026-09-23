"""Guard the contract between Codex's free-form output and Ming's input."""

import unittest
from copy import deepcopy

from scripts.prompt_rewriter_bridge import validate_prompt


class PromptBridgeTests(unittest.TestCase):
    def setUp(self):
        self.prompt = {
            "canvas_settings": {
                "aspect_ratio": "16:9",
                "ambient_lighting": "Soft daylight",
                "image_style": "Clear editorial layout",
            },
            "layers": [
                {
                    "description": "Plain background",
                    "coordinates": "cx: 0.500, cy: 0.500, w: 1.000, h: 1.000",
                    "hierarchy_and_relation": "Behind everything",
                    "color_specs": ["#FFFFFF"],
                },
                {
                    "description": 'Headline "LOCAL AI"',
                    "coordinates": "cx: 0.300, cy: 0.300, w: 0.400, h: 0.100",
                    "hierarchy_and_relation": "Above the hero",
                    "color_specs": ["#14213D"],
                },
            ],
        }

    def test_valid_output_is_forced_to_mings_square_canvas(self):
        result = validate_prompt(deepcopy(self.prompt))
        self.assertEqual(result["canvas_settings"]["aspect_ratio"], "1:1, 2048 x 2048 px")

    def test_invalid_coordinates_cannot_reach_ming(self):
        prompt = deepcopy(self.prompt)
        prompt["layers"][1]["coordinates"] = "cx: 1.500, cy: 0.300, w: 0.400, h: 0.100"
        with self.assertRaisesRegex(ValueError, "coordinates"):
            validate_prompt(prompt)


if __name__ == "__main__":
    unittest.main()
