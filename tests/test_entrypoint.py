import os


def test_entrypoint():
    exit_status = os.system(
        'carbonplan_benchmarks --dataset pyramids-v3-sharded-4326-1MB --non-headless'
    )
    assert exit_status == 0
