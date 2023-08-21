import os


def test_entrypoint():
    exit_status = os.system(
        'carbonplan_benchmarks --dataset pyramids-v2-3857-True-128-1-0-0-f4-0-0-0-gzipL1-100'
    )
    assert exit_status == 0
