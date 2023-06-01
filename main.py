import datetime
import itertools
import json
import pathlib

from playwright.sync_api import sync_playwright

data_dir = pathlib.Path(__file__).parent / 'data'
data_dir.mkdir(exist_ok=True, parents=True)


all_data = []


def run(playwright, operation, level):
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
        window._rafId = requestAnimationFrame(function countFrames() {
            window._frameCounter++;
            window._rafId = requestAnimationFrame(countFrames);
        });
    """
    )

    # Perform operation
    for _ in range(level):
        if operation == 'zoom_in':
            page.keyboard.press('=')
        elif operation == 'zoom_out':
            page.keyboard.press('-')
        # Add more elif conditions here for other operations

    page.wait_for_load_state('networkidle')

    # Cancel the frame counting and calculate FPS
    fps = page.evaluate(
        """
        cancelAnimationFrame(window._rafId);
        const durationInSeconds = (performance.now() - window._timerStart) / 1000;
        const fps = window._frameCounter / durationInSeconds;
        fps;
    """
    )

    browser.close()

    data = {
        'average_fps': round(fps, 0),
        'request_data': request_data,
        'operation': operation,
        'zoom_level': level,
    }

    all_data.append(data)

    print(
        f"Average FPS during {data['operation']} operation at level {data['zoom_level']}: {data['average_fps']}"
    )
    print(f"Total number of requests: {len(data['request_data'])}")
    print(
        f"Average response time for each tile: {sum(x['total_response_time_in_ms'] for x in data['request_data']) / len(data['request_data']):.2f} ms"
    )


with sync_playwright() as playwright:
    operations = ['zoom_in', 'zoom_out']  # Add more operations here
    levels = [1, 2, 3]  # Add more levels here
    for operation, level in itertools.product(operations, levels):
        run(playwright, operation, level)

    # Write the data to a json file
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')
    with open(data_dir / f'data_{now}.json', 'w') as outfile:
        json.dump(all_data, outfile, indent=4, sort_keys=True)
