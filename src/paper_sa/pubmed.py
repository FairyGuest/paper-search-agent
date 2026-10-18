import asyncio
import re
import time
from urllib.parse import quote

import httpx
from defusedxml import ElementTree

from .network import ServiceError

BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
RELATIONS = {
    "similar": "pubmed_pubmed",
    "references": "pubmed_pubmed_refs",
    "cited_by": "pubmed_pubmed_citedin",
}


def node_text(node):
    return "".join(node.itertext()).strip() if node is not None else ""


def parse_articles(xml):
    root = ElementTree.fromstring(xml)
    articles = []
    for record in root.findall(".//PubmedArticle"):
        citation = record.find("MedlineCitation")
        article = citation.find("Article")
        if article is None:
            continue
        authors = []
        for author in article.findall("AuthorList/Author"):
            authors.append(
                node_text(author.find("CollectiveName"))
                or " ".join(
                    filter(None, [node_text(author.find("LastName")), node_text(author.find("Initials"))])
                )
            )
        ids = {
            item.attrib.get("IdType"): node_text(item)
            for item in record.findall("PubmedData/ArticleIdList/ArticleId")
        }
        abstract = []
        for section in article.findall("Abstract/AbstractText"):
            label = section.attrib.get("Label", "")
            abstract.append((label + ": " if label else "") + node_text(section))
        date = article.find("Journal/JournalIssue/PubDate")
        year_match = re.search(r"\b(?:19|20)\d{2}\b", node_text(date))
        pmid = node_text(citation.find("PMID"))
        articles.append(
            {
                "pmid": pmid,
                "doi": ids.get("doi", ""),
                "pmcid": ids.get("pmc", ""),
                "title": node_text(article.find("ArticleTitle")),
                "authors": authors,
                "journal": node_text(article.find("Journal/ISOAbbreviation"))
                or node_text(article.find("Journal/Title")),
                "year": year_match.group(0) if year_match else "",
                "abstract": "\n\n".join(abstract),
                "mesh": [
                    node_text(item) for item in citation.findall("MeshHeadingList/MeshHeading/DescriptorName")
                ],
                "publication_types": [
                    node_text(item) for item in article.findall("PublicationTypeList/PublicationType")
                ],
                "article_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }
        )
    return articles


def normalize_query(value):
    value = value.strip()
    url_pmids = re.findall(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", value)
    stripped = re.sub(r"(?i)PMID\s*:?", "", value).strip()
    if re.fullmatch(r"[\d\s,;，；]+", stripped):
        return " OR ".join(f"{item}[uid]" for item in re.findall(r"\d+", stripped))
    if url_pmids:
        return " OR ".join(f"{item}[uid]" for item in url_pmids)
    if re.fullmatch(r"(?i)(?:https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/\S+", value):
        doi = re.sub(r"(?i)^https?://(?:dx\.)?doi\.org/", "", value)
        return f'"{doi}"[AID]'
    if re.fullmatch(r"(?i)PMC\d+", value):
        return f"{value.upper()}[pmc]"
    return value


class PubMed:
    def __init__(self, config):
        self.config = config
        self.lock = asyncio.Lock()
        self.last_request = 0.0

    async def request(self, operation, params, xml=False):
        settings = self.config.settings
        params = dict(params, tool="paper_sa")
        if settings.contact_email:
            params["email"] = settings.contact_email
        if settings.ncbi_api_key:
            params["api_key"] = settings.ncbi_api_key
        async with httpx.AsyncClient(timeout=45) as client:
            for attempt in range(3):
                async with self.lock:
                    await asyncio.sleep(
                        max(
                            0,
                            (0.12 if settings.ncbi_api_key else 0.36)
                            - (time.monotonic() - self.last_request),
                        )
                    )
                    self.last_request = time.monotonic()
                    try:
                        response = await client.get(f"{BASE}/{operation}.fcgi", params=params)
                    except httpx.RequestError:
                        if attempt == 2:
                            raise ServiceError("无法连接 PubMed，请检查网络或代理设置") from None
                        continue
                if response.status_code == 429 or response.status_code >= 500:
                    await asyncio.sleep(1 + 2**attempt)
                    continue
                if response.is_error:
                    raise ServiceError(f"PubMed 请求失败（HTTP {response.status_code}）")
                if xml:
                    return response.text
                try:
                    data = response.json()
                except ValueError:
                    raise ServiceError("PubMed 返回了无效响应") from None
                if data.get("error"):
                    raise ServiceError("PubMed 拒绝了请求，请检查检索式")
                return data
        raise ServiceError("PubMed 限流或暂时不可用，请稍后重试")

    async def search(self, query, limit=20, year_from=None, year_to=None):
        normalized = normalize_query(query)
        params = {"db": "pubmed", "term": normalized, "retmode": "json", "retmax": limit, "sort": "relevance"}
        if year_from or year_to:
            params.update(datetype="pdat", mindate=str(year_from or 1800), maxdate=str(year_to or 2100))
        result = (await self.request("esearch", params)).get("esearchresult", {})
        papers = await self.fetch(result.get("idlist", []))
        return {
            "query": normalized,
            "total": int(result.get("count", 0)),
            "papers": papers,
            "warnings": result.get("warninglist", {}),
            "translation": result.get("querytranslation", normalized),
        }

    async def fetch(self, pmids):
        if not pmids:
            return []
        xml = await self.request(
            "efetch", {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}, xml=True
        )
        try:
            return parse_articles(xml)
        except (ElementTree.ParseError, ValueError):
            raise ServiceError("PubMed 文献解析失败，请稍后重试") from None

    async def neighbors(self, pmid, relation, limit):
        data = await self.request(
            "elink",
            {
                "dbfrom": "pubmed",
                "db": "pubmed",
                "id": pmid,
                "linkname": RELATIONS[relation],
                "retmode": "json",
            },
        )
        ids = []
        for group in data.get("linksets", []):
            for link in group.get("linksetdbs", []):
                if link.get("linkname") == RELATIONS[relation]:
                    ids.extend(str(item) for item in link.get("links", []) if str(item) != pmid)
        return await self.fetch(list(dict.fromkeys(ids))[:limit])

    async def routes(self, metadata):
        doi, pmcid = metadata.get("doi", ""), metadata.get("pmcid", "")
        routes = []
        article_url = f"https://doi.org/{quote(doi, safe='/')}" if doi else metadata.get("article_url", "")
        if pmcid:
            routes.append(
                {
                    "url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/pdf/",
                    "kind": "browser",
                    "label": "PMC",
                }
            )
        if doi.startswith("10.1038/"):
            routes.append(
                {
                    "url": f"https://www.nature.com/articles/{doi.split('/', 1)[1]}.pdf",
                    "kind": "browser",
                    "label": "Nature",
                }
            )
        elif doi.startswith(("10.1002/", "10.1111/")):
            routes.append(
                {
                    "url": f"https://onlinelibrary.wiley.com/doi/pdfdirect/{quote(doi, safe='/')}",
                    "kind": "browser",
                    "label": "Wiley",
                }
            )
        elif doi.startswith("10.1007/"):
            routes.append(
                {
                    "url": f"https://link.springer.com/content/pdf/{quote(doi, safe='/')}.pdf",
                    "kind": "browser",
                    "label": "Springer",
                }
            )
        elif doi.startswith("10.1056/"):
            routes.append(
                {
                    "url": f"https://www.nejm.org/doi/pdf/{quote(doi, safe='/')}?download=true",
                    "kind": "browser",
                    "label": "NEJM",
                }
            )
        async with httpx.AsyncClient(timeout=18) as client:
            if doi.startswith("10.1016/"):
                try:
                    response = await client.get(f"https://api.crossref.org/works/{quote(doi, safe='')}")
                    response.raise_for_status()
                    message = response.json()["message"]
                    alternative = message.get("alternative-id", [])
                    pii = re.sub(r"[-()]", "", alternative[0]) if alternative else ""
                    if re.fullmatch(r"[A-Za-z0-9]+", pii):
                        article_url = f"https://www.sciencedirect.com/science/article/pii/{pii}"
                except (httpx.HTTPError, ValueError, KeyError, IndexError):
                    pass
            if doi and self.config.settings.contact_email:
                try:
                    response = await client.get(
                        f"https://api.unpaywall.org/v2/{quote(doi, safe='')}",
                        params={"email": self.config.settings.contact_email},
                    )
                    response.raise_for_status()
                    for location in response.json().get("oa_locations", []):
                        if location.get("url_for_pdf"):
                            routes.append(
                                {"url": location["url_for_pdf"], "kind": "oa", "label": "Unpaywall 开放获取"}
                            )
                except (httpx.HTTPError, ValueError):
                    pass
        if article_url:
            routes.append({"url": article_url, "kind": "article", "label": "出版商页面"})
        unique = {route["url"]: route for route in routes}
        return list(unique.values())
