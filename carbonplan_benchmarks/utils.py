import pandas as pd


def shuffle_runs(*, datasets: list, nruns: int, **kwargs):
    """
    Create a shuffled set of run commands for various data configurations

    Parameters
    ----------

    datasets: list
        List of datasets to include

    nruns: int
        Number of runs for each dataset

    **kwargs
        Additional flags and parameters to include in the commands


    Returns
    -------
    commands : list
        List containing shuffled CLI commands
    """

    df = pd.DataFrame(datasets, columns=['command'])
    df['command'] = 'carbonplan_benchmarks --dataset' + ' ' + df['command']
    for key, value in kwargs.items():
        key = key.replace('_', '-')
        df['command'] = df['command'] + ' --' + key
        if value is not True:
            df['command'] = df['command'] + ' ' + str(value)
    df = df.loc[df.index.repeat(nruns)].reset_index(drop=True).sample(frac=1)
    return df['command'].to_list()
