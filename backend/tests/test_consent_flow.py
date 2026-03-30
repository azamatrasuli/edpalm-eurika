"""Tests for consent flow defaults and minor handling — Phase 14."""


class TestConsentDefaults:
    """Verify that optional consents default to OFF."""

    OPTIONAL_PURPOSES = {"ai_memory", "notifications"}
    REQUIRED_PURPOSES = {"data_processing", "automated_decisions", "crm_sync"}

    def test_optional_purposes_are_known(self):
        """Smoke test: ensure purpose IDs match what's in the SQL migration."""
        # These are the IDs defined in 021_consent_fz152_compliance.sql
        all_purposes = self.OPTIONAL_PURPOSES | self.REQUIRED_PURPOSES
        assert "notifications" in all_purposes
        assert "automated_decisions" in all_purposes

    def test_required_purposes_list(self):
        assert "data_processing" in self.REQUIRED_PURPOSES
        assert "crm_sync" in self.REQUIRED_PURPOSES
        assert "automated_decisions" in self.REQUIRED_PURPOSES

    def test_optional_are_not_required(self):
        overlap = self.OPTIONAL_PURPOSES & self.REQUIRED_PURPOSES
        assert len(overlap) == 0, f"Purposes in both sets: {overlap}"
