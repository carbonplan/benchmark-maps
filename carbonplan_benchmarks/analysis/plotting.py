# Utilities for plotting information from chromium trace records

import holoviews as hv
import pandas as pd


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
    boxes = hv.Rectangles(request_data['rectangle'].to_list())
    boxes.opts(width=1000, color='lightgrey', xlabel='Time (ms)', yaxis=None, title='Network')
    return boxes


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
