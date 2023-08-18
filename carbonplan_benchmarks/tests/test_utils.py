from carbonplan_benchmarks.utils import shuffle_runs


def test_randomize_runs():
    datasets = ['pyramids-v3-sharded-4326-1MB', 'pyramids-v3-sharded-4326-5MB']
    nruns = 10
    runs = shuffle_runs(datasets=datasets, nruns=nruns, non_headless=True)
    assert len(runs) == 20
    assert runs[0] in {
        'carbonplan_benchmarks --dataset pyramids-v3-sharded-4326-1MB --non-headless',
        'carbonplan_benchmarks --dataset pyramids-v3-sharded-4326-5MB --non-headless',
    }
