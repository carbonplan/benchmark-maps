import argparse
import json

import holoviews as hv
import hvplot.pandas
import pandas as pd

pd.options.plotting.backend = 'holoviews'


def extract_request_data(*, trace_events, url_filter: str = None):
    """
    Extract request data from a list of Chromium trace events, optionally filtering by URL.

    Parameters
    ----------

    trace_events: list
         The list of trace events.
    url_filter : str, optional
        If specified, only include requests where the URL contains this string.

    Returns
    -------
    request_data : DataFrame containing information about requests
    """
    send_requests = pd.json_normalize(
        [event for event in trace_events if event['name'] == 'ResourceSendRequest']
    )
    finish_requests = pd.json_normalize(
        [event for event in trace_events if event['name'] == 'ResourceFinish']
    )
    data = send_requests.merge(
        finish_requests, on='args.data.requestId', how='left', suffixes=('_send', '_finish')
    )[
        [
            'ts_send',
            'ts_finish',
            'args.data.encodedDataLength',
            'args.data.priority',
            'args.data.url',
            'args.data.requestMethod',
        ]
    ].rename(
        {
            'ts_send': 'request_start',
            'ts_finish': 'response_end',
            'args.data.encodedDataLength': 'encoded_data_length',
            'args.data.url': 'url',
            'args.data.requestMethod': 'method',
        },
        axis=1,
    )
    data['request_start'] = data['request_start'] * 1e-3
    data['response_end'] = data['response_end'] * 1e-3
    data['total_response_time_ms'] = data['response_end'] - data['request_start']
    if url_filter:
        data = data[data['url'].str.contains(url_filter)]
    return data


def load_frame_data(*, frame_data_path: str):
    """
    Load frame data from the output of Chrome dev tools.

    Parameters
    ----------

    frame_data_path: str
        Path to the json containing frame data

    Returns
    -------
    frame_data : pd:DataFrame
        DataFrame containing frame timing and durations
    """
    with open(frame_data_path) as f:
        frames = json.load(f)
    frames = pd.json_normalize(frames).sort_values(by='startTime')[
        ['startTime', 'endTime', 'duration']
    ]
    return frames


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


def plot_frames(df: pd.DataFrame):
    """
    Plot rectangles showing each fra,e duration
    """
    df['rectangle'] = df.apply(lambda x: (x['startTime'], 1, x['endTime'], 2), axis=1)
    boxes = hv.Rectangles(df['rectangle'].to_list())
    boxes.opts(width=1000, color='lightgreen', xlabel='Timestamp', yaxis=None)
    return boxes


# Parse command line arguments and run main function
if __name__ == '__main__':
    # Parse input args
    parser = argparse.ArgumentParser()
    parser.add_argument('--timestamp', type=str)
    parser.add_argument('--run', type=int, default=1)
    args = parser.parse_args()
    trace_data_fp = f'chrome-devtools-traces/{args.timestamp}-{args.run}.json'
    frame_data_fp = f'chrome-devtools-traces/frames/{args.timestamp}-{args.run}.json'
    # Extract request data
    with open(trace_data_fp) as f:
        trace_data = json.load(f)
    url_filter = 'carbonplan-maps.s3.us-west-2.amazonaws.com/v2/demo'
    filtered_request_data = extract_request_data(
        trace_events=trace_data['traceEvents'], url_filter=url_filter
    )
    # Extract frame data
    frame_data = load_frame_data(frame_data_path=frame_data_fp)
    requests_plt = plot_requests(filtered_request_data)
    frames_plt = plot_frames(frame_data)
    # Show plot using bokeh server
    hvplot.show((requests_plt + frames_plt).cols(1))
