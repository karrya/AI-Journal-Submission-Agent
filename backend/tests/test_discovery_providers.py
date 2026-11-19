import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.crawlers.url_security import FetchResult
from app.services.discovery_providers import (
    CandidateSeed,
    CrossrefProvider,
    DoajProvider,
    KimiSearchProvider,
    KimiCodingProvider,
    OpenAlexProvider,
    ProviderError,
    merge_candidate_seeds,
)


def response(payload, status=200):
    text = json.dumps(payload)
    return FetchResult(
        final_url="https://provider.example",
        status=status,
        headers={},
        body=text.encode(),
        text=text,
        redirects=(),
        content_sha256="hash",
    )


class FakeClient:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status
        self.calls = []

    def get(self, url):
        self.calls.append(("GET", url))
        return response(self.payload, self.status)

    def post_json(self, url, payload, *, headers=None):
        self.calls.append(("POST", url, payload, headers))
        return response(self.payload, self.status)


def test_openalex_discovers_homepage_and_identifiers():
    client = FakeClient({
        "results": [{
            "display_name": "Journal One",
            "homepage": "https://journal.example",
            "issn_l": "0378-5955",
            "issn": ["0378-5955", "1878-1128"],
            "host_organization_name": "Publisher One",
        }]
    })
    items = OpenAlexProvider(client).discover("Journal One", "03785955", None)
    assert items == [CandidateSeed(
        name="Journal One",
        publisher_name="Publisher One",
        issn="03785955",
        eissn="18781128",
        website_url="https://journal.example",
        sources=("OPENALEX",),
    )]
    query = parse_qs(urlsplit(client.calls[0][1]).query)
    assert query["filter"] == ["issn:0378-5955"]


def test_crossref_uses_typed_issn_values():
    client = FakeClient({
        "message": {
            "title": "Journal Two",
            "publisher": "Publisher Two",
            "URL": "https://journal-two.example",
            "ISSN": ["0378-5955", "2434-561X"],
            "issn-type": [
                {"value": "0378-5955", "type": "print"},
                {"value": "2434-561X", "type": "electronic"},
            ],
        }
    })
    items = CrossrefProvider(client).discover("Journal Two", None, None)
    assert items[0].issn == "03785955"
    assert items[0].eissn == "2434561X"
    assert items[0].website_url == "https://journal-two.example"


def test_doaj_maps_public_journal_metadata():
    client = FakeClient({
        "results": [{
            "bibjson": {
                "title": "Open Journal",
                "publisher": {"name": "Open Publisher"},
                "pissn": "0378-5955",
                "eissn": "2434-561X",
                "link": [{"type": "homepage", "url": "https://open.example"}],
            }
        }]
    })
    items = DoajProvider(client).discover("Open Journal", None, None)
    assert items[0].name == "Open Journal"
    assert items[0].publisher_name == "Open Publisher"
    assert items[0].issn == "03785955"
    assert items[0].eissn == "2434561X"
    assert items[0].website_url == "https://open.example"


def test_kimi_search_uses_official_search_endpoint_and_maps_urls():
    client = FakeClient({
        "search_results": [{
            "title": "Journal One official website",
            "url": "https://journal.example/home",
            "snippet": "Journal One ISSN 0378-5955",
        }]
    })
    provider = KimiSearchProvider(client, api_key="secret", base_url="https://api.moonshot.ai/v1")
    items = provider.discover("Journal One", "03785955", None)
    assert items[0].website_url == "https://journal.example/home"
    assert items[0].sources == ("KIMI",)
    method, url, payload, headers = client.calls[0]
    assert url == "https://api.moonshot.ai/v1/tools/search_pro"
    assert "Journal One" in payload["text_query"]
    assert "0378-5955" in payload["text_query"]
    assert headers == {"Authorization": "Bearer secret"}


def test_kimi_coding_messages_returns_verified_candidate_seeds():
    client = FakeClient({
        "content": [{
            "type": "text",
            "text": """```json
            {"candidates": [{"name": "Journal One", "publisher_name": "Publisher One", "issn": "0378-5955", "website_url": "https://journal.example"}]}
            ```""",
        }]
    })
    provider = KimiCodingProvider(
        client,
        api_key="secret",
        base_url="https://api.kimi.com/coding",
        model="kimi-k3.1-pro",
    )
    items = provider.discover("Journal One", "03785955", None)
    assert items[0].name == "Journal One"
    assert items[0].website_url == "https://journal.example"
    assert items[0].issn == "03785955"
    method, url, payload, headers = client.calls[0]
    assert url == "https://api.kimi.com/coding/v1/messages"
    assert payload["model"] == "kimi-k3.1-pro"
    assert headers == {"Authorization": "Bearer secret"}


def test_search_pro_401_falls_back_to_kimi_coding():
    client = FakeClient({}, status=401)
    fallback = FakeClient({
        "content": [{
            "type": "text",
            "text": '{"candidates": [{"name": "Journal One", "website_url": "https://journal.example"}]}',
        }]
    })

    class ClientWithFallback:
        def __init__(self):
            self.calls = []
        def get(self, url):
            return client.get(url)
        def post_json(self, url, payload, *, headers=None):
            self.calls.append(url)
            if url.endswith("/messages"):
                return fallback.post_json(url, payload, headers=headers)
            return client.post_json(url, payload, headers=headers)

    provider = KimiSearchProvider(
        ClientWithFallback(),
        api_key="secret",
        coding_provider=KimiCodingProvider(
            ClientWithFallback(), api_key="secret", base_url="https://api.kimi.com/coding"
        ),
    )
    items = provider.discover("Journal One", None, None)
    assert items[0].website_url == "https://journal.example"


def test_provider_errors_distinguish_retryable_failures():
    with pytest.raises(ProviderError) as caught:
        OpenAlexProvider(FakeClient({}, status=503)).discover("Journal", None, None)
    assert caught.value.retryable is True
    with pytest.raises(ProviderError) as caught:
        KimiSearchProvider(FakeClient({}, status=401), api_key="bad").discover("Journal", None, None)
    assert caught.value.retryable is False


def test_merge_candidates_combines_sources_without_duplicates():
    first = CandidateSeed("Journal", "Publisher", "03785955", None, "https://example.com", ("OPENALEX",))
    second = CandidateSeed("Journal", "Publisher", "03785955", None, "https://example.com/", ("CROSSREF",))
    merged = merge_candidate_seeds([first, second])
    assert len(merged) == 1
    assert merged[0].sources == ("OPENALEX", "CROSSREF")
