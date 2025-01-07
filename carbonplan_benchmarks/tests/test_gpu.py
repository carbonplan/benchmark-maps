import platform

from playwright.sync_api import sync_playwright

# get the OS name
os_name = platform.system()
chrome_args = ['--enable-unsafe-webgpu', '--ignore-gpu-blocklist', '--disable-software-rasterizer']

if os_name == 'Linux':
    chrome_args.extend(
        ['--enable-features=Vulkan,UseSkiaRenderer', '--use-angle=vulkan', '--enable-gpu']
    )


def test_gpu_hardware_acceleration():
    with sync_playwright() as p:

        browser = p.chromium.launch(args=chrome_args, headless=True)
        page = browser.new_page()

        # First navigate to a regular page
        page.goto('https://webglreport.com')

        # Now check GPU capabilities using JavaScript
        gpu_info = page.evaluate(
            """() => {
                const canvas = document.createElement('canvas');
                const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
                const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                return {
                    vendor: gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL),
                    renderer: gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL),
                    webglVersion: gl.getParameter(gl.VERSION)
                }
            }"""
        )

        print('GPU Info:', gpu_info)

        # Assert GPU acceleration is enabled
        assert gpu_info['renderer'] and 'software' not in gpu_info['renderer'].lower()

        browser.close()
