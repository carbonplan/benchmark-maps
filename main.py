import datetime
import json
import pathlib

import numpy as np
from playwright.sync_api import sync_playwright

data_dir = pathlib.Path(__file__).parent / 'data'
data_dir.mkdir(exist_ok=True, parents=True)


all_data = []


def run(playwright):
    browser = playwright.chromium.launch()
    context = browser.new_context()
    page = context.new_page()

    request_data = []

    # Subscribe to "requestfinished" events.
    page.on(
        'requestfinished',
        lambda request: request_data.append(
            {
                'method': request.method,
                'url': request.url,
                'total_response_time_in_ms': request.timing['responseEnd']
                - request.timing['requestStart'],
                'response_end': request.timing['responseEnd'],
                'request_start': request.timing['requestStart'],
            }
        )
        if 'storage.googleapis.com/carbonplan-maps/v2/demo' in request.url
        else None,
    )

    page.goto('https://maps.demo.carbonplan.org/')

    # Focus on the map element
    page.focus('.mapboxgl-canvas')

    # Click on the map element
    page.click('.mapboxgl-canvas')

    # Start the timer and initialize frame counter in the page

    # Create the PerformanceObserver in the page's context
    page.evaluate(
        """
        window._lastPaint = performance.now();
        window._perfObserver = new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                if (entry.entryType === 'paint') {
                    window._lastPaint = performance.now();
                }
            }
        });
        window._perfObserver.observe({ entryTypes: ['paint'] });
    """
    )

    # Start the timer and initialize frame counter in the page
    # this measures the frame rate and frame durations only during actual content changes,
    # by counting frames when a paint event has occurred.
    # the following approach involves storing the time of the last paint event and
    # only counting a frame if the time since the last paint event is less than a certain threshold (e.g., 500 ms)
    # the _frameCounter and _frameDurations will only be updated when the page is actively being painted.
    time_since_last_paint_threshold = 500  # change this threshold as needed (in ms)
    page.evaluate(
        f"""
    window._frameCounter = 0;
    window._timerStart = performance.now();
    window._frameDurations = [];
    window._prevFrameTime = performance.now();
    window._rafId = requestAnimationFrame(function countFrames() {{
        const currentTime = performance.now();
        const timeSinceLastPaint = currentTime - window._lastPaint;
        if (timeSinceLastPaint < {time_since_last_paint_threshold}) {{  // Change this threshold as needed
            window._frameDurations.push(currentTime - window._prevFrameTime);
            window._frameCounter++;
        }}
        window._prevFrameTime = currentTime;
        window._rafId = requestAnimationFrame(countFrames);
    }});
"""
    )

    # Wait until no paint events have occurred for the duration of the threshold
    page.wait_for_function(
        f"""
        () => {{
            const timeSinceLastPaint = performance.now() - window._lastPaint;
            return timeSinceLastPaint > {time_since_last_paint_threshold};  // If time since last paint is more than threshold
        }}

    """
    )

    # Cancel the frame counting and calculate FPS, total duration and frame durations
    durations = page.evaluate(
        """
        cancelAnimationFrame(window._rafId);
        const timerEnd = performance.now();
        const durationInSeconds = (timerEnd - window._timerStart) / 1000;
        const fps = window._frameCounter / durationInSeconds;
        const frameDurations = window._frameDurations;
        [fps, frameDurations, window._timerStart, timerEnd];
    """
    )

    fps = durations[0]
    frame_durations = durations[1]
    timer_start = durations[2]
    timer_end = durations[3]

    browser.close()

    # record frame duration and fps

    data = {
        'average_fps': round(fps, 0),
        'frame_durations_in_ms': frame_durations,
        'request_data': request_data,
        'timer_start': timer_start,
        'timer_end': timer_end,
        'total_duration_in_ms': timer_end - timer_start,
    }

    all_data.append(data)

    frame_durations_mean = np.mean(frame_durations)
    frame_durations_median = np.median(frame_durations)
    frame_durations_percentiles = np.percentile(frame_durations, [25, 50, 75, 90])

    print(f"Average FPS: {data['average_fps']}")
    print(f'Average frame duration: {frame_durations_mean}')
    print(f'Median frame duration: {frame_durations_median}')
    print(f'25th percentile frame duration: {frame_durations_percentiles[0]}')
    print(f'50th percentile frame duration: {frame_durations_percentiles[1]}')
    print(f'75th percentile frame duration: {frame_durations_percentiles[2]}')
    print(f'90th percentile frame duration: {frame_durations_percentiles[3]}')
    print(f"Total number of requests: {len(data['request_data'])}")
    print(
        f"Average response time for each tile: {sum(x['total_response_time_in_ms'] for x in data['request_data']) / len(data['request_data']):.2f} ms"
    )
    print(f'Total duration: {data["total_duration_in_ms"]:.2f} ms')
    print(f'Time since last paint threshold: {time_since_last_paint_threshold} ms')


with sync_playwright() as playwright:
    run(playwright)

    # Write the data to a json file
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')
    with open(data_dir / 'data.json', 'w') as outfile:
        json.dump(all_data, outfile, indent=4, sort_keys=True)
