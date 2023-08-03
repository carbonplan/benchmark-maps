import platform

from playwright.sync_api import sync_playwright

# get the OS name
os_name = platform.system()
chrome_args = ['--enable-unsafe-webgpu', '--ignore-gpu-blocklist']

if os_name == 'Linux':
    chrome_args.extend(['--enable-features=Vulkan,UseSkiaRenderer', '--use-angle=vulkan'])


def test_gpu_hardware_acceleration():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=chrome_args)
        page = browser.new_page()
        page.goto('chrome://gpu')
        feature_status_list = page.query_selector('.feature-status-list')
        assert 'Hardware accelerated' in feature_status_list.inner_text()
        # Check if webGL is enabled
        print(feature_status_list.inner_text())
        assert 'OpenGL: Enabled' in feature_status_list.inner_text()
        assert 'WebGL: Hardware accelerated' in feature_status_list.inner_text()
        assert 'WebGL2: Hardware accelerated' in feature_status_list.inner_text()
        assert 'WebGPU: Hardware accelerated' in feature_status_list.inner_text()
        browser.close()
