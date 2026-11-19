import json
from dataclasses import dataclass
from urllib.parse import quote, urlencode

from app.schemas.journals import normalize_issn
from app.services.authors import normalize_comparison


@dataclass(frozen=True)
class CandidateSeed:
    name: str
    publisher_name: str | None
    issn: str | None
    eissn: str | None
    website_url: str | None
    sources: tuple[str, ...]


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


def _normalize_identifier(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return normalize_issn(value)
    except ValueError:
        return None


def _display_issn(value: str) -> str:
    normalized = _normalize_identifier(value)
    if not normalized:
        raise ProviderError("ISSN 格式无效", retryable=False)
    return f"{normalized[:4]}-{normalized[4:]}"


def _https_url(value: str | None) -> str | None:
    if value and value.lower().startswith("https://"):
        return value
    return None


def _decode_json(result, provider: str) -> dict:
    if result.status >= 400:
        raise ProviderError(
            f"{provider} 请求失败（HTTP {result.status}）",
            retryable=result.status == 429 or result.status >= 500,
        )
    try:
        payload = json.loads(result.text)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"{provider} 返回了无效 JSON", retryable=False) from exc
    if not isinstance(payload, dict):
        raise ProviderError(f"{provider} 返回结构无效", retryable=False)
    return payload


class OpenAlexProvider:
    def __init__(self, client):
        self.client = client

    def discover(self, journal_name: str, issn: str | None, eissn: str | None) -> list[CandidateSeed]:
        identifier = issn or eissn
        if identifier:
            params = {"filter": f"issn:{_display_issn(identifier)}", "per-page": "5"}
        else:
            params = {"search": journal_name, "per-page": "5"}
        result = self.client.get(f"https://api.openalex.org/sources?{urlencode(params)}")
        payload = _decode_json(result, "OpenAlex")
        seeds = []
        for item in payload.get("results", []):
            name = item.get("display_name")
            if not name:
                continue
            values = [
                normalized
                for value in item.get("issn") or []
                if (normalized := _normalize_identifier(value))
            ]
            linking = _normalize_identifier(item.get("issn_l"))
            normalized_issn = _normalize_identifier(issn) or linking or (values[0] if values else None)
            normalized_eissn = _normalize_identifier(eissn) or next(
                (value for value in values if value != normalized_issn), None
            )
            seeds.append(CandidateSeed(
                name=name,
                publisher_name=item.get("host_organization_name"),
                issn=normalized_issn,
                eissn=normalized_eissn,
                website_url=_https_url(item.get("homepage")),
                sources=("OPENALEX",),
            ))
        return seeds


class CrossrefProvider:
    def __init__(self, client):
        self.client = client

    def discover(self, journal_name: str, issn: str | None, eissn: str | None) -> list[CandidateSeed]:
        identifier = issn or eissn
        if identifier:
            url = f"https://api.crossref.org/journals/{_display_issn(identifier)}"
        else:
            url = f"https://api.crossref.org/journals?{urlencode({'query': journal_name, 'rows': '5'})}"
        payload = _decode_json(self.client.get(url), "Crossref")
        message = payload.get("message") or {}
        records = message.get("items", []) if isinstance(message, dict) else []
        if isinstance(message, dict) and message.get("title"):
            records = [message]
        seeds = []
        for item in records:
            raw_title = item.get("title")
            name = raw_title[0] if isinstance(raw_title, list) and raw_title else raw_title
            if not name:
                continue
            typed = {
                entry.get("type"): _normalize_identifier(entry.get("value"))
                for entry in item.get("issn-type") or []
                if isinstance(entry, dict)
            }
            normalized_issn = _normalize_identifier(issn) or typed.get("print")
            normalized_eissn = _normalize_identifier(eissn) or typed.get("electronic")
            seeds.append(CandidateSeed(
                name=name,
                publisher_name=item.get("publisher"),
                issn=normalized_issn,
                eissn=normalized_eissn,
                website_url=_https_url(item.get("URL")),
                sources=("CROSSREF",),
            ))
        return seeds


class DoajProvider:
    def __init__(self, client):
        self.client = client

    def discover(self, journal_name: str, issn: str | None, eissn: str | None) -> list[CandidateSeed]:
        identifier = issn or eissn
        query = f"issn:{_display_issn(identifier)}" if identifier else journal_name
        url = f"https://doaj.org/api/search/journals/{quote(query, safe='')}?pageSize=5"
        payload = _decode_json(self.client.get(url), "DOAJ")
        seeds = []
        for record in payload.get("results", []):
            item = record.get("bibjson") or {}
            name = item.get("title")
            if not name:
                continue
            homepage = next(
                (
                    _https_url(link.get("url"))
                    for link in item.get("link") or []
                    if link.get("type") == "homepage" and _https_url(link.get("url"))
                ),
                None,
            )
            publisher = item.get("publisher") or {}
            seeds.append(CandidateSeed(
                name=name,
                publisher_name=publisher.get("name"),
                issn=_normalize_identifier(issn) or _normalize_identifier(item.get("pissn")),
                eissn=_normalize_identifier(eissn) or _normalize_identifier(item.get("eissn")),
                website_url=homepage,
                sources=("DOAJ",),
            ))
        return seeds


class KimiSearchProvider:
    def __init__(
        self,
        client,
        *,
        api_key: str,
        base_url: str = "https://api.moonshot.ai/v1",
        coding_provider=None,
    ):
        self.client = client
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.coding_provider = coding_provider

    def discover(self, journal_name: str, issn: str | None, eissn: str | None) -> list[CandidateSeed]:
        try:
            return self._discover_search_pro(journal_name, issn, eissn)
        except ProviderError as exc:
            if self.coding_provider is not None and "401" in str(exc):
                return self.coding_provider.discover(journal_name, issn, eissn)
            raise

    def _discover_search_pro(self, journal_name: str, issn: str | None, eissn: str | None) -> list[CandidateSeed]:
        query = f'"{journal_name}" 期刊 官方网站'
        identifier = issn or eissn
        if identifier:
            query = f"{query} ISSN {_display_issn(identifier)}"
        result = self.client.post_json(
            f"{self.base_url}/tools/search_pro",
            {"text_query": query, "limit": 5, "timeout_seconds": 30},
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        payload = _decode_json(result, "Kimi")
        seeds = []
        for item in payload.get("search_results", []):
            website_url = _https_url(item.get("url"))
            if not website_url:
                continue
            seeds.append(CandidateSeed(
                name=journal_name,
                publisher_name=None,
                issn=_normalize_identifier(issn),
                eissn=_normalize_identifier(eissn),
                website_url=website_url,
                sources=("KIMI",),
            ))
        return seeds


class KimiCodingProvider:
    def __init__(
        self,
        client,
        *,
        api_key: str,
        base_url: str = "https://api.kimi.com/coding",
        model: str = "kimi-k3.1-pro",
    ):
        self.client = client
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def discover(self, journal_name: str, issn: str | None, eissn: str | None) -> list[CandidateSeed]:
        identifier = issn or eissn
        prompt = (
            "请仅返回 JSON，不要附带解释。根据你已知的公开信息查找期刊候选官网，"
            "不确定时必须返回空数组，不得编造 URL。"
            "输出结构：{\"candidates\":[{\"name\":\"...\",\"publisher_name\":\"...\","
            "\"issn\":\"...\",\"eissn\":\"...\",\"website_url\":\"https://...\"}]}。"
            f"期刊名称：{journal_name}；"
            f"ISSN/EISSN：{_display_issn(identifier) if identifier else '未提供'}。"
        )
        result = self.client.post_json(
            f"{self.base_url}/v1/messages",
            {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 800,
            },
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        payload = _decode_json(result, "Kimi Coding")
        text = "".join(
            item.get("text", "")
            for item in payload.get("content", [])
            if item.get("type") == "text"
        ).strip()
        if text.startswith("```"):
            text = text.split("\n", maxsplit=1)[-1]
            if text.endswith("```"):
                text = text[:-3]
        try:
            parsed = json.loads(text.strip())
        except json.JSONDecodeError as exc:
            raise ProviderError("Kimi Coding 返回了无效 JSON", retryable=False) from exc
        seeds = []
        for item in parsed.get("candidates", []):
            website_url = _https_url(item.get("website_url"))
            if not website_url:
                continue
            seeds.append(CandidateSeed(
                name=item.get("name") or journal_name,
                publisher_name=item.get("publisher_name"),
                issn=_normalize_identifier(item.get("issn")) or _normalize_identifier(issn),
                eissn=_normalize_identifier(item.get("eissn")) or _normalize_identifier(eissn),
                website_url=website_url,
                sources=("KIMI",),
            ))
        return seeds


def merge_candidate_seeds(seeds: list[CandidateSeed]) -> list[CandidateSeed]:
    merged: dict[str, CandidateSeed] = {}
    for seed in seeds:
        if seed.website_url:
            key = f"url:{seed.website_url.lower().rstrip('/')}"
        elif seed.issn or seed.eissn:
            key = f"id:{seed.issn or seed.eissn}"
        else:
            key = f"name:{normalize_comparison(seed.name)}"
        current = merged.get(key)
        if current is None:
            merged[key] = seed
            continue
        merged[key] = CandidateSeed(
            name=current.name or seed.name,
            publisher_name=current.publisher_name or seed.publisher_name,
            issn=current.issn or seed.issn,
            eissn=current.eissn or seed.eissn,
            website_url=current.website_url or seed.website_url,
            sources=tuple(dict.fromkeys((*current.sources, *seed.sources))),
        )
    return list(merged.values())
