import json
import pathlib

from playwright.sync_api import sync_playwright

data_dir = pathlib.Path(__file__).parent / 'data'
data_dir.mkdir(exist_ok=True, parents=True)


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
                'total_request_time_in_ms': request.timing['responseEnd']
                - request.timing['requestStart'],
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

    # Zooming out to one level
    page.keyboard.press('=')  # (-) zoom out | (=) zoom in

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

    # page.screenshot(path='example.png')
    browser.close()

    data = {
        'average_fps': round(fps, 0),
        'request_data': request_data,
        'operation': 'zooming',
        'zoom_level': 1,
    }

    print(f"Average FPS during {data['operation']} operation: {data['average_fps']}")
    print(f'Zoom level: {data["zoom_level"]}')
    print(f"Total number of requests: {len(data['request_data'])}")
    print(
        f"Average request time for each tile: {sum(x['total_request_time_in_ms'] for x in data['request_data']) / len(data['request_data']):.2f} ms"
    )

    # Write the data to a json file
    with open(data_dir / 'data.json', 'w') as outfile:
        json.dump(data, outfile, indent=4, sort_keys=True)


with sync_playwright() as playwright:
    run(playwright)
