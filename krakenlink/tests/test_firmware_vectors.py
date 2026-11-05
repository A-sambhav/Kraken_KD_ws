from pathlib import Path
import runpy


def test_committed_firmware_vectors_match_python_proto():
    script = Path(__file__).resolve().parents[1] / "firmware/esp32_link/tools/gen_vectors.py"
    namespace = runpy.run_path(str(script))
    committed = script.resolve().parents[1] / "test/test_klf/vectors.h"
    assert committed.read_text() == namespace["render"]()
