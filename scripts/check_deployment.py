"""Exercise the two Fly images locally, with separate disks and no paid API calls.

Build Dockerfile.merchant and Dockerfile.agent first. This creates and removes only its
own uniquely named containers, network and volume. It never uses a production volume.
"""

import argparse
import secrets
import subprocess
import time
from uuid import uuid4

import httpx


def docker(*args: str, optional: bool = False) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120)
    if result.returncode and not optional:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout.strip()


def address(name: str) -> str:
    return "http://" + docker("port", name, "8080/tcp").splitlines()[0]


def wait(url: str) -> None:
    for _ in range(60):
        try:
            if httpx.get(url + "/health", timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise RuntimeError(f"Service did not become healthy: {url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merchant-image", default="bondlayer-merchant:unified-check")
    parser.add_argument("--agent-image", default="bondlayer-agent:unified-check")
    args = parser.parse_args()
    prefix = "bondlayer-check-" + uuid4().hex[:10]
    merchant, agent, network, volume = (prefix + suffix for suffix in ("-merchant", "-agent", "-network", "-data"))
    token = secrets.token_urlsafe(32)
    network_created = volume_created = False

    def start_merchant() -> str:
        docker("run", "-d", "--name", merchant, "--network", network, "--network-alias", "merchant",
               "-p", "127.0.0.1::8080", "-v", f"{volume}:/data",
               "-e", "BONDLAYER_AI_MODE=rules", "-e", "BONDLAYER_TEST_DATA=0",
               "-e", f"BONDLAYER_SERVICE_TOKEN={token}", args.merchant_image)
        url = address(merchant)
        wait(url)
        return url

    try:
        docker("network", "create", network)
        network_created = True
        docker("volume", "create", volume)
        volume_created = True
        merchant_url = start_merchant()
        docker("run", "-d", "--name", agent, "--network", network, "-p", "127.0.0.1::8080",
               "-e", "BONDLAYER_MERCHANT_URL=http://merchant:8080",
               "-e", "BONDLAYER_AI_MODE=rules", "-e", "BONDLAYER_TEST_DATA=0",
               "-e", f"BONDLAYER_SERVICE_TOKEN={token}", args.agent_image)
        agent_url = address(agent)
        wait(agent_url)

        with httpx.Client(base_url=merchant_url, timeout=30) as shop, httpx.Client(base_url=agent_url, timeout=30) as buyer:
            assert shop.get("/onboard/merchants").json() == []
            for page in ("/console/", "/console/onboarding/", "/console/benefits/", "/console/requests/", "/console/settings/"):
                assert shop.get(page).status_code == 200, page
            assert buyer.get("/merchant-health").json()["reachable"] is True
            csv = "sku,title,category,price,ram,stock\nOWN-1,Deployment test laptop,laptop,999,16GB,5\n"
            response = shop.post("/onboard/catalog?merchant=shop&create=true", files={"file": ("products.csv", csv)})
            assert response.status_code == 200, response.text
            response = buyer.post("/query", json={"query": "a laptop under $1500", "bondlayer_enabled": False})
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["winner"]["sku_id"] == "OWN-1", result
            assert result["history_error"] is None, result["history_error"]
            request_id = result["request_id"]
            assert request_id
            assert shop.get(f"/onboard/requests/{request_id}").json()["source"] == "live"
            assert shop.get("/onboard/insights/shop?mode=all&days=0").status_code == 200
            assert shop.post("/internal/requests", json={}).status_code == 401
            # A stateless agent must not have created a local requests directory.
            absent = docker("exec", agent, "python", "-c",
                            "from bondlayer.activity import UPLOADS; print((UPLOADS / 'requests').exists())")
            assert absent == "False", absent
            print("PASS: separate services, real upload/search/checkout, authenticated HTTP history, insights and static console")

        docker("rm", "-f", merchant)
        merchant_url = start_merchant()
        with httpx.Client(base_url=merchant_url, timeout=30) as shop:
            assert shop.get("/shop/ucp/catalog/search").json()["products"][0]["id"] == "OWN-1"
            assert shop.get(f"/onboard/requests/{request_id}").status_code == 200
        assert httpx.get(agent_url + "/merchant-health", timeout=10).json()["reachable"] is True
        print("PASS: replacing the merchant container preserves catalogue and history on its volume")
        print("No OpenAI requests were made: this deployment check uses explicit rules mode with user-uploaded test data.")
    except Exception:
        for name in (merchant, agent):
            print(docker("logs", "--tail", "40", name, optional=True))
        raise
    finally:
        docker("rm", "-f", agent, merchant, optional=True)
        if volume_created:
            docker("volume", "rm", volume, optional=True)
        if network_created:
            docker("network", "rm", network, optional=True)


if __name__ == "__main__":
    main()
