"""Historical scenarios opt in to fixture data; normal application startup is empty."""

import os

os.environ["BONDLAYER_TEST_DATA"] = "1"
