"""Historical scenarios opt in to fixture data; normal application startup is empty."""

import os

os.environ["BONDLAYER_TEST_DATA"] = "1"
os.environ["BONDLAYER_AI_MODE"] = "rules"
os.environ["BONDLAYER_SERVICE_TOKEN"] = "bondlayer-test-service-token"
