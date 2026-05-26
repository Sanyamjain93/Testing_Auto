# Inject Windows/OS certificate store so corporate SSL proxies work with all HTTP clients.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass  # truststore not installed; run: pip install truststore

# Corporate SSL proxy fix: disable verification when SSL_VERIFY=false in .env
import os
from dotenv import load_dotenv
load_dotenv(override=True)
if os.getenv("SSL_VERIFY", "true").strip().lower() in ("false", "0", "no"):
    import ssl
    import warnings
    import urllib3
    ssl._create_default_https_context = ssl._create_unverified_context  # covers httpx / google-genai
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    os.environ["REQUESTS_CA_BUNDLE"] = ""     # covers requests / huggingface_hub
    os.environ["CURL_CA_BUNDLE"] = ""          # covers curl-backed libs
    from logger import get_logger
    get_logger().warning("SSL verification DISABLED (SSL_VERIFY=false). Running in corporate proxy mode.")

from pipeline import run

if __name__ == "__main__":
    run()