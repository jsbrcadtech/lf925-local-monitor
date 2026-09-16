import unittest
from http import HTTPStatus

from vtech_api import ApiError, build_command


class BuildCommandTests(unittest.TestCase):
    def test_ptz(self):
        self.assertEqual(build_command("ptz", {"direction": "left"}), "PTZ LEFT")

    def test_light_preset_and_brightness(self):
        self.assertEqual(
            build_command("light", {"preset": "blue", "brightness": 57}),
            "LIGHT PRESET 5 ; LIGHT POWER 1 57",
        )

    def test_light_rgb(self):
        self.assertEqual(build_command("light", {"rgb": [1, 2, 3]}),
                         "LIGHT RGB 1 2 3")

    def test_light_off_uses_proven_power_contract(self):
        self.assertEqual(build_command("light", {"enabled": False}),
                         "LIGHT POWER 0 98")
        self.assertEqual(
            build_command("light", {"enabled": False, "brightness": 57}),
            "LIGHT POWER 0 57",
        )

    def test_light_on_default(self):
        self.assertEqual(build_command("light", {"enabled": True}),
                         "LIGHT POWER 1 98")

    def test_light_timer(self):
        self.assertEqual(build_command("light_timer", {"seconds": 900}),
                         "LIGHT_TIMER 900")

    def test_lullaby_bounds(self):
        self.assertEqual(build_command("lullaby", {"track": -1}),
                         "LULLABY_TRACK -1")
        self.assertEqual(build_command("lullaby", {"track": 10}),
                         "LULLABY_TRACK 10")

    def test_lullaby_params(self):
        self.assertEqual(
            build_command("lullaby_params", {"volume": 3, "timer_seconds": 1800}),
            "LULLABY_PARAMS 3 1800",
        )

    def test_reject_unknown_light_fields(self):
        with self.assertRaises(ApiError) as cm:
            build_command("light", {"enabled": True, "raw": "bad"})
        self.assertEqual(cm.exception.status, HTTPStatus.BAD_REQUEST)

    def test_reject_off_with_colour(self):
        with self.assertRaises(ApiError):
            build_command("light", {"enabled": False, "preset": "blue"})


if __name__ == "__main__":
    unittest.main()
