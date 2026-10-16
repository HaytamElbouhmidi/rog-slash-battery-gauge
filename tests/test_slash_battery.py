import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import call, patch

MODULE = Path(__file__).resolve().parents[1] / "slash-battery.py"
SPEC = importlib.util.spec_from_file_location("slash_battery", MODULE)
slash_battery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(slash_battery)


class BrightnessTests(unittest.TestCase):
    def test_zero_and_full(self):
        self.assertEqual(slash_battery.battery_brightness(0), 0)
        self.assertEqual(slash_battery.battery_brightness(100), 255)

    def test_gamma_corrected_levels(self):
        self.assertEqual(slash_battery.battery_brightness(5), 8)
        self.assertEqual(slash_battery.battery_brightness(30), 25)
        self.assertEqual(slash_battery.battery_brightness(50), 62)
        self.assertEqual(slash_battery.battery_brightness(90), 204)

    def test_brightness_increases_monotonically(self):
        last = -1
        for capacity in range(101):
            value = slash_battery.battery_brightness(capacity)
            self.assertGreaterEqual(value, last)
            self.assertLessEqual(value, 255)
            last = value

    def test_gamma_is_adjustable(self):
        self.assertGreater(slash_battery.battery_brightness(50, gamma=1.0),
                           slash_battery.battery_brightness(50, gamma=3.0))

    def test_brightness_rejects_invalid_inputs(self):
        for capacity in (-1, 101):
            with self.assertRaises(ValueError):
                slash_battery.battery_brightness(capacity)
        for gamma in (0, -1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                slash_battery.battery_brightness(50, gamma)


class SegmentTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(slash_battery.segment_values(0), [0] * 7)

    def test_full(self):
        self.assertEqual(slash_battery.segment_values(100), [255] * 7)

    def test_thirty_percent_is_bottom_up(self):
        self.assertEqual(slash_battery.segment_values(30), [0, 0, 0, 0, 0, 25, 25])

    def test_ninety_percent(self):
        self.assertEqual(slash_battery.segment_values(90), [0] + [204] * 6)

    def test_ninety_nine_percent(self):
        brightness = slash_battery.battery_brightness(99)
        self.assertEqual(slash_battery.segment_values(99), [0] + [brightness] * 6)

    def test_half(self):
        self.assertEqual(slash_battery.segment_values(50), [0, 0, 0, 0, 62, 62, 62])

    def test_low_battery_has_one_dim_segment(self):
        self.assertEqual(slash_battery.segment_values(5), [0, 0, 0, 0, 0, 0, 8])

    def test_top_down_override(self):
        self.assertEqual(slash_battery.segment_values(30, bottom_up=False), [25, 25, 0, 0, 0, 0, 0])

    def test_levels_are_monotonic(self):
        previous = [0] * 7
        for capacity in range(101):
            values = slash_battery.segment_values(capacity)
            self.assertEqual(len(values), 7)
            self.assertTrue(all(0 <= value <= 255 for value in values))
            self.assertTrue(all(value >= old for value, old in zip(values, previous)))
            previous = values

    def test_rejects_invalid_percentages(self):
        for capacity in (-1, 101):
            with self.assertRaises(ValueError):
                slash_battery.segment_values(capacity)

    def test_frame_packet(self):
        with patch.object(slash_battery, "feature_write") as feature:
            slash_battery.write_frame(5, [0, 0, 0, 0, 0, 25, 25])
        feature.assert_called_once_with(5, bytes((0xD3, 0, 0, 7, 0, 0, 0, 0, 0, 25, 25)))


class HardwareTests(unittest.TestCase):
    def test_hardware_test_restores_actual_capacity(self):
        stages = [
            ("BAT1 0%", [0] * 7),
            ("BAT1 30%", slash_battery.segment_values(30)),
            ("BAT1 100%", [255] * 7),
        ]
        with (
            patch.object(slash_battery, "open_controller", return_value=4),
            patch.object(slash_battery, "initialize_custom_mode"),
            patch.object(slash_battery, "write_frame") as frame,
            patch.object(slash_battery, "battery_capacity", return_value=90),
            patch.object(slash_battery.time, "sleep"),
            patch.object(slash_battery.os, "close") as close,
        ):
            slash_battery.hardware_test(stages, 1, True, 2.2, None)

        frame.assert_has_calls([
            call(4, [0] * 7),
            call(4, [0, 0, 0, 0, 0, 25, 25]),
            call(4, [255] * 7),
            call(4, [0] + [204] * 6),
        ])
        self.assertEqual(frame.call_count, 4)
        close.assert_called_once_with(4)

    def test_brightness_test_keeps_all_seven_leds_on(self):
        with (
            patch.object(sys, "argv", ["slash-battery.py", "--brightness-test"]),
            patch.object(slash_battery, "hardware_test") as hardware,
            patch.object(slash_battery.signal, "signal"),
        ):
            slash_battery.main()
        stages = hardware.call_args.args[0]
        self.assertEqual(stages, [
            ("RAW PWM 8/255", [8] * 7),
            ("RAW PWM 64/255", [64] * 7),
            ("RAW PWM 255/255", [255] * 7),
        ])

    def test_reverse_flag_remains_compatible(self):
        with (
            patch.object(sys, "argv", ["slash-battery.py", "--once", "--reverse"]),
            patch.object(slash_battery, "controller_loop") as loop,
            patch.object(slash_battery.signal, "signal"),
        ):
            slash_battery.main()
        self.assertTrue(loop.call_args.args[1])

    def test_top_down_flag(self):
        with (
            patch.object(sys, "argv", ["slash-battery.py", "--once", "--top-down"]),
            patch.object(slash_battery, "controller_loop") as loop,
            patch.object(slash_battery.signal, "signal"),
        ):
            slash_battery.main()
        self.assertFalse(loop.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
