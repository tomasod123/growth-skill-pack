import json
import os
import sys

import pytest
import yaml

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

START, END = "2026-09-15", "2026-10-12"


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name + ".json")) as f:
        return json.load(f)


@pytest.fixture
def cfg():
    with open(os.path.join(HERE, "fixtures", "demo-config.yaml")) as f:
        return yaml.safe_load(f)


@pytest.fixture
def bm():
    with open(os.path.join(HERE, "benchmarks.yaml")) as f:
        return yaml.safe_load(f)


@pytest.fixture
def data(cfg):
    from sources import ALL
    return {s.NAME: s.parse(fixture(s.NAME), cfg, START, END) for s in ALL}
