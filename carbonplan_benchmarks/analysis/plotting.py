# Utilities for plotting information from chromium trace records

import holoviews as hv
import hvplot.pandas  # noqa
import pandas as pd
from bokeh.models import HoverTool

pd.options.plotting.backend = 'holoviews'


def plot_request_with_hover_tool(row):
    df = pd.DataFrame({'time': [row['request_start'] + 5, row['response_end'] - 5]})
    df['y'] = row.name + 0.5
    include_vars = [
        'y',
        'encoded_data_length',
        'url',
        'method',
        'total_response_time_ms',
        'request_start',
        'response_end',
    ]
    for var in include_vars[1:]:
        df[var] = row[var]
    df['url'] = df['url'].apply(lambda x: '/'.join(x.split('/')[10:]))
    lines = hv.Curve(df, 'time', include_vars)
    tooltips = [
        ('Request start (ms)', '@request_start'),
        ('Response end (ms)', '@response_end'),
        ('Request duration (ms)', '@total_response_time_ms'),
        ('Encoded data length', '@encoded_data_length'),
        ('url', '@url'),
        ('Method', '@method'),
    ]
    hover = HoverTool(tooltips=tooltips)
    lines.opts(tools=[hover], line_color='lightgrey')
    return lines


def plot_requests(request_data: pd.DataFrame):
    """
    Plot rectangles showing each request duration
    """
    request_data['rectangle'] = request_data.apply(
        lambda x: (
            x['request_start'],
            x.name,
            x['response_end'],
            x.name + 1,
        ),
        axis=1,
    )
    plt = hv.Rectangles(request_data['rectangle'].to_list())
    plt.opts(width=1000, color='lightgrey', xlabel='Time (ms)', yaxis=None, title='Network')
    for row in request_data.iterrows():
        plt = plt * plot_request_with_hover_tool(row[1])
    return plt


def plot_frames(frame_data: pd.DataFrame, *, yl: int = 1):
    """
    Plot rectangles showing each fra,e duration
    """
    frame_data['rectangle'] = frame_data.apply(
        lambda x: (x['startTime'], yl, x['endTime'], yl + 1), axis=1
    )
    plt_opts = {
        'width': 1000,
        'xlabel': 'Time (ms)',
        'yaxis': None,
        'title': 'Frames',
        'ylim': (yl * 0.99, (yl + 1) * 1.01),
    }
    subsets = {'idle': 'lightgrey', 'isPartial': 'yellow', 'dropped': 'red', 'drawn': 'lightgreen'}
    plots = {}
    for key, value in subsets.items():
        subset = frame_data[frame_data[key]]
        plots[key] = hv.Rectangles(subset['rectangle'].to_list())
        plots[key].opts(**plt_opts, color=value)
    return plots['idle'] * plots['isPartial'] * plots['dropped'] * plots['drawn']


def plot_zoom_levels(action_data: pd.DataFrame, *, yl: int = 0, yh: int = 6):
    """
    Plot difference between the screenshots and baseline frames
    """
    action_data['rectangle'] = action_data.apply(
        lambda x: (
            x['start_time'],
            yl,
            x['end_time'],
            yh,
        ),
        axis=1,
    )
    return hv.Rectangles(action_data['rectangle'].to_list()).opts(color='darkgrey', alpha=0.3)


def plot_screenshot_rmse(*, screenshot_data: pd.DataFrame, metadata: pd.DataFrame):
    y = [f'rmse_snapshot_{x}' for x in range(metadata['zoom_level'] + 1)]
    plt = screenshot_data.hvplot(x='startTime', y=y)
    return plt.opts(width=1000, xlabel='Time (ms)', ylabel='RMSE')
