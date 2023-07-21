import argparse

import holoviews as hv
import hvplot.pandas
import numpy as np
import pandas as pd

pd.options.plotting.backend = 'holoviews'


def extract_frames(df: pd.DataFrame, run: int):
    """
    Extract frame information from trace JSON for a given run
    """
    return pd.DataFrame(
        {
            'timestamp_ms': np.array(df.iloc[run]['chromium_trace_frame_timestamps_in_micros'])
            * 1e-3,  # nb: based on timestamps being in nanoseconds
            'durations_ms': np.array(df.iloc[run]['chromium_trace_frame_durations_in_s']) * 1000,
            'fps': np.array(df.iloc[run]['chromium_trace_fps']),
        }
    )


def extract_requests(df: pd.DataFrame, run: int):
    """
    Extract request information from trace JSON for a given run
    """
    return pd.DataFrame(df.iloc[run]['chromium_trace_request_data'])


def plot_frame_hist(df: pd.DataFrame):
    """
    Plot a histogram of frame durations
    """
    hist = df.hvplot.hist('durations_ms', bins=100)
    hist.opts(width=1000, xlabel='Duration (ms)', ylabel='Counts')
    return hist


def plot_frame_durations(df: pd.DataFrame):
    """
    Plot rectangles showing each frame duration
    """
    df['rectangle'] = df.apply(
        lambda x: (x['timestamp_ms'], 0, x['timestamp_ms'] + x['durations_ms'], 1), axis=1
    )
    boxes = hv.Rectangles(df['rectangle'].to_list())
    boxes.opts(width=1000, color='lightgreen', xlabel='Timestamp', yaxis=None)
    return boxes


def plot_requests(df: pd.DataFrame):
    """
    Plot rectangles showing each request duration
    """
    df['rectangle'] = df.apply(
        lambda x: (x['request_start'], x.name, x['response_end'], x.name + 1), axis=1
    )
    boxes = hv.Rectangles(df['rectangle'].to_list())
    boxes.opts(width=1000, color='lightgrey', xlabel='Timestamp', yaxis=None)
    return boxes


# Parse command line arguments and run main function
if __name__ == '__main__':
    # Parse input args
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=str)
    parser.add_argument('--run', type=int, default=0)
    args = parser.parse_args()
    # Extract data
    df = pd.read_json(args.data)
    frames = extract_frames(df, args.run)
    requests = extract_requests(df, args.run)
    # Create plots
    hist_plt = plot_frame_hist(frames)
    frames_plt = plot_frame_durations(frames)
    requests_plt = plot_requests(requests)
    # Show plot using bokeh server
    hvplot.show((hist_plt + requests_plt + frames_plt).cols(1))
