import os

import pytest

from optimizer.optimizer import Optimizer
from tests.test_optimizer import make_workload

pytestmark = pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY set nahi")


def test_real_llm_path():
    out = Optimizer(make_workload()).run()
    assert out["source"] == "llm", out["llm_error"]       # fallback ho gaya to yahin fail
    assert out["suggestions"]
