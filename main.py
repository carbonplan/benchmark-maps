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
    page.evaluate(
        """
        window._frameCounter = 0;
        window._timerStart = performance.now();
        window._frameDurations = [];
        window._prevFrameTime = performance.now();
        window._rafId = requestAnimationFrame(function countFrames() {
            const currentTime = performance.now();
            window._frameDurations.push(currentTime - window._prevFrameTime);
            window._prevFrameTime = currentTime;
            window._frameCounter++;
            window._rafId = requestAnimationFrame(countFrames);
        });
    """
    )

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

    # Wait until no paint events have occurred for 500 ms
    page.wait_for_function(
        """
        () => {
            const timeSinceLastPaint = performance.now() - window._lastPaint;
            return timeSinceLastPaint > 500;  // Change this threshold as needed
        }
    """
    )

    # Cancel the frame counting and calculate FPS and frame durations
    durations = page.evaluate(
        """
        cancelAnimationFrame(window._rafId);
        const durationInSeconds = (performance.now() - window._timerStart) / 1000;
        const fps = window._frameCounter / durationInSeconds;
        const frameDurations = window._frameDurations;
        [fps, frameDurations];
    """
    )

    fps = durations[0]
    frame_durations = durations[1]

    browser.close()

    # record frame duration and fps

    data = {
        'average_fps': round(fps, 0),
        'frame_durations_in_ms': frame_durations,
        'request_data': request_data,
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


with sync_playwright() as playwright:
    run(playwright)

    # Write the data to a json file
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')
    with open(data_dir / 'data.json', 'w') as outfile:
        json.dump(all_data, outfile, indent=4, sort_keys=True)
