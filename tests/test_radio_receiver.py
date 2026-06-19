from pathlib import Path
import unittest

from radio_receiver.decoders import decoder_for
from radio_receiver.input_sources import WavInputSource, build_input_source


class RadioReceiverTests(unittest.TestCase):
    def test_synthetic_fixture_decodes(self):
        fixture = (
            Path(__file__).resolve().parent.parent
            / "radio_receiver"
            / "fixtures"
            / "synthetic_1000hz.wav"
        )
        result = decoder_for("SYNTHETIC_TONE").decode(fixture)
        self.assertTrue(result.success)

    def test_unimplemented_decoder_never_claims_success(self):
        result = decoder_for("AFSK1200").decode(Path("anything.wav"))
        self.assertFalse(result.success)
        self.assertEqual(result.details["status"], "not_implemented")

    def test_wav_source_is_explicit_no_hardware_path(self):
        fixture = (
            Path(__file__).resolve().parent.parent
            / "radio_receiver"
            / "fixtures"
            / "synthetic_1000hz.wav"
        )
        source = build_input_source("wav", input_path=fixture)
        self.assertIsInstance(source, WavInputSource)
        self.assertEqual(source.acquire(), fixture)


if __name__ == "__main__":
    unittest.main()
