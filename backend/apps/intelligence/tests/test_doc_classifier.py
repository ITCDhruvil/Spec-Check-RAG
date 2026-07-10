"""C1 — doc-type classification + query routing tests."""

from django.test import SimpleTestCase, override_settings

from apps.intelligence.choices import ExtractionType
from apps.intelligence.services.doc_classifier import DocClassification, classify
from apps.intelligence.services.extraction_retrieval_service import (
    overrides_for_classification,
)


class ClassifyTests(SimpleTestCase):
    def test_empty_text_defaults(self):
        c = classify("")
        self.assertEqual(c.solicitation_type, "unknown")
        self.assertEqual(c.domain, "general")

    def test_federal_rfq(self):
        text = "REQUEST FOR QUOTATION (RFQ) — Standard Form SF-1449, NAICS 541512"
        self.assertEqual(classify(text).solicitation_type, "federal_rfq")

    def test_state_ifb(self):
        text = "INVITATION FOR BID (IFB): sealed bids from lowest responsible bidder"
        self.assertEqual(classify(text).solicitation_type, "state_ifb")

    def test_rfp(self):
        self.assertEqual(classify("Request for Proposal for services").solicitation_type, "rfp")

    def test_prequalification_wins_over_rfp_on_tie(self):
        # Both 'prequalification' and 'rfp' present; specificity favors prequalification.
        text = "Contractor Prequalification — Statement of Qualifications (RFP reference)"
        self.assertEqual(classify(text).solicitation_type, "prequalification")

    def test_domain_it_network(self):
        text = "E-rate structured cabling, network switches, wireless access points, fiber"
        self.assertEqual(classify(text).domain, "it_network")

    def test_domain_construction(self):
        text = "Building renovation: demolition, HVAC, masonry, 40,000 square feet"
        self.assertEqual(classify(text).domain, "construction")

    def test_municipal_solicitation_without_ifb_keyword(self):
        # HRSD-style: numbered "Solicitation" addressed to Bidders, no literal "IFB".
        text = (
            "Solicitation 407973-2 — Fuel Tank Demolitions. HRSD Procurement Office. "
            "Bidders/Offerors Certification. Contractor shall furnish all material for "
            "the demolition of fuel tanks."
        )
        c = classify(text)
        self.assertEqual(c.solicitation_type, "state_ifb")
        self.assertEqual(c.domain, "construction")

    def test_bidders_does_not_override_explicit_rfp(self):
        # A true RFP mentioning bidders once must still classify as rfp.
        text = "Request for Proposal (RFP) for consulting. Bidders shall submit proposals."
        self.assertEqual(classify(text).solicitation_type, "rfp")


class OverridesTests(SimpleTestCase):
    def test_routing_on_injects_only_matching_domain(self):
        c = DocClassification(solicitation_type="rfp", domain="it_network")
        ov = overrides_for_classification(c)
        # IT scope vocabulary injected...
        self.assertIn(ExtractionType.SCOPE_OF_WORK, ov)
        self.assertTrue(any("cabling" in q for q in ov[ExtractionType.SCOPE_OF_WORK]))
        # ...but no federal/state penalty overrides for a plain RFP.
        self.assertNotIn(ExtractionType.MANDATORY_DOCUMENTS, ov)

    def test_routing_on_general_construction_no_it_pollution(self):
        c = DocClassification(solicitation_type="state_ifb", domain="construction")
        ov = overrides_for_classification(c)
        scope = ov.get(ExtractionType.SCOPE_OF_WORK, [])
        self.assertFalse(any("cabling" in q for q in scope))
        # state_ifb penalty override present.
        self.assertIn(ExtractionType.PENALTIES_AND_RISKS, ov)

    @override_settings(INTELLIGENCE_DOC_TYPE_ROUTING_ENABLED=False)
    def test_routing_off_injects_all_overrides(self):
        c = DocClassification(solicitation_type="unknown", domain="general")
        ov = overrides_for_classification(c)
        # Superset = pre-C1 behavior: IT scope vocabulary present even for general doc.
        self.assertTrue(any("cabling" in q for q in ov[ExtractionType.SCOPE_OF_WORK]))
        self.assertIn(ExtractionType.MANDATORY_DOCUMENTS, ov)
