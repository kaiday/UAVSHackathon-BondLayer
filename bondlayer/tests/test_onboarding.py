from pathlib import Path

from bondlayer.onboarding import OnboardingService


def service(tmp_path: Path) -> OnboardingService:
    return OnboardingService(tmp_path / "onboarding.json")


def complete(s: OnboardingService) -> None:
    s.save_profile("m1", {"business_name": "Harbor", "registration": "ABN", "contact": "Ada"})
    s.upload("m1", "business_document", "abn.pdf", b"pdf")
    s.import_catalogue("m1", "products.csv", b"sku,name,price\nS1,Widget,9.95\n")
    for policy in ("shipping", "returns", "privacy"):
        s.upload("m1", policy, f"{policy}.txt", b"policy")
    p = s.current_membership_policy(); s.accept_membership("m1", "u1", p["policy_id"], p["version"])


def test_draft_resume_persists_to_repository(tmp_path: Path) -> None:
    s = service(tmp_path); s.save_profile("m1", {"business_name": "Harbor", "registration": "ABN", "contact": "Ada"}, "files")
    resumed = OnboardingService(tmp_path / "onboarding.json").state("m1")
    assert resumed["current_step"] == "files" and not resumed["incomplete_requirements"][0].get("code") == "business_profile"


def test_invalid_upload_and_invalid_catalogue_rows_do_not_complete(tmp_path: Path) -> None:
    s = service(tmp_path)
    assert s.upload("m1", "business_document", "bad.exe", b"x")["state"] == "rejected"
    result = s.import_catalogue("m1", "products.csv", b"sku,name,price\nS1,,9\n")
    assert result["valid_products"] == 0 and result["row_errors"][0]["destination_step"] == "catalogue"


def test_missing_policies_blocks_submission(tmp_path: Path) -> None:
    s = service(tmp_path); result = s.submit("m1", "u1")
    assert result["status"] == "blocked" and {x["code"] for x in result["incomplete_requirements"]} >= {"shipping_policy", "returns_policy", "privacy_policy"}


def test_changed_membership_policy_requires_current_version(tmp_path: Path) -> None:
    s = service(tmp_path); p = s.current_membership_policy()
    try: s.accept_membership("m1", "u1", p["policy_id"], "0.9")
    except ValueError as exc: assert "changed" in str(exc)
    else: raise AssertionError("stale policy version was accepted")


def test_complete_onboarding_submits_without_publishing(tmp_path: Path) -> None:
    s = service(tmp_path); complete(s); result = s.submit("m1", "u1")
    assert result["accepted"] and result["status"] == "submitted"
